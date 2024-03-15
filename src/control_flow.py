from __future__ import annotations

from lark import Token, Tree
from context import Context

from context import LocalVarDecl, Symbol
from helper import extract_name, get_child_tree, get_tree_token


class CFG_Node:
    next_nodes: list[CFG_Node]

    def __init__(self, defs, uses, next_nodes):
        self.defs = defs
        self.uses = uses
        self.next_nodes = next_nodes


def make_cfg(tree: Tree, context: Context, parent_node: CFG_Node | None = None) -> CFG_Node:
    match tree.data:
        case "block":
            for child in tree.children:
                node = CFG_Node([], [], [make_cfg(child, context)])

        case "local_var_declaration":
            expr = next(tree.find_data("var_initializer"), None).children[0]
            var_name = get_tree_token(tree, "var_declarator_id", "IDENTIFIER")

            assert isinstance(expr, Tree)

            (defs_expr, uses_expr) = decompose_expression(expr, context)
            return CFG_Node(defs_expr + [var_name], uses_expr, [])

        case "if_st" | "if_st_no_short_if":
            cond, true_block = tree.children
            (uses_cond, defs_cond) = decompose_expression(cond, context)

            # We need to get the if statement context
            CFG_Node(defs_cond, uses_cond, [make_cfg(true_block, context)])

        case "if_else_st" | "if_else_st_no_short_if":
            _if, cond, true_block, _else, false_block = tree.children

            (defs_cond, uses_cond) = decompose_expression(cond, context)

            # We need to get the if statement context
            return CFG_Node(defs_cond, uses_cond, [make_cfg(b, context) for b in [true_block, false_block]])

        case "while_st" | "while_st_no_short_if":
            _while, cond, true_block = tree.children

            (defs_cond, uses_cond) = decompose_expression(cond, context)

            cond_node = CFG_Node(defs_cond, uses_cond, None)
            nested_node = make_cfg(true_block, context, cond_node)
            cond_node.next_nodes = [nested_node]

            return cond_node

        case "for_st" | "for_st_no_short_if":
            for_init, for_cond, for_update = [decompose_expression(get_child_tree(tree, name), context) for name in ["for_init", "expr", "for_update"]]
            true_block = tree.children[-1]

            for_update_node = CFG_Node(for_update[0], for_update[1], None)
            for_cond_node = CFG_Node(for_cond[0], for_cond[1], make_cfg(true_block, context, for_update_node))
            for_init_node = CFG_Node(for_init[0], for_init[1], for_cond_node)
            for_update_node.next_nodes = [for_cond_node]

            return for_init_node

        case "expr_st":
            (defs_expr, uses_expr) = decompose_expression(tree.children[0], context)
            return CFG_Node(defs_expr, uses_expr, [])

        case "return_st":
            if len(tree.children) > 1:
                defs_expr, uses_expr = decompose_expression(tree.children[0], context)
            else:
                defs_expr, uses_expr = [[], []]

            return CFG_Node(defs_expr, uses_expr, [])


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