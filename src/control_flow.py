from lark import Token, Tree
from context import Context

from context import LocalVarDecl, Symbol
from helper import extract_name, get_child_tree, get_tree_token


class CFG_Node:
    def __init__(self, defs, uses, children):
        self.defs = defs
        self.uses = uses
        self.children = children


def make_cfg(tree: Tree, context: Context):
    match tree.data:
        case "local_var_declaration":
            expr = next(tree.find_data("var_initializer"), None).children[0]
            var_name = get_tree_token(tree, "var_declarator_id", "IDENTIFIER")

            assert isinstance(expr, Tree)

            (uses_expr, defs_expr) = decompose_expression(expr, context)
            CFG_Node(defs_expr + [var_name], uses_expr, [])

        case "if_st":
            expr = get_child_tree(tree, "expr")
            (uses_expr, defs_expr) = decompose_expression(expr, context)
            nested_stmts = tree.children[-1]

            # We need to get the if statement context
            CFG_Node(defs_expr, uses_expr, make_cfg(nested_stmts, context))


def get_argument_types(context: Context, tree: Tree) -> tuple[list[Symbol], list[Symbol]]:
    arg_lists = list(tree.find_data("argument_list"))
    defs = []
    uses = []
    if arg_lists:
        # get the last one, because find_data fetches bottom-up
        for c in arg_lists[-1].children:
            child_defs, child_uses = decompose_expression(c, context)
            defs += child_defs
            uses += child_uses
    return (defs, uses)


def resolve_refname(name: str, context: Context):
    refs = name.split(".")

    if len(refs) == 1:
        return context.resolve(LocalVarDecl, refs[-1])


def decompose_expression(tree: Tree, context: Context) -> tuple[list[Symbol], list[Symbol]]:
    match tree.data:
        case "expr":
            return decompose_expression(tree.children[0], context)

        case "class_instance_creation":
            return get_argument_types(context, tree)

        case "array_creation_expr":
            size_expr = next(tree.find_data("expr"))
            return decompose_expression(size_expr, context)

        case ("mult_expr" | "add_expr" | "sub_expr" | "rel_expr" | "eq_expr" |
              "eager_and_expr" | "eager_or_expr" | "and_expr" | "or_expr"):
            operands = [decompose_expression(c, context) for c in tree.children]

            defs_l, uses_l = operands[0]
            defs_r, uses_r = operands[-1]

            return (defs_l + defs_r, uses_l + uses_r)

        case "expression_name":
            return ([], [resolve_refname(extract_name(tree), context)])

        case "field_access":
            return decompose_expression(tree.children[0], context)

        case "method_invocation":
            if isinstance(tree.children[0], Tree) and tree.children[0].data == "method_name":
                return get_argument_types(context, tree)
            else:
                # lhs is expression
                defs_args, uses_args = get_argument_types(context, tree if len(tree.children) == 2 else tree.children[-1])

                defs_l, uses_l = decompose_expression(tree.children[0], context)
                return (defs_args + defs_l, uses_args + uses_l)

        case "unary_negative_expr"| "unary_complement_expr":
            return decompose_expression(tree.children[0], context)

        case "array_access":
            assert len(tree.children) == 2
            # array_type = decompose_expression(ref_array, context) # Don't think array type can have defs/uses

            return decompose_expression(tree.children[-1], context)

        case "cast_expr":
            cast_target = tree.children[-1]
            return decompose_expression(cast_target, context)

        case "assignment":
            lhs_tree = next(tree.find_data("lhs")).children[0]
            defs_l, uses_l = decompose_expression(lhs_tree, context)
            defs_r, uses_r = decompose_expression(tree.children[1], context)

            if lhs_tree.data == "expression_name":
                assert len(defs_l) == 0
                return (defs_l + defs_r + uses_l, uses_r)
            else:
                return (defs_l + defs_r, uses_l + uses_r)

        case _:
            return ([], [])