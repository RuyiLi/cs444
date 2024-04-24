from __future__ import annotations

import logging
from functools import reduce
from typing import Dict, List, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from context import GlobalContext, Context

from type_link import ClassInterfaceDecl
from tir import (
    IRBinExpr,
    IRCall,
    IRCJump,
    IRComment,
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


externs = set()


def tile_comp_unit(comp_unit: IRCompUnit, context: GlobalContext):
    externs.clear()
    asm = ["extern __malloc", "extern __exception", "extern __debexit"]
    init_label = f"_{comp_unit.name}_init"

    if any(func == "test^" for func in comp_unit.functions.keys()):
        asm += [
            f"extern _{child.parent_node.name}_init"
            for child in context.children
            if child.parent_node.name != comp_unit.name
        ] + ["global _start"]
    else:
        asm += [f"global {init_label}"]

    asm += ["", "__err:", "call __exception", ""]

    # Field initializers
    asm += [f"{init_label}:"]

    temps = sorted(
        reduce(lambda acc, field: acc.union(find_temps(field.canonical[0])), comp_unit.fields.values(), set())
    )
    temp_dict = dict([(temp, i) for i, temp in enumerate(temps)])

    if len(temps) > 0:
        asm += ["push ebp", "mov ebp, esp", f"sub esp, {len(temps) * 4}"]

    instance_fields = []

    for field in comp_unit.fields.values():
        if "static" in field.modifiers:
            asm += tile_static_field(field, temp_dict, comp_unit, None, context)
        else:
            instance_fields.append(field)

    if len(temps) > 0:
        asm += ["mov esp, ebp", "pop ebp"]

    asm += ["ret", ""]

    # Declared methods
    static_methods = set()
    for name, func in comp_unit.functions.items():
        func_asm = tile_func(func, comp_unit, context) + [""]

        if name == "test^":
            func_asm = (
                func_asm[:1]
                + [f"call _{child.parent_node.name}_init" for child in context.children]
                + func_asm[1:]
            )

        if "static" in func.modifiers or func.is_constructor:
            # maybe add 'public' to modifier condition?
            static_methods.add(func_label(func, comp_unit))

        asm += func_asm

    asm += ["section .data"]

    # Static fields
    static_fields = set()
    for field_name, field in comp_unit.fields.items():
        if "static" in field.modifiers:
            asm += [f"_field_{comp_unit.name}_{field_name}:", "dd 0"]
            static_fields.add(f"_field_{comp_unit.name}_{field_name}")

    # TODO: Class vtable (for instance methods)

    # Extern used static fields, make local static fields globally available
    statics = static_fields | static_methods
    asm = (
        asm[:3]
        + [f"global {f}" for f in statics]
        + [f"extern {e}" for e in externs if e not in statics]
        + asm[3:]
    )
    return asm


def tile_static_field(
    field: IRFieldDecl,
    temp_dict: Dict[str, int],
    comp_unit: IRCompUnit,
    func: IRFuncDecl,
    context: Context,
) -> List[str]:
    stmt, expr = field.canonical
    asm = tile_stmt(stmt, temp_dict, comp_unit, func, context) if str(stmt) != "EMPTY" else []

    return asm + tile_stmt(
        IRMove(IRTemp(f"{comp_unit.name}.{field.name}"), expr), temp_dict, comp_unit, func, context
    )


def find_temps(node: IRNode) -> Set[str]:
    temps = set()

    for child in node.children:
        temps = temps.union(find_temps(child))

    if isinstance(node, IRTemp):
        return {node.name}

    return temps


def fix_param_names(param_names: str) -> str:
    # this probably breaks if the typename is literally ARRTYPE lol
    return param_names.replace("[]", "ARRTYPE")


def func_label(func: IRFuncDecl, comp_unit: IRCompUnit) -> str:
    param_names = "_".join(param.name for param in func.formal_param_types)
    return f"_{comp_unit.name}_{func.name}_{fix_param_names(param_names)}"


def tile_func(func: IRFuncDecl, comp_unit: IRCompUnit, context: Context) -> List[str]:
    asm = []

    if func.name == "test":
        asm += ["_start:"]
    else:
        asm += [
            f"{func_label(func, comp_unit)}:",
            "push ebp",  # Save old base pointer
        ]

    asm += ["mov ebp, esp"]  # Update base pointer to start in this call frame

    params = func.params
    if "static" not in func.modifiers:
        params.insert(0, "%THIS")

    # Parameters are behind the return address on the stack, so we make them -2
    temp_dict = dict([(param, -(i + 2)) for i, param in enumerate(reversed(params))])
    temp_dict["%RET"] = -100

    # Allocate space for local temps
    temps = sorted(find_temps(func.body) - set(params) - {"%RET"})
    asm += [f"sub esp, {len(temps) * 4}"]

    print(f"For function {comp_unit.name}.{func.name}, temps are {temps}", temp_dict)

    for i, var in enumerate(temps):
        temp_dict[var] = i

    asm += tile_stmt(func.body, temp_dict, comp_unit, func, context)

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

    if isinstance(expr, IRName):
        externs.add(expr.name)
        return (reg, [f"mov {reg}, {expr.name}"])

    return (reg, tile_expr(expr, reg, temp_dict, comp_unit, func))


bin_op_to_short = {
    "EQ": "e",
    "LT": "l",
    "GT": "g",
    "LT_EQ": "le",
    "GT_EQ": "ge",
    "NOT_EQ": "ne",
}


def tile_stmt(
    stmt: IRStmt,
    temp_dict: Dict[str, int],
    comp_unit: IRCompUnit,
    func: IRFuncDecl,
    context: Context,
) -> List[str]:
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

            target, target_asm = process_expr(t, temp_dict, comp_unit, func)

            asm += target_asm + [
                f"call {target}" if t.name != "__exception" else "call __exception",
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

                        return asm + [f"mov [_field_{comp_unit.name}_{parts[-1]}], ecx"]

                    if (loc := temp_dict.get(n, None)) is not None:
                        if func is not None and n in func.actual_local_var_decls:
                            return asm + [f"mov {fmt_bp(loc)}, ecx"]

                        # implicit this
                        # does not handle k = 9; int k = 3; case
                        type_decl = context.resolve(ClassInterfaceDecl, comp_unit.name)
                        if n in type_decl.all_instance_fields:
                            index = type_decl.all_instance_fields.index(n)
                            this_addr = temp_dict["%THIS"]
                            return asm + [
                                f"; begin implicit this for {n}",
                                f"mov ebx, {fmt_bp(this_addr)}",
                                f"mov [ebx+{index * 4 + 4}], ecx",
                            ]

                        # an actual intermediate result
                        return asm + [f"mov {fmt_bp(loc)}, ecx"]

                    raise Exception(f"var {n} doesn't exist in temp dict {temp_dict}!")

                case IRMem(address=a):
                    assert isinstance(a, IRTemp)
                    return asm + tile_expr(a, "eax", temp_dict, comp_unit, func) + ["mov [eax], ecx"]

        case IRReturn(ret=ret):
            if ret is None:
                return []

            # Return always uses eax register
            stmts = tile_expr(ret, "eax", temp_dict, comp_unit, func)
            return stmts + ["mov esp, ebp", "pop ebp", "ret"]

        case IRSeq(stmts=ss):
            asm = []
            for s in ss:
                tiled = tile_stmt(s, temp_dict, comp_unit, func, context)
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
    available_regs = ["eax", "ebx", "ecx", "edx"]

    def allocate_register():
        return available_regs.pop(0) if available_regs else None

    def free_register(reg):
        available_regs.append(reg)

    hold = ""

    def spill_to_memory(var_name):
        nonlocal asm
        reg = temp_dict[var_name]
        asm += [f"mov {fmt_bp(reg)}, {output_reg}"]
        free_register(output_reg)
        temp_dict[var_name] = None

    def process_temp(temp: str):
        nonlocal asm, output_reg
        if temp in temp_dict:
            reg = temp_dict[temp]
            if reg is None:
                reg = allocate_register()
                temp_dict[temp] = reg
                asm += [f"mov {reg}, {fmt_bp(reg)}"]
            output_reg = reg
        else:
            reg = allocate_register()
            temp_dict[temp] = reg
            asm += [f"mov {reg}, {fmt_bp(reg)}"]
            output_reg = reg

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
                    "mov eax, edx",
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
                        asm += ["mov eax, [eax - 4]"]

                    hold = "eax"
                    # raise Exception(f"unimplemented field access of objects!")
                else:
                    asm += [f"mov eax, [_field_{comp_unit.name}_{parts[-1]}]"]
                    hold = "eax"

        case x:
            log.info(f"unknown expr type {x}")

    if output_reg != hold:
        asm += [f"mov {output_reg}, {hold}"]

    # if output_reg not in ["eax", "ebx", "ecx", "edx"]:
    #     print("AAADSDSDAD")
    #     spill_to_memory(output_reg)

    # log.info(f"{asm}")
    return asm
