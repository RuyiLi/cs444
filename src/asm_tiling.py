import logging
from functools import reduce
from typing import Dict, List, Set, Tuple, TYPE_CHECKING

from tir import (
    IRBinExpr,
    IRCall,
    IRCJump,
    IRCompUnit,
    IRConst,
    IRExpr,
    IRFieldDecl,
    IRFuncDecl,
    IRJump,
    IRLabel,
    IRMem,
    IRMove,
    IRName,
    IRNode,
    IRReturn,
    IRSeq,
    IRStmt,
    IRTemp,
    IRComment,
)

log = logging.getLogger(__name__)


def tile_comp_unit(comp_unit: IRCompUnit):
    asm = ["extern __malloc", "extern __exception", "extern __debexit"]

    if any(func == "test" for func in comp_unit.functions.keys()):
        asm += ["global _start"]
    else:
        asm += [f"global _{comp_unit.name}_init"]

    asm += ["", "__err:", "call __exception", ""]

    if len(comp_unit.fields.keys()) > 0:
        # Field initializers
        asm += [f"_{comp_unit.name}_init:", "push ebp", "mov ebp, esp"]
        temps = reduce(
            lambda acc, field: acc.union(find_temps(field.canonical[0])), comp_unit.fields.values(), set()
        )
        temp_dict = dict([(temp, i) for i, temp in enumerate(temps)])
        asm += [f"sub esp, {len(temps)*4}"]

        for field in comp_unit.fields.values():
            asm += tile_field(field, temp_dict, comp_unit, None)
        asm += ["mov esp, ebp", "pop ebp", "ret", ""]

    # Declared methods
    for name, func in comp_unit.functions.items():
        func_asm = tile_func(func, comp_unit) + [""]

        if name == "test" and len(comp_unit.fields.keys()) > 0:
            func_asm.insert(1, f"call _{comp_unit.name}_init")

        asm += func_asm

    # Class vtable
    asm += ["section .data", f"_class_{comp_unit.name}:"]

    for field in comp_unit.fields.keys():
        asm += [f"dd 0"]

    for func in comp_unit.functions.keys():
        if func == "test":
            continue
        asm += [f"dd _{comp_unit.name}_{func}"]

    return asm


def tile_field(
    field: IRFieldDecl, temp_dict: Dict[str, int], comp_unit: IRCompUnit, func: IRFuncDecl
) -> List[str]:
    stmt, expr = field.canonical
    asm = tile_stmt(stmt, temp_dict, comp_unit, func) if stmt.__str__() != "EMPTY" else []

    return asm + tile_stmt(IRMove(IRTemp(f"{comp_unit.name}.{field.name}"), expr), temp_dict, comp_unit, func)


def find_temps(node: IRNode) -> Set[str]:
    temps = set()

    for child in node.children:
        temps = temps.union(find_temps(child))

    if isinstance(node, IRTemp):
        return {node.name}

    return temps


def tile_func(func: IRFuncDecl, comp_unit: IRCompUnit) -> List[str]:
    asm = []

    if func.name == "test":
        asm += ["_start:"]
    else:
        asm += [
            f"_{comp_unit.name}_{func.name}:",
            "push ebp",  # Save old base pointer
        ]

    asm += ["mov ebp, esp"]  # Update base pointer to start in this call frame

    # Parameters are behind the return address on the stack, so we make them -2
    temp_dict = dict([(param, -(i + 2)) for i, param in enumerate(reversed(func.params))])
    temp_dict["%RET"] = -100

    # Allocate space for local temps
    temps = find_temps(func.body) - set(func.params) - {"%RET"}
    print("TEMPS", temps)
    asm += [f"sub esp, {len(temps)*4}"]

    for i, var in enumerate(temps):
        temp_dict[var] = i

    asm += tile_stmt(func.body, temp_dict, comp_unit, func)

    if func.name != "test":
        asm += ["mov esp, ebp", "pop ebp", "ret"]  # Restore stack and base pointers
        return asm

    main_return = [
        "mov ebx, eax",  # Save final return
        "mov eax, 1",  # sys_exit
        "int 0x80",
    ]

    # Replace "ret" with special returns in main function
    return reduce(lambda a, c: a + ([c] if c != "ret" else main_return), asm, [])


def fmt_bp(index: int | None):
    if index is None:
        raise Exception("Attempted to format with None index!")

    if index == -100:
        return "eax"

    if index < 0:
        return f"[ebp+{-4*index}]"

    index += 1
    return f"[ebp-{4*index}]"


def process_expr(
    expr: IRExpr, temp_dict: Dict[str, int], comp_unit: IRCompUnit, func: IRFuncDecl, reg="ecx"
) -> Tuple[str | int, List[str]]:
    if isinstance(expr, IRConst):
        return (expr.value, [])

    return (reg, tile_expr(expr, reg, temp_dict, comp_unit, func))


bin_op_to_short = {
    "EQ": "e",
    "LT": "l",
    "GT": "g",
    "LT_EQ": "le",
    "GT_EQ": "ge",
    "NOT_EQ": "ne",
}


def tile_stmt(stmt: IRStmt, temp_dict: Dict[str, int], comp_unit: IRCompUnit, func: IRFuncDecl) -> List[str]:
    # log.info(f"tiling stmt {stmt}")

    match stmt:
        case IRCall(target=t, args=args):
            if t.name == "__malloc":
                # malloc() allocates eax bytes and returns address in eax
                return tile_expr(args[0], "eax", temp_dict, comp_unit, func) + ["call __malloc"]

            asm = []

            for arg in args:
                r, r_asm = process_expr(arg, temp_dict, comp_unit, func)
                asm += r_asm + [f"push {r}"]

            asm += [
                f"call _{comp_unit.name}_{t.name.split('.')[-1]}"
                if t.name != "__exception"
                else f"call __exception",
                f"add esp, {len(args)*4}",  # pop off arguments
            ]
            return asm

        case IRCJump(cond=c, true_label=t):
            match c:
                case IRConst(value=v):
                    if v == 0:  # never jump
                        return []
                    if v == 1:  # always jump
                        return [f"jmp {t.name}"]

                    raise Exception(f"CJump with constant value {v} not 0 or 1!!")

                case IRTemp(name=n):
                    if (loc := temp_dict.get(n, None)) is not None:
                        return [f"mov eax, {fmt_bp(loc)}", "cmp eax, 1", f"je {t.name}"]
                    raise Exception(f"CJump with unbound variable {n}")

                case IRBinExpr(op_type=o, left=l, right=r):
                    asm = []
                    assert isinstance(l, IRTemp)

                    left = temp_dict.get(l.name)

                    right, r_asm = process_expr(r, temp_dict, comp_unit, func)
                    asm += r_asm

                    if o in bin_op_to_short.keys():
                        return asm + [
                            f"mov edx, {fmt_bp(left)}",
                            f"cmp edx, {right}",
                            f"j{bin_op_to_short[o]} {t.name}",
                        ]

                    match o:
                        case "LOGICAL_AND":
                            return asm + [
                                f"mov edx, {fmt_bp(left)}",
                                f"and edx, {right}",
                                "cmp edx, 1",
                                f"je {t.name}",
                            ]
                        case "LOGICAL_OR":
                            return asm + [
                                f"mov edx, {fmt_bp(left)}",
                                f"or edx, {right}",
                                "cmp edx, 1",
                                f"je {t.name}",
                            ]
                        case "SUB":
                            return asm + [f"mov edx, {fmt_bp(left)}", f"sub edx, {right}", f"jle {t.name}"]
                        case x:
                            raise Exception(f"CJump with unimplemented cond IRBinExpr with optype {o}")

                case x:
                    raise Exception(f"CJump with unimplemented condition {c}")

        case IRJump(target=t):
            assert isinstance(t, IRName)
            return [f"jmp {t.name}"]

        case IRLabel(name=n):
            return [f"{n}:"]

        case IRMove(target=t, source=s):
            asm = tile_expr(s, "ecx", temp_dict, comp_unit, func)

            match t:
                case IRTemp(name=n):
                    if "." in n:
                        parts = n.split(".")

                        if (loc := temp_dict.get(parts[0], None)) is not None:
                            return asm + [f"mov {fmt_bp(temp_dict.get(parts[0]))}, ecx"]
                            # raise Exception(f"unimplemented field access of objects!")

                        # Must be a class name then
                        # print(".".join(parts[:-1]), comp_unit.name)
                        # assert ".".join(parts[:-1]) == comp_unit.name

                        index = list(comp_unit.fields.keys()).index(parts[-1])
                        return asm + [f"mov [_class_{comp_unit.name} + 4*{index}], ecx"]

                    if (loc := temp_dict.get(n, None)) is not None:
                        return asm + [f"mov {fmt_bp(loc)}, ecx"]

                    raise Exception(f"var {n} doesn't exist in temp dict {temp_dict}!")

                case IRMem(address=a):
                    assert isinstance(a, IRTemp)
                    l, l_asm = process_expr(a, temp_dict, comp_unit, func, "eax")

                    return l_asm + asm + [f"mov [{l}], ecx"]

        case IRReturn(ret=ret):
            if stmt.ret is None:
                return []

            # Return always uses eax register
            stmts = tile_expr(stmt.ret, "eax", temp_dict, comp_unit, func)
            return stmts + ["mov esp, ebp", "pop ebp", "ret"]

        case IRSeq(stmts=ss):
            asm = []
            for s in ss:
                tiled = tile_stmt(s, temp_dict, comp_unit, func)
                # log.info(f"tiled to {tiled}")
                asm += tiled
            return asm

        case IRComment(comment=c):
            return [f"; {c}"]

        case x:
            raise Exception(f"Unknown tiling for statement {x}")

    return []


def tile_expr(
    expr: IRExpr, output_reg: str, temp_dict: Dict[str, int], comp_unit: IRCompUnit, func: IRFuncDecl
) -> List[str]:
    asm = []
    hold = ""

    # log.info(f"tiling expr {expr}")

    match expr:
        case IRConst(value=v):
            hold = v if v != "null" else 0

        case IRBinExpr(op_type=o, left=l, right=r):
            assert isinstance(l, IRTemp)

            left = temp_dict.get(l.name)

            right, r_asm = process_expr(r, temp_dict, comp_unit, func)
            asm += r_asm

            asm.append(f"mov eax, {fmt_bp(left)}")

            if o == "MUL":
                asm.append(f"imul eax, {right}")

            elif o == "DIV":
                # Zero-extend eax into edx for division
                asm.append("cdq")

                if isinstance(r, IRConst):
                    asm.append(f"mov ebx, {right}")
                    right = "ebx"

                label_id = id(expr)

                asm += [
                    f"cmp {right}, 0",
                    f"jne _{label_id}_nonzero",
                    "call __exception",
                    f"_{label_id}_nonzero:",
                    f"idiv {right}",  # Quotient stored in eax, remainder stored in edx
                ]

            elif o == "MODULO":
                # Zero-extend eax into edx for division
                asm.append("cdq")

                if isinstance(r, IRConst):
                    asm.append(f"mov ebx, {right}")
                    right = "ebx"

                label_id = id(expr)

                asm += [
                    f"cmp {right}, 0",
                    f"jne _{label_id}_nonzero",
                    "call __exception",
                    f"_{label_id}_nonzero:",
                    f"idiv {right}",  # Quotient stored in eax, remainder stored in edx
                    "mov eax, edx"
                ]

            elif o in bin_op_to_short.keys():
                asm += [
                    f"cmp eax, {right}",
                    f"set{bin_op_to_short[o]} al",
                    "movzx eax, al",  # Zero-extend AL into EAX
                ]

            elif o[:5] == "EAGER":
                asm.append(f"{o[6:].lower()} eax, {right}")

            else:
                asm.append(f"{o.lower()} eax, {right}")

            hold = "eax"

        case IRMem(address=a):
            address_reg, address_asm = process_expr(a, temp_dict, comp_unit, func)
            asm += address_asm + [f"mov {address_reg}, [{address_reg}]"]
            hold = address_reg

        case IRTemp(name=n):
            if "." not in expr.name:
                if (loc := temp_dict.get(n, None)) is not None:
                    hold = fmt_bp(loc)
                else:
                    log.info(f"{temp_dict.get(n, None)}")
                    log.info(f"{temp_dict}")
                    raise Exception(f"couldn't find local var {n} in dict!")
            else:
                parts = expr.name.split(".")

                if (loc := temp_dict.get(parts[0], None)) is not None:
                    asm += [f"mov eax, {fmt_bp(temp_dict.get(parts[0]))}"]

                    var_type = func.local_vars.get(parts[0])

                    # Accessing array.length
                    if var_type.node_type == "array_type":
                        asm += [f"mov eax, [eax - 4]"]

                    hold = "eax"
                    # raise Exception(f"unimplemented field access of objects!")
                else:
                    index = list(comp_unit.fields.keys()).index(parts[-1])
                    asm += [f"mov eax, [_class_{comp_unit.name} + 4*{index}]"]
                    hold = "eax"

        case x:
            log.info(f"unknown expr type {x}")

    if output_reg != hold:
        asm += [f"mov {output_reg}, {hold}"]

    # log.info(f"{asm}")
    return asm
