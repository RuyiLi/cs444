from __future__ import annotations

import logging
from typing import List, Set, Tuple

from context import Context, FieldDecl, LocalVarDecl, SemanticError, Symbol
from helper import extract_name, get_child_tree, get_tree_token, is_static_context
from joos_types import is_numeric_type
from lark import Token, Tree
from type_check import resolve_token


class CFGNode:
    in_vars: Set[str]
    out_vars: Set[str]

    def __init__(self, type: str, defs: Set[str], uses: Set[str], next_nodes: List[CFGNode] | None = None):
        self.type = type
        self.defs = defs
        self.uses = uses
        self.next_nodes = next_nodes or []
        self.in_vars = set()
        self.out_vars = set()

    def pretty(self, visited, depth=0):
        ret = "  " * depth + repr(self) + "\n"
        if self in visited:
            return ret
        for node in self.next_nodes:
            ret += node.pretty(visited | {self}, depth + 1)
        return ret

    def __repr__(self):
        return f"CFGNode(type={self.type}, defs={self.defs or ''}, uses={self.uses or ''}, successors={len(self.next_nodes)})"

    def __str__(self):
        return self.pretty(set())


def resolve_const_expr(expr: Tree | Token):
    if isinstance(expr, Token):
        expr_type = resolve_token(expr, None)

        if is_numeric_type(expr_type):
            return int(expr.value)
        elif expr_type.name == "boolean":
            return expr.value == "true"
        else:
            return expr.value

    match expr.data:
        case "mult_expr":
            lhs, rhs = [resolve_const_expr(expr.children[i]) for i in [0, -1]]
            return lhs * rhs

        case "add_expr":
            lhs, rhs = [resolve_const_expr(expr.children[i]) for i in [0, -1]]
            return lhs + rhs

        case "rel_expr" | "eq_expr":
            lhs, rhs = [resolve_const_expr(expr.children[i]) for i in [0, -1]]
            op = expr.children[1]
            return eval(f"{lhs} {op} {rhs}")

        case "or_expr" | "and_expr" | "eager_or_expr" | "eager_and_expr":
            lhs, rhs = [resolve_const_expr(expr.children[i]) for i in [0, -1]]
            match expr.children[1]:
                case "||" | "|":
                    op = "or"
                case "&&" | "&":
                    op = "and"
            return eval(f"{lhs} {op} {rhs}")

        case "expr":
            return resolve_const_expr(expr.children[0])


def make_cfg(tree: Tree, context: Context) -> tuple[CFGNode, List[CFGNode], bool]:
    """
    Returns the CFGNode corresponding to the given tree.
    Mutates parent_node.
    """

    if isinstance(tree, Token):
        raise Exception("This shouldn't happen. CFG token encountered:", tree.value)

    match tree.data:
        case "block":
            if len(tree.children) == 0:
                empty_node = CFGNode("empty_st", set(), set(), [])
                return (empty_node, [empty_node], False)

            child_nodes_terminals = [make_cfg(child, context) for child in tree.children]

            for i in range(0, len(child_nodes_terminals) - 1):
                _, l_terminals, non_terminal = child_nodes_terminals[i]
                r_node, _, _ = child_nodes_terminals[i + 1]

                if non_terminal:
                    raise SemanticError("unreachable code after non-terminal loop")

                for terminal in l_terminals:
                    terminal.next_nodes.append(r_node)

            return (child_nodes_terminals[0][0], child_nodes_terminals[-1][1], False)

        case "local_var_declaration":
            expr = next(tree.find_data("var_initializer")).children[0]
            var_name = get_tree_token(tree, "var_declarator_id", "IDENTIFIER")

            assert isinstance(expr, Tree)

            defs_expr, uses_expr = decompose_expression(expr, context)
            for uses in uses_expr:
                if uses == var_name:
                    sym = context.resolve(FieldDecl, uses)
                    if sym and is_static_context(context):
                        raise SemanticError(f"Self-assignment to variable {var_name}")

            var_node = CFGNode(tree.data, defs_expr | {var_name}, uses_expr)
            return (var_node, [var_node], False)

        case "if_st" | "if_st_no_short_if":
            _if_kw, cond, true_block = tree.children
            defs_cond, uses_cond = decompose_expression(cond, context)

            # We need to get the if statement context
            if_node = CFGNode(tree.data, defs_cond, uses_cond)
            true_node, true_terminals, _ = make_cfg(true_block, context)

            if_terminal = CFGNode("empty_st", set(), set(), [])
            if_node.next_nodes = [true_node, if_terminal]

            for terminal in true_terminals:
                terminal.next_nodes.append(if_terminal)

            return (if_node, [if_terminal], False)

        case "if_else_st" | "if_else_st_no_short_if":
            # the way that these currently work is that if/else nodes have three children
            # the first is the true block, second is false, third is everything after

            _if_kw, cond, true_block, _else_kw, false_block = tree.children
            defs_cond, uses_cond = decompose_expression(cond, context)

            # We need to get the if statement context
            if_else_node = CFGNode(tree.data, defs_cond, uses_cond)
            true_node, true_terminals, true_non_terminal = make_cfg(true_block, context)
            false_node, false_terminals, false_non_terminal = make_cfg(false_block, context)

            if_else_node.next_nodes = [true_node, false_node]
            return (if_else_node, true_terminals + false_terminals, true_non_terminal and false_non_terminal)

        case "while_st" | "while_st_no_short_if":
            _while_kw, cond, loop_body = tree.children
            defs_cond, uses_cond = decompose_expression(cond, context)

            cond_node = CFGNode(tree.data, defs_cond, uses_cond)
            true_node, true_terminals, _ = make_cfg(loop_body, context)
            cond_node.next_nodes = [true_node]

            for terminal in true_terminals:
                terminal.next_nodes.append(cond_node)

            non_terminal = False

            # Constant expression
            if (cond_tree := get_child_tree(tree, "expr")) and len(list(cond_tree.find_data("name"))) == 0:
                const_expr_result = resolve_const_expr(get_child_tree(tree, "expr"))
                if const_expr_result is True:
                    non_terminal = True

                if const_expr_result is False:
                    raise SemanticError("Statements found inside false while loop")

            return (cond_node, [cond_node], non_terminal)

        case "for_st" | "for_st_no_short_if":
            for_init, for_cond, for_update = (
                decompose_expression(get_child_tree(tree, name), getattr(tree, "context", context))
                for name in ["for_init", "expr", "for_update"]
            )
            loop_body = tree.children[-1]

            # for_init
            #   for_cond
            #     loop_body
            #     for_update
            #       for_cond   # circular reference
            #   rest_of_program

            loop_body_node, loop_body_terminals, _ = make_cfg(loop_body, context)

            non_terminal = False

            # Constant expression
            if (cond_tree := get_child_tree(tree, "expr")) and len(list(cond_tree.find_data("name"))) == 0:
                const_expr_result = resolve_const_expr(get_child_tree(tree, "expr"))
                if const_expr_result is True:
                    non_terminal = True

                if const_expr_result is False:
                    raise SemanticError("Statements found inside false for loop")

            for_cond_node = CFGNode(tree.data + "_cond", for_cond[0], for_cond[1], [loop_body_node])
            for_init_node = CFGNode(tree.data + "_init", for_init[0], for_init[1], [for_cond_node])
            for_update_node = CFGNode(tree.data + "_update", for_update[0], for_update[1], [for_cond_node])

            for terminal in loop_body_terminals:
                terminal.next_nodes.append(for_update_node)

            return (for_init_node, [for_cond_node], non_terminal)

        case "expr_st":
            # assignment | method_invocation | class_instance_creation
            defs_expr, uses_expr = decompose_expression(tree.children[0], context)
            expr_node = CFGNode(tree.data, defs_expr, uses_expr)
            return (expr_node, [expr_node], False)

        case "return_st":
            defs_expr, uses_expr = set(), set()
            if len(tree.children) > 1:
                defs_expr, uses_expr = decompose_expression(tree.children[1], context)
            return_node = CFGNode(tree.data, defs_expr, uses_expr)
            return (return_node, [return_node], False)

        case "statement" | "statement_no_short_if":
            return make_cfg(tree.children[0], context)

        case "empty_st":
            empty_node = CFGNode("empty_st", set(), set(), [])
            return (empty_node, [empty_node], False)

        case _:
            raise Exception(f"! CFG for {tree.data} not implemented")


def get_argument_types(context: Context, tree: Tree) -> Tuple[Set[Symbol], Set[Symbol]]:
    arg_lists = list(tree.find_data("argument_list"))
    defs = set()
    uses = set()
    if arg_lists:
        # get the last one, because find_data fetches bottom-up
        for c in arg_lists[-1].children:
            child_defs, child_uses = decompose_expression(c, context)
            defs |= child_defs
            uses |= child_uses
    return (defs, uses)


def resolve_refname(name: str, context: Context):
    refs = name.split(".")
    if len(refs) == 1:
        return context.resolve(LocalVarDecl, refs[-1])


def decompose_expression(tree: Tree, context: Context) -> Tuple[Set[str], Set[str]]:
    """
    returns (defs, uses)
    """

    if tree is None or isinstance(tree, Token):
        return (set(), set())

    match tree.data:
        case "expr":
            return decompose_expression(tree.children[0], context)

        case "class_instance_creation":
            return get_argument_types(context, tree)

        case "array_creation_expr":
            size_expr = next(tree.find_data("expr"))
            return decompose_expression(size_expr, context)

        case (
            "mult_expr"
            | "add_expr"
            | "sub_expr"
            | "rel_expr"
            | "eq_expr"
            | "eager_and_expr"
            | "eager_or_expr"
            | "and_expr"
            | "or_expr"
        ):
            assert len(tree.children) == 2 or len(tree.children) == 3
            defs_l, uses_l = decompose_expression(tree.children[0], context)
            defs_r, uses_r = decompose_expression(tree.children[-1], context)
            return (defs_l | defs_r, uses_l | uses_r)

        case "expression_name":
            name = extract_name(tree)
            return (set(), {name} if context.resolve(LocalVarDecl, name) else set())

        case "field_access":
            return decompose_expression(tree.children[0], context)

        case "method_invocation":
            if isinstance(tree.children[0], Tree) and tree.children[0].data == "method_name":
                return get_argument_types(context, tree)
            else:
                # lhs is expression
                defs_args, uses_args = get_argument_types(
                    context, tree if len(tree.children) == 2 else tree.children[-1]
                )

                defs_l, uses_l = decompose_expression(tree.children[0], context)
                return (defs_args | defs_l, uses_args | uses_l)

        case "unary_negative_expr" | "unary_complement_expr":
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
                return (defs_l | defs_r | uses_l, uses_r)
            else:
                return (defs_l | defs_r, uses_l | uses_r)

        case "for_init":
            child = tree.children[0]
            if child.data == "local_var_declaration":
                var_declarator = next(tree.find_data("var_declarator_id"))
                var_initializer = next(tree.find_data("var_initializer"))
                var_name = extract_name(var_declarator)
                defs, uses = decompose_expression(var_initializer.children[0], context)
                return ({var_name}, defs | uses)

            # assert child.data == "assignment"
            return decompose_expression(child, context)

        case "for_update":
            return decompose_expression(tree.children[0], context)

        case "string_l" | "char_l" | "type_name":
            return (set(), set())

        case _:
            logging.info(f"! Decompose for {tree.data} not implemented")
            return (set(), set())
