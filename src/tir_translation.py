import logging
from typing import List

from context import Context, GlobalContext
from helper import (
    extract_name,
    get_child_tree,
    get_enclosing_type_decl,
    get_formal_params,
    get_nested_token,
    get_tree_token,
)
from lark import Token, Tree
from joos_types import ArrayType, ReferenceType
from tir import (
    IRBinExpr,
    IRCall,
    IRCJump,
    IRCompUnit,
    IRConst,
    IRESeq,
    IRExp,
    IRExpr,
    IRFieldDecl,
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
    IRComment,
)
from type_check import resolve_expression

log = logging.getLogger(__name__)

global_id = 0
err_label = "__err"


def get_id():
    global global_id
    global_id += 1
    return global_id


def lower_comp_unit(context: Context, parent_context: GlobalContext):
    return IRCompUnit(
        context.parent_node.name,
        dict([lower_field(f, context) for f in list(context.tree.find_data("field_declaration"))]),
        dict([lower_function(f, context) for f in list(context.tree.find_data("method_declaration"))]),
    )


def lower_field(tree: Tree, context: Context):
    field_name = get_nested_token(tree, "IDENTIFIER")

    rhs_tree = next(tree.find_data("var_initializer"), None)
    if rhs_tree is None:
        return (field_name, IRFieldDecl(field_name, IRConst("null")))

    return (field_name, IRFieldDecl(field_name, lower_expression(rhs_tree.children[0], context)))


local_vars = dict()


def lower_function(tree: Tree, context: Context):
    method_declarator = next(tree.find_data("method_declarator"))
    method_name = get_nested_token(method_declarator, "IDENTIFIER")
    formal_param_types, formal_param_names = get_formal_params(tree)
    nested_context = context.child_map[method_name]

    if method_body := next(tree.find_data("method_body"), None):
        local_vars.clear()
        body = lower_statement(method_body.children[0], nested_context)

        # Add parameters to local var type dictionary
        for i in range(len(formal_param_names)):
            local_vars[formal_param_names[i]] = get_enclosing_type_decl(nested_context).resolve_type(
                formal_param_types[i]
            )

        return (
            method_name,
            IRFuncDecl(method_name, body, formal_param_names, local_vars.copy()),
        )

    return (method_name, IRFuncDecl(method_name, IRStmt(), formal_param_names, dict()))


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

    if not isinstance(tree, Tree):
        # assume primitive python value
        return IRConst(tree)

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
            label_id = get_id()

            save_temp = f"_{label_id}_save"

            return IRESeq(
                IRSeq(
                    [
                        IRMove(IRTemp(save_temp), IRConst(0)),
                        IRCJump(
                            lower_expression(left, context),
                            IRName(f"_{label_id}_lt"),
                            IRName(f"_{label_id}_lf"),
                        ),
                        IRLabel(f"_{label_id}_lt"),
                        IRMove(IRTemp(save_temp), lower_expression(right, context)),
                        IRLabel(f"_{label_id}_lf"),
                    ]
                ),
                IRTemp(save_temp),
            )

        case "or_expr":
            left, right = [tree.children[i] for i in [0, -1]]
            label_id = get_id()

            save_temp = f"_{label_id}_save"

            return IRESeq(
                IRSeq(
                    [
                        IRMove(IRTemp(save_temp), IRConst(1)),
                        IRCJump(
                            lower_expression(left, context),
                            IRName(f"_{label_id}_lt"),
                            None,
                        ),
                        IRMove(IRTemp(save_temp), lower_expression(right, context)),
                        IRLabel(f"_{label_id}_lt"),
                    ]
                ),
                IRTemp(save_temp),
            )

        case "expression_name":
            name = extract_name(tree)
            return IRTemp(name)  # if context.resolve(LocalVarDecl, name)

        case "field_access":
            primary, identifier = tree.children

            primary_expr = lower_expression(primary, context)
            assert isinstance(primary_expr, IRESeq)

            primary_type = resolve_expression(primary, context)
            assert isinstance(primary_type, ReferenceType)

            if isinstance(primary_type, ArrayType):
                return IRESeq(primary_expr.stmt, IRMem(IRBinExpr("SUB", primary_expr.expr, IRConst(4))));

            raise Exception(f"unimplemented field access on {primary}, {identifier}!")

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

            lhs.stmt.stmts.append(IRMove(lhs.expr, rhs))
            return IRESeq(lhs.stmt, lhs.expr)

        case "cast_expr":
            cast_target = tree.children[-1]
            # We might need to do some conversions?
            return lower_expression(cast_target, context)

        case "for_update":
            return lower_expression(tree.children[0], context)

        case "array_access":
            ref_array, index = tree.children
            label_id = get_id()

            nonnull_label = f"_{label_id}_lnnull"
            ref_temp = f"_{label_id}_ref"
            index_temp = f"_{label_id}_index"

            return IRESeq(
                IRSeq(
                    [
                        IRMove(IRTemp(ref_temp), lower_expression(ref_array, context)),
                        IRCJump(IRBinExpr("NOT_EQ", IRTemp(ref_temp), IRConst(0)), IRName(nonnull_label), None),
                        IRJump(IRName(err_label)),
                        IRLabel(nonnull_label),
                        IRMove(IRTemp(index_temp), lower_expression(index, context)),
                        IRCJump(
                            IRBinExpr(
                                "LOGICAL_OR",
                                IRBinExpr(
                                    "GT_EQ", IRTemp(index_temp), IRMem(IRBinExpr("SUB", IRTemp(ref_temp), IRConst(4)))
                                ),
                                IRBinExpr("LT", IRTemp(index_temp), IRConst(0)),
                            ),
                            IRName(err_label),
                            None,
                        ),
                        IRComment("array access end"),
                    ]
                ),
                IRMem(
                    IRBinExpr(
                        "ADD",
                        IRTemp(ref_temp),
                        IRBinExpr("ADD", IRBinExpr("MUL", IRConst(4), IRTemp(index_temp)), IRConst(4)),
                    )
                ),
            )

        case "array_creation_expr":
            _new_kw, _array_type, size_expr = tree.children
            label_id = get_id()

            nonneg_label = f"_{label_id}_lnneg"
            size_temp = f"_{label_id}_size"
            ref_temp = f"_{label_id}_ref"

            stmts: List[IRStmt] = [
                IRMove(IRTemp(size_temp), lower_expression(size_expr, context)),
                IRCJump(IRBinExpr("GT_EQ", IRTemp(size_temp), IRConst(0)), IRName(nonneg_label), None),
                IRJump(IRName(err_label)),
                IRLabel(nonneg_label),
                IRMove(
                    IRTemp(ref_temp),
                    IRCall(
                        IRName("__malloc"),
                        [IRBinExpr("ADD", IRBinExpr("MUL", IRTemp(size_temp), IRConst(4)), IRConst(8))],
                    ),
                ),
                IRMove(IRMem(IRTemp(ref_temp)), IRTemp(size_temp)),
            ]

            # Zero-initialize array
            cond_label = f"_{label_id}_cond"
            false_label = f"_{label_id}_lf"
            index_temp = f"_{label_id}_index"
            counter_temp = f"_{label_id}_counter"

            # Cursed manual for loop in TIR
            stmts.extend(
                [
                    IRMove(IRTemp(index_temp), IRConst(0)),
                    IRMove(IRTemp(counter_temp), IRBinExpr("ADD", IRTemp(ref_temp), IRConst(4))),
                    IRLabel(cond_label),
                    IRCJump(
                        IRBinExpr("EQ", IRTemp(index_temp), IRTemp(size_temp)), IRName(false_label), None
                    ),  # for (i = 0; i < n)
                    IRMove(IRMem(IRTemp(counter_temp)), IRConst(0)),  # mem(c) = 0
                    IRMove(IRTemp(counter_temp), IRBinExpr("ADD", IRTemp(counter_temp), IRConst(4))),  # c += 4
                    IRMove(IRTemp(index_temp), IRBinExpr("ADD", IRTemp(index_temp), IRConst(1))),  # i++
                    IRJump(IRName(cond_label)),
                    IRLabel(false_label),
                ]
            )

            return IRESeq(IRSeq(stmts), IRBinExpr("ADD", IRTemp(ref_temp), IRConst(4)))

        case "char_l":
            return IRConst(tree.children[0].value)

        case _:
            log.info(f"{tree}")
            raise Exception(f"! Lower for {tree.data} not implemented {tree}")


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
                label_id = f"_{get_id()}"

                return IRSeq(
                    [
                        lower_c(left, context, IRName(label_id), false_label),
                        IRLabel(label_id),
                        lower_c(right, context, true_label, false_label),
                    ]
                )

            case "or_expr":
                left, right = [expr.children[i] for i in [0, -1]]
                label_id = f"_{get_id()}"

                return IRSeq(
                    [
                        lower_c(left, context, true_label, IRName(label_id)),
                        IRLabel(label_id),
                        lower_c(right, context, true_label, false_label),
                    ]
                )

            case "expr":
                return lower_c(expr.children[0], context, true_label, false_label)

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

            nested_context = context.child_map.get(f"{hash(tree)}", context)
            return IRSeq([lower_statement(child, nested_context) for child in tree.children])

        case "local_var_declaration":
            expr = next(tree.find_data("var_initializer")).children[0]
            var_name = get_tree_token(tree, "var_declarator_id", "IDENTIFIER")

            local_vars[var_name] = resolve_expression(expr, context)

            return IRMove(IRTemp(var_name), lower_expression(expr, context))

        case "if_st" | "if_st_no_short_if":
            _if_kw, cond, true_block = tree.children
            nested_context = context.child_map[f"{hash(tree)}"]
            label_id = get_id()

            true_label = f"_{label_id}_lt"
            false_label = f"_{label_id}_lf"

            return IRSeq(
                [
                    lower_c(cond, context, IRName(true_label), IRName(false_label)),
                    IRLabel(true_label),
                    lower_statement(true_block, nested_context),
                    IRLabel(false_label),
                ]
            )

        case "if_else_st" | "if_else_st_no_short_if":
            _if_kw, cond, true_block, _else_kw, false_block = tree.children
            nested_context = context.child_map[f"{hash(tree)}"]
            label_id = get_id()

            true_label = f"_{label_id}_lt"
            false_label = f"_{label_id}_lf"

            return IRSeq(
                [
                    lower_c(cond, context, IRName(true_label), IRName(false_label)),
                    IRLabel(true_label),
                    lower_statement(true_block, nested_context),
                    IRLabel(false_label),
                    lower_statement(false_block, nested_context),
                ]
            )

        case "while_st" | "while_st_no_short_if":
            _while_kw, cond, loop_body = tree.children
            nested_context = context.child_map[f"{hash(tree)}"]
            label_id = get_id()

            # Check for constant condition?

            cond_label = f"_{label_id}_cond"
            true_label = f"_{label_id}_lt"
            false_label = f"_{label_id}_lf"

            return IRSeq(
                [
                    IRLabel(cond_label),
                    lower_c(cond, context, IRName(true_label), IRName(false_label)),
                    IRLabel(true_label),
                    lower_statement(loop_body, nested_context),
                    IRJump(IRName(cond_label)),
                    IRLabel(false_label),
                ]
            )

        case "for_st" | "for_st_no_short_if":
            for_init, for_cond, for_update = [
                get_child_tree(tree, name) for name in ["for_init", "expr", "for_update"]
            ]
            loop_body = tree.children[-1]
            nested_context = context.child_map[f"{hash(tree)}"]
            label_id = get_id()

            # Check for constant condition?

            cond_label = f"_{label_id}_cond"
            true_label = f"_{label_id}_lt"
            false_label = f"_{label_id}_lf"

            return IRSeq(
                [
                    lower_statement(for_init, nested_context),
                    IRLabel(cond_label),
                    lower_c(for_cond, context, IRName(true_label), IRName(false_label)),
                    IRLabel(true_label),
                    lower_statement(loop_body, nested_context),
                    IRExp(lower_expression(for_update, nested_context)),
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
