import logging
from typing import List

from context import Context
from helper import extract_name, get_child_tree, get_formal_params, get_nested_token, get_tree_token
from lark import Token, Tree
from tir import (
    IRBinExpr,
    IRCall,
    IRCJump,
    IRCompUnit,
    IRConst,
    IRESeq,
    IRExp,
    IRExpr,
    IRFuncDecl,
    IRJump,
    IRLabel,
    IRMem,
    IRMove,
    IRName,
    IRReturn,
    IRSeq,
    IRStmt,
    IRTemp,
)
from type_check import resolve_expression

log = logging.getLogger(__name__)


def lower_comp_unit(tree: Tree, context: Context):
    return IRCompUnit(
        "test", dict([lower_function(f, context) for f in list(tree.find_data("method_declaration"))])
    )


def lower_function(tree: Tree, context: Context):
    method_name = get_nested_token(tree, "IDENTIFIER")
    formal_param_types, formal_param_names = get_formal_params(tree)

    if method_body := next(tree.find_data("method_body"), None):
        return (
            method_name,
            IRFuncDecl(method_name, lower_statement(method_body.children[0], context), formal_param_names),
        )

    return (method_name, IRFuncDecl(method_name, IRStmt(), formal_param_names))


def lower_token(token: Token):
    match token.type:
        case "INTEGER_L" | "char_l" | "NULL":
            return IRConst(token.value)
        case "BOOLEAN_L":
            return IRConst(1 if token.value == "true" else 0)
        case "string_l":
            raise Exception("strings are objects")
        case x:
            raise Exception(f"couldn't parse token {x}")


def get_arguments(context: Context, tree: Tree) -> List[IRExpr]:
    if arg_lists := list(tree.find_data("argument_list")):
        # get the last one, because find_data fetches bottom-up
        return [lower_expression(c, context) for c in arg_lists[-1].children]
    return []


def lower_expression(tree: Tree | Token, context: Context) -> IRExpr:
    if isinstance(tree, Token):
        return lower_token(tree)

    match tree.data:
        case "expr":
            return lower_expression(tree.children[0], context)

        case (
            "mult_expr"
            | "add_expr"
            | "sub_expr"
            | "rel_expr"
            | "eq_expr"
            | "eager_and_expr"
            | "eager_or_expr"
        ):
            left, right = [lower_expression(tree.children[i], context) for i in [0, -1]]
            op_type = tree.data[:-5][:3].upper() if len(tree.children) == 2 else tree.children[1].type
            return IRBinExpr(op_type, left, right)

        case "and_expr":
            left, right = [tree.children[i] for i in [0, -1]]

            return IRESeq(
                IRSeq(
                    [
                        IRMove(IRTemp("t"), IRConst(0)),
                        IRCJump(
                            lower_expression(left, context),
                            IRName(f"_{id(tree)}_lt"),
                            IRName(f"_{id(tree)}_lf"),
                        ),
                        IRLabel(f"_{id(tree)}_lt"),
                        IRMove(IRTemp("t"), lower_expression(right, context)),
                        IRLabel(f"_{id(tree)}_lf"),
                    ]
                ),
                IRTemp("t"),
            )

        case "or_expr":
            left, right = [tree.children[i] for i in [0, -1]]

            return IRESeq(
                IRSeq(
                    [
                        IRMove(IRTemp("t"), IRConst(0)),
                        IRCJump(
                            lower_expression(left, context),
                            IRName(f"_{id(tree)}_lt"),
                            IRName(f"_{id(tree)}_lf"),
                        ),
                        IRLabel(f"_{id(tree)}_lt"),
                        IRMove(IRTemp("t"), IRConst(1)),
                        IRLabel(f"_{id(tree)}_lf"),
                        IRMove(IRTemp("t"), lower_expression(right, context)),
                    ]
                ),
                IRTemp("t"),
            )

        case "expression_name":
            name = extract_name(tree)
            return IRTemp(name)  # if context.resolve(LocalVarDecl, name)

        # case "field_access":
        #     return lower_expression(tree.children[0], context)

        case "method_invocation":
            if isinstance(tree.children[0], Tree) and tree.children[0].data == "method_name":
                args = get_arguments(context, tree)

                return IRCall(IRName(extract_name(tree.children[0])), args)

            # lhs is expression
            args = get_arguments(context, tree if len(tree.children) == 2 else tree.children[-1])
            expr_type = resolve_expression(tree.children[0], context)

            return IRCall(IRName(f"java.lang.{expr_type.name.capitalize()}.{extract_name(tree)}"), args)

        case "unary_negative_expr":
            return IRBinExpr("MUL", IRConst(-1), lower_expression(tree.children[0], context))

        case "unary_complement_expr":
            return IRBinExpr("SUB", IRConst(1), lower_expression(tree.children[0], context))

        case "assignment":
            lhs_tree = next(tree.find_data("lhs")).children[0]
            lhs = lower_expression(lhs_tree, context)
            rhs = lower_expression(tree.children[1], context)

            if lhs_tree.data != "array_access":
                return IRESeq(IRMove(lhs, rhs), lhs)

            assert isinstance(lhs, IRESeq)
            assert isinstance(lhs.stmt, IRSeq)

            lhs.stmt.stmts.append(IRMove(IRMem(lhs.expr), rhs))
            return IRESeq(lhs.stmt, rhs)

        case "cast_expr":
            cast_target = tree.children[-1]
            # We might need to do some conversions?
            return lower_expression(cast_target, context)

        case "for_update":
            return lower_expression(tree.children[0], context)

        case "array_access":
            ref_array, index = tree.children

            err_label = f"_{id(tree)}_lerr"
            nonnull_label = f"_{id(tree)}_lnnull"
            inbound_label = f"_{id(tree)}_linbound"
            outbound_label = f"_{id(tree)}_loutbound"

            return IRESeq(
                IRSeq(
                    [
                        IRMove(IRTemp("a"), lower_expression(ref_array, context)),
                        IRCJump(
                            IRBinExpr("EQ", IRTemp("a"), IRConst(0)), IRName(err_label), IRName(nonnull_label)
                        ),
                        IRLabel(err_label),
                        IRExp(IRCall(IRName("__exception"))),
                        IRLabel(nonnull_label),
                        IRMove(IRTemp("i"), lower_expression(index, context)),
                        IRCJump(
                            IRBinExpr(
                                "LOGICAL_AND",
                                IRBinExpr(
                                    "LT", IRTemp("i"), IRMem(IRBinExpr("SUB", IRTemp("a"), IRConst(4)))
                                ),
                                IRBinExpr("GT_EQ", IRTemp("i"), IRConst(0)),
                            ),
                            IRName(inbound_label),
                            IRName(outbound_label),
                        ),
                        IRLabel(inbound_label),
                    ]
                ),
                IRMem(
                    IRBinExpr(
                        "ADD",
                        IRTemp("a"),
                        IRBinExpr("ADD", IRBinExpr("MUL", IRConst(4), IRTemp("i")), IRConst(4)),
                    )
                ),
            )

        case "array_creation_expr":
            _new_kw, _array_type, size_expr = tree.children

            err_label = f"_{id(tree)}_lerr"
            nonneg_label = f"_{id(tree)}_lnneg"

            stmts: List[IRStmt] = [
                IRMove(IRTemp("n"), lower_expression(size_expr, context)),
                IRCJump(IRBinExpr("LT", IRTemp("n"), IRConst(0)), IRName(err_label), IRName(nonneg_label)),
                IRLabel(err_label),
                IRExp(IRCall(IRName("__exception"))),
                IRLabel(nonneg_label),
                IRMove(
                    IRTemp("m"),
                    IRCall(
                        IRName("__malloc"),
                        [IRBinExpr("ADD", IRBinExpr("MUL", IRTemp("n"), IRConst(4)), IRConst(8))],
                    ),
                ),
                IRMove(IRMem(IRTemp("m")), IRTemp("n")),
            ]

            # Zero-initialize array
            cond_label = f"_{id(tree)}_cond"
            true_label = f"_{id(tree)}_lt"
            false_label = f"_{id(tree)}_lf"

            # Cursed manual for loop in TIR
            stmts.extend(
                [
                    IRMove(IRTemp("i"), IRConst(0)),
                    IRMove(IRTemp("c"), IRBinExpr("ADD", IRTemp("m"), IRConst(4))),
                    IRLabel(cond_label),
                    IRCJump(
                        IRBinExpr("LT", IRTemp("i"), IRTemp("n")), IRName(true_label), IRName(false_label)
                    ),  # for (i = 0; i < n)
                    IRLabel(true_label),
                    IRMove(IRMem(IRTemp("c")), IRConst(0)),  # mem(c) = 0
                    IRMove(IRTemp("c"), IRBinExpr("ADD", IRTemp("c"), IRConst(4))),  # c += 4
                    IRMove(IRTemp("i"), IRBinExpr("ADD", IRTemp("i"), IRConst(1))),  # i++
                    IRJump(IRName(cond_label)),
                    IRLabel(false_label),
                ]
            )

            return IRESeq(IRSeq(stmts), IRBinExpr("ADD", IRTemp("m"), IRConst(4)))

        case "char_l":
            return IRConst(tree.children[0].value)

        case _:
            log.info(f"{tree}")
            raise Exception(f"! Lower for {tree.data} not implemented")


def lower_c(expr: Tree | Token, context: Context, true_label: IRName, false_label: IRName) -> IRStmt:
    if isinstance(expr, Token):
        if expr == "true":
            return IRJump(true_label)
        if expr == "false":
            return IRJump(false_label)
    else:
        match expr.data:
            case "unary_complement_expr":
                return lower_c(expr.children[0], context, false_label, true_label)

            case "and_expr":
                left, right = [expr.children[i] for i in [0, -1]]

                return IRSeq(
                    [
                        lower_c(left, context, IRName(str(id(expr))), false_label),
                        IRLabel(str(id(expr))),
                        lower_c(right, context, true_label, false_label),
                    ]
                )

            case "or_expr":
                left, right = [expr.children[i] for i in [0, -1]]

                return IRSeq(
                    [
                        lower_c(left, context, true_label, IRName(str(id(expr)))),
                        IRLabel(str(id(expr))),
                        lower_c(right, context, true_label, false_label),
                    ]
                )

    return IRCJump(lower_expression(expr, context), true_label, false_label)


def lower_statement(tree: Tree, context: Context) -> IRStmt:
    if isinstance(tree, Token):
        if tree.value == ";":
            return IRStmt()
        log.info(f"{tree}")
        raise Exception("e")

    match tree.data:
        case "block":
            if len(tree.children) == 0:
                return IRStmt()

            return IRSeq([lower_statement(child, context) for child in tree.children])

        case "local_var_declaration":
            expr = next(tree.find_data("var_initializer")).children[0]
            var_name = get_tree_token(tree, "var_declarator_id", "IDENTIFIER")

            return IRMove(IRTemp(var_name), lower_expression(expr, context))

        case "if_st" | "if_st_no_short_if":
            _if_kw, cond, true_block = tree.children

            true_label = f"_{id(tree)}_lt"
            false_label = f"_{id(tree)}_lf"

            return IRSeq(
                [
                    lower_c(cond, context, IRName(true_label), IRName(false_label)),
                    IRLabel(true_label),
                    lower_statement(true_block, context),
                    IRLabel(false_label),
                ]
            )

        case "if_else_st" | "if_else_st_no_short_if":
            _if_kw, cond, true_block, _else_kw, false_block = tree.children

            true_label = f"_{id(tree)}_lt"
            false_label = f"_{id(tree)}_lf"

            return IRSeq(
                [
                    lower_c(cond, context, IRName(true_label), IRName(false_label)),
                    IRLabel(true_label),
                    lower_statement(true_block, context),
                    IRLabel(false_label),
                    lower_statement(false_block, context),
                ]
            )

        case "while_st" | "while_st_no_short_if":
            _while_kw, cond, loop_body = tree.children

            # Check for constant condition?

            cond_label = f"_{id(tree)}_cond"
            true_label = f"_{id(tree)}_lt"
            false_label = f"_{id(tree)}_lf"

            return IRSeq(
                [
                    IRLabel(cond_label),
                    lower_c(cond, context, IRName(true_label), IRName(false_label)),
                    IRLabel(true_label),
                    lower_statement(loop_body, context),
                    IRJump(IRName(cond_label)),
                    IRLabel(false_label),
                ]
            )

        case "for_st" | "for_st_no_short_if":
            for_init, for_cond, for_update = [
                get_child_tree(tree, name) for name in ["for_init", "expr", "for_update"]
            ]
            loop_body = tree.children[-1]

            # Check for constant condition?

            cond_label = f"_{id(tree)}_cond"
            true_label = f"_{id(tree)}_lt"
            false_label = f"_{id(tree)}_lf"

            return IRSeq(
                [
                    lower_statement(for_init, context),
                    IRLabel(cond_label),
                    lower_c(for_cond, context, IRName(true_label), IRName(false_label)),
                    IRLabel(true_label),
                    lower_statement(loop_body, context),
                    IRExp(lower_expression(for_update, context)),
                    IRJump(IRName(cond_label)),
                    IRLabel(false_label),
                ]
            )

        case "expr_st":
            return IRExp(lower_expression(tree.children[0], context))

        case "return_st":
            return IRReturn(lower_expression(tree.children[1], context) if len(tree.children) > 1 else None)

        case "statement" | "statement_no_short_if":
            return lower_statement(tree.children[0], context)

        case "empty_st":
            return IRStmt()

        case "for_init":
            child = tree.children[0]
            return (
                lower_statement(child, context)
                if child.data == "local_var_declaration"
                else IRExp(lower_expression(child, context))
            )

        case _:
            raise Exception(f"! lower_statement for {tree.data} not implemented")
