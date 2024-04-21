import logging
from functools import reduce
from typing import Dict, List, Set, Tuple

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
)

log = logging.getLogger(__name__)


def tile_comp_unit(comp_unit: IRCompUnit):
    asm = ["extern __malloc", "extern __exception", "extern __debexit"]

    if any(func == "test" for func in comp_unit.functions.keys()):
        asm += ["global _start"]
    else:
        asm += [f"global _{comp_unit.name}_init"]

    asm += [""]

    # Field initializers
    asm += [f"_{comp_unit.name}_init:"]
    for field in comp_unit.fields.values():
        asm += tile_field(field, comp_unit)
    asm += ["ret", ""]

    # Declared methods
    for name, func in comp_unit.functions.items():
        func_asm = tile_func(func, comp_unit) + [""]

        if name == "test":
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


def tile_field(field: IRFieldDecl, comp_unit: IRCompUnit) -> List[str]:
    stmt, expr = field.canonical
    asm = tile_stmt(stmt, {}, comp_unit) if stmt.__str__() != "EMPTY" else []

    return asm + tile_stmt(IRMove(IRTemp(f"{comp_unit.name}.{field.name}"), expr), {}, comp_unit)


def find_local_vars(node: IRNode) -> Set[str]:
    local_vars = set()

    for child in node.children:
        local_vars = local_vars.union(find_local_vars(child))

    if isinstance(node, IRTemp):
        return { node.name }

    return local_vars


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
    local_var_dict = dict([(param, -(i + 2)) for i, param in enumerate(func.params)])
    local_var_dict["%RET"] = -100

    # Allocate space for local variables
    local_vars = find_local_vars(func.body) - set(func.params) - { "%RET" }
    asm += [f"add esp, {len(local_vars)*4}"]

    for i, var in enumerate(local_vars):
        local_var_dict[var] = i

    asm += tile_stmt(func.body, local_var_dict, comp_unit)

    if func.name != "test":
        asm += ["mov esp, ebp", "pop ebp"]      # Restore stack and base pointers
        return asm

    main_return = [
        "mov ebx, eax",  # Save final return
        "mov eax, 1",  # sys_exit
        "int 0x80",
    ]

    # Replace "ret" with special returns in main function
    return reduce(lambda a, c: a + ([c] if c != "ret" else main_return), asm, [])


def fmt_bp(index: int):
    if index is None:
        raise Exception("Attempted to format with None index!")

    if index == -100:
        return "eax"

    if index < 0:
        return f"[ebp+{-4*index}]"

    index += 1
    return f"[ebp-{4*index}]"


def process_expr(expr: IRExpr, local_var_dict: Dict[str, int], comp_unit: IRCompUnit, reg="ecx") -> Tuple[str | int, List[str]]:
    if isinstance(expr, IRConst):
        return (expr.value, [])

    return (reg, tile_expr(expr, reg, local_var_dict, comp_unit))


def tile_stmt(stmt: IRStmt, local_var_dict: Dict[str, int], comp_unit: IRCompUnit) -> List[str]:
    log.info(f"tiling stmt {stmt}")

    match stmt:
        case IRCall(target=t, args=args):
            if t.name == "__malloc":
                # malloc() allocates eax bytes and returns address in eax
                return tile_expr(args[0], "eax", local_var_dict, comp_unit) + ["call __malloc"]

            asm = []

            for arg in args:
                r, r_asm = process_expr(arg, local_var_dict, comp_unit)
                asm += r_asm + [f"push {r}"]

            asm += [
                f"call _{comp_unit.name}_{t.name.split('.')[-1]}" if t.name != "__exception" else f"call __exception",
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
                    if (loc := local_var_dict.get(n, None)) is not None:
                        return [f"mov eax, {fmt_bp(loc)}", "cmp eax, 1", f"je {t.name}"]
                    raise Exception(f"CJump with unbound variable {n}")

                case IRBinExpr(op_type=o, left=l, right=r):
                    asm = []
                    assert isinstance(l, IRTemp)

                    left = local_var_dict.get(l.name)

                    right, r_asm = process_expr(r, local_var_dict, comp_unit)
                    asm += r_asm

                    match o:
                        case "EQ":
                            return asm + [f"mov edx, {fmt_bp(left)}", f"cmp edx, {right}", f"je {t.name}"]
                        case "LT":
                            return asm + [f"mov edx, {fmt_bp(left)}", f"cmp edx, {right}", f"jl {t.name}"]
                        case "NOT_EQ":
                            return asm + [f"mov edx, {fmt_bp(left)}", f"cmp edx, {right}", f"jne {t.name}"]
                        case "LOGICAL_AND":
                            return asm + [
                                f"mov edx, {fmt_bp(left)}",
                                f"and edx, {right}",
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
            asm = tile_expr(s, "ecx", local_var_dict, comp_unit)

            match t:
                case IRTemp(name=n):
                    if "." in n:
                        parts = n.split(".")

                        if (loc := local_var_dict.get(parts[0], None)) is not None:
                            return asm + [f"mov {fmt_bp(local_var_dict.get(parts[0]))}, ecx"]
                            # raise Exception(f"unimplemented field access of objects!")

                        # Must be a class name then
                        # print(".".join(parts[:-1]), comp_unit.name)
                        # assert ".".join(parts[:-1]) == comp_unit.name

                        index = list(comp_unit.fields.keys()).index(parts[-1])
                        return asm + [f"mov [_class_{comp_unit.name} + 4*{index}], ecx"]

                    if (loc := local_var_dict.get(n, None)) is not None:
                        log.info(f"VARIABLE {n} EXISTS AT {loc}")
                        return asm + [f"mov {fmt_bp(loc)}, ecx"]

                    raise Exception(f"CREATING NEW VAR {n} AT LOC {local_var_dict[n]}")

                case IRMem(address=a):
                    assert isinstance(a, IRTemp)
                    l, l_asm = process_expr(a, local_var_dict, comp_unit, "eax")

                    return l_asm + asm + [f"mov [{l}], ecx"]

        case IRReturn(ret=ret):
            if stmt.ret is None:
                return []

            # Return always uses eax register
            stmts = tile_expr(stmt.ret, "eax", local_var_dict, comp_unit)
            return stmts + ["mov esp, ebp", "pop ebp", "ret"]

        case IRSeq(stmts=ss):
            asm = []
            for s in ss:
                tiled = tile_stmt(s, local_var_dict, comp_unit)
                log.info(f"tiled to {tiled}")
                asm += tiled
            return asm

        case x:
            raise Exception(f"Unknown tiling for statement {x}")

    return []


def tile_expr(expr: IRExpr, output_reg: str, local_var_dict: Dict[str, int], comp_unit: IRCompUnit) -> List[str]:
    asm = []
    hold = ""

    log.info(f"tiling expr {expr}")

    match expr:
        case IRConst(value=v):
            hold = v

        case IRBinExpr(op_type=o, left=l, right=r):
            assert isinstance(l, IRTemp)

            left = local_var_dict.get(l.name)

            right, r_asm = process_expr(r, local_var_dict, comp_unit)
            asm += r_asm

            asm.append(f"mov eax, {fmt_bp(left)}")

            if o == "MUL":
                asm.append(f"imul eax, {right}")

            elif o == "DIV":
                if isinstance(r, IRConst):
                    asm.append(f"mov ebx, {right}")
                    right = "ebx"

                asm += [
                    "xor edx, edx",  # Clear out edx for division
                    f"div {right}",  # Quotient stored in eax, remainder stored in edx
                ]

            elif o == "LT":
                asm += [
                    f"cmp eax, {right}",
                    "setl al",
                    "movzx eax, al",  # Zero-extend AL into EAX
                ]

            elif o == "GT_EQ":
                asm += [
                    f"cmp eax, {right}",
                    "setge al",
                    "movzx eax, al",  # Zero-extend AL into EAX
                ]

            elif o == "EQ":
                asm += [
                    f"cmp eax, {right}",
                    "sete al",
                    "movzx eax, al",  # Zero-extend AL to EAX
                ]

            elif o == "NOT_EQ":
                asm += [
                    f"cmp eax, {right}",
                    "setne al",
                    "movzx eax, al",  # Zero-extend AL to EAX
                ]

            else:
                asm.append(f"{o.lower()} eax, {right}")

            hold = "eax"

        case IRMem(address=a):
            address_reg, address_asm = process_expr(a, local_var_dict, comp_unit)
            asm += address_asm + [f"mov {address_reg}, [{address_reg}]"]
            hold = address_reg

        case IRTemp(name=n):
            if "." not in expr.name:
                if (loc := local_var_dict.get(n, None)) is not None:
                    hold = fmt_bp(loc)
                else:
                    log.info(f"{local_var_dict.get(n, None)}")
                    log.info(f"{local_var_dict}")
                    raise Exception(f"couldn't find local var {n} in dict!")
            else:
                parts = expr.name.split(".")

                if (loc := local_var_dict.get(parts[0], None)) is not None:
                    asm += [f"mov eax, {fmt_bp(local_var_dict.get(parts[0]))}"]
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

    log.info(f"{asm}")
    return asm
