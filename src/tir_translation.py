from tir import IRExpr, IRBinExpr, IRCall, IRCJump, IRConst, IRLabel, IRMove, IRESeq, IRName, IRSeq, IRTemp
from lark import Token, Tree
from context import Context
from helper import extract_name
from type_check import resolve_expression

def lower_token(token: Token):
    match token.type:
        case "INTEGER_L" | "char_l" | "NULL":
            return IRConst(token.value)
        case "BOOLEAN_L":
            return IRConst(1 if token.value == "true" else 0)
        case "string_l":
            raise Exception("strings are objects")


def get_arguments(context: Context, tree: Tree) -> Tuple[Set[Symbol], Set[Symbol]]:
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
                IRMove(IRTemp("t"), 0),
                IRCJump(lower_expression(left, context), f"{tree.id()}_lt", f"{tree.id()}_lf"),
                IRLabel(f"{tree.id()}_lt"), IRMove(IRTemp("t", lower_expression(right, context))),
                IRLabel(f"{tree.id()}_lf")
            ]), IRTemp("t"))

        case "or_expr":
            left, right = [tree.children[i] for i in [0, -1]]

            return IRESeq(IRSeq([
                IRMove(IRTemp("t"), 0),
                IRCJump(lower_expression(left, context), f"{tree.id()}_lt", f"{tree.id()}_lf"),
                IRLabel(f"{tree.id()}_lt"), IRMove(IRTemp("t", 1)),
                IRLabel(f"{tree.id()}_lf"), IRMove(IRTemp("t", lower_expression(right, context))),
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

            return IRCall(IRName(f"java.lang.{expr_type.capitalize()}.{extract_name(tree)}", args))

        case "unary_negative_expr":
            return IRBinExpr("MULT", IRConst(-1), lower_expression(tree.children[0], context))

        case "unary_complement_expr":
            return IRBinExpr("SUB", IRConst(1), lower_expression(tree.children[0], context))

        ### TO BE IMPLEMENTED:

        case "array_access":
            assert len(tree.children) == 2
            # array_type = lower_expression(ref_array, context) # Don't think array type can have defs/uses

            return lower_expression(tree.children[-1], context)

        case "cast_expr":
            cast_target = tree.children[-1]
            return lower_expression(cast_target, context)

        case "assignment":
            lhs_tree = next(tree.find_data("lhs")).children[0]
            defs_l, uses_l = lower_expression(lhs_tree, context)
            defs_r, uses_r = lower_expression(tree.children[1], context)

            if lhs_tree.data == "expression_name":
                assert len(defs_l) == 0
                return (defs_l | defs_r | uses_l, uses_r)
            else:
                return (defs_l | defs_r, uses_l | uses_r)

        case "for_init":
            child = tree.children[0]
            if child.data == "local_var_declaration":
                var_declarator = next(tree.find_data("var_declarator_id"))
                var_initializer = next(tree.find_data("var_initializer"))
                var_name = extract_name(var_declarator)
                defs, uses = lower_expression(var_initializer.children[0], context)
                return ({var_name}, defs | uses)

            # assert child.data == "assignment"
            return lower_expression(child, context)

        case "for_update":
            return lower_expression(tree.children[0], context)

        case _:
            print(f"! Lower for {tree.data} not implemented")
            return (set(), set())
