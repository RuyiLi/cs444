from tir import IRExpr, IRBinExpr, IRCall, IRCJump, IRConst, IRExp, IRJump, IRLabel, IRMove, IRESeq, IRName, IRReturn, IRSeq, IRStmt, IRTemp
from lark import Token, Tree
from context import Context
from helper import extract_name, get_child_tree, get_tree_token
from type_check import resolve_expression
from typing import List

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
            op_type = tree.data[:-5].upper() if len(tree.children) == 2 else tree.children[1].value
            return IRBinExpr(op_type, left, right)

        case "and_expr":
            left, right = [tree.children[i] for i in [0, -1]]

            return IRESeq(IRSeq([
                IRMove(IRTemp("t"), IRConst(0)),
                IRCJump(lower_expression(left, context), f"{id(tree)}_lt", f"{id(tree)}_lf"),
                IRLabel(f"{id(tree)}_lt"), IRMove(IRTemp("t"), lower_expression(right, context)),
                IRLabel(f"{id(tree)}_lf")
            ]), IRTemp("t"))

        case "or_expr":
            left, right = [tree.children[i] for i in [0, -1]]

            return IRESeq(IRSeq([
                IRMove(IRTemp("t"), IRConst(0)),
                IRCJump(lower_expression(left, context), f"{id(tree)}_lt", f"{id(tree)}_lf"),
                IRLabel(f"{id(tree)}_lt"), IRMove(IRTemp("t"), IRConst(1)),
                IRLabel(f"{id(tree)}_lf"), IRMove(IRTemp("t"), lower_expression(right, context)),
            ]), IRTemp("t"))

        case "expression_name":
            name = extract_name(tree)
            return IRTemp(name) # if context.resolve(LocalVarDecl, name)

        # case "field_access":
        #     return lower_expression(tree.children[0], context)

        case "method_invocation":
            if isinstance(tree.children[0], Tree) and tree.children[0].data == "method_name":
                args = get_arguments(context, tree)

                return IRCall(IRName(extract_name(tree)), args)

            # lhs is expression
            args = get_arguments(context, tree if len(tree.children) == 2 else tree.children[-1])
            expr_type = resolve_expression(tree.children[0], context)

            return IRCall(IRName(f"java.lang.{expr_type.name.capitalize()}.{extract_name(tree)}"), args)

        case "unary_negative_expr":
            return IRBinExpr("MULT", IRConst(-1), lower_expression(tree.children[0], context))

        case "unary_complement_expr":
            return IRBinExpr("SUB", IRConst(1), lower_expression(tree.children[0], context))

        case "assignment":
            lhs_tree = next(tree.find_data("lhs")).children[0]
            lhs = lower_expression(lhs_tree, context)
            rhs = lower_expression(tree.children[1], context)

            return IRESeq(IRMove(lhs, rhs), lhs)

        case "cast_expr":
            cast_target = tree.children[-1]
            # We might need to do some conversions?
            return lower_expression(cast_target, context)

        case "for_update":
            return lower_expression(tree.children[0], context)

        ### TO BE IMPLEMENTED:

        case "array_access":
            assert len(tree.children) == 2
            # array_type = lower_expression(ref_array, context) # Don't think array type can have defs/uses

            return lower_expression(tree.children[-1], context)

        case _:
            raise Exception(f"! Lower for {tree.data} not implemented")


def lower_c(expr: Tree | Token, context: Context, true_label: str, false_label: str) -> IRStmt:
    if isinstance(expr, Token):
        if expr == "true":
            return IRJump(IRName(true_label))
        if expr == "false":
            return IRJump(IRName(false_label))
    else:
        match expr.data:
            case "unary_complement_expr":
                return lower_c(expr.children[0], context, false_label, true_label)

            case "and_expr":
                left, right = [expr.children[i] for i in [0, -1]]

                return IRSeq([
                    lower_c(left, context, str(id(expr)), false_label),
                    IRLabel(str(id(expr))), lower_c(right, context, true_label, false_label)
                ])

            case "or_expr":
                left, right = [expr.children[i] for i in [0, -1]]

                return IRSeq([
                    lower_c(left, context, true_label, str(id(expr))),
                    IRLabel(str(id(expr))), lower_c(right, context, true_label, false_label)
                ])

    return IRCJump(lower_expression(expr, context), true_label, false_label)


def lower_statement(tree: Tree, context: Context) -> IRStmt:
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

            true_label = f"{id(tree)}_lt"
            false_label = f"{id(tree)}_lf"

            return IRSeq([
                lower_c(cond, context, true_label, false_label),
                IRLabel(true_label), lower_statement(true_block, context),
                IRLabel(false_label)
            ])

        case "if_else_st" | "if_else_st_no_short_if":
            _if_kw, cond, true_block, _else_kw, false_block = tree.children

            true_label = f"{id(tree)}_lt"
            false_label = f"{id(tree)}_lf"

            return IRSeq([
                lower_c(cond, context, true_label, false_label),
                IRLabel(true_label), lower_statement(true_block, context),
                IRLabel(false_label), lower_statement(false_block, context)
            ])

        case "while_st" | "while_st_no_short_if":
            _while_kw, cond, loop_body = tree.children

            # Check for constant condition?

            cond_label = f"{id(tree)}_cond"
            true_label = f"{id(tree)}_lt"
            false_label = f"{id(tree)}_lf"

            return IRSeq([
                IRLabel(cond_label), lower_c(cond, context, true_label, false_label),
                IRLabel(true_label), lower_statement(loop_body, context), IRJump(IRName(cond_label)),
                IRLabel(false_label)
            ])

        case "for_st" | "for_st_no_short_if":
            for_init, for_cond, for_update = [get_child_tree(tree, name) for name in ["for_init", "expr", "for_update"]]
            loop_body = tree.children[-1]

            # Check for constant condition?

            cond_label = f"{id(tree)}_cond"
            true_label = f"{id(tree)}_lt"
            false_label = f"{id(tree)}_lf"

            return IRSeq([
                lower_statement(for_init, context),
                IRLabel(cond_label), lower_c(for_cond, context, true_label, false_label),
                IRLabel(true_label), lower_statement(loop_body, context), IRExp(lower_expression(for_update, context)), IRJump(IRName(cond_label)),
                IRLabel(false_label)
            ])

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
            return lower_statement(child, context) if child.data == "local_var_declaration" else IRExp(lower_expression(child, context))

        case _:
            raise Exception(f"! lower_statement for {tree.data} not implemented")
