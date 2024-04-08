import logging
import warnings

from context import GlobalContext, SemanticError
from control_flow import CFGNode, make_cfg
from helper import extract_name, get_return_type
from lark import Tree
log = logging.getLogger(__name__)


def analyze_reachability(context: GlobalContext):
    for child_context in context.children:
        tree = child_context.tree

        class_name = next(tree.find_data("constructor_declaration"), None)
        if class_name is not None:
            class_name = extract_name(class_name.children[1])
            log.debug(f"Analyzing reachability for {class_name}")

        method_decls = tree.find_data("method_declaration")
        for method_decl in method_decls:
            return_type = get_return_type(method_decl)
            if method_body := next(method_decl.find_data("method_body"), None):
                check_tree_reachability(method_body, return_type != "void")

        constructors = tree.find_data("constructor_declaration")
        for ctor in constructors:
            body = ctor.children[-1]
            check_tree_reachability(body)


def check_tree_reachability(tree: Tree, check_return=False):
    if tree.children and isinstance(tree.children[0], Tree):
        cfg_root = make_cfg(tree.children[0], tree.context)[0]
        log.debug(cfg_root)
        iterative_solving(cfg_root)
        check_dead_code_assignment(cfg_root)
        check_unreachable(cfg_root)

        if check_return:
            check_returns(cfg_root)


def get_terminals(root: CFGNode):
    terminals = []
    to_visit = [root]
    visited = set()

    while len(to_visit) > 0:
        curr = to_visit.pop()
        visited.add(curr)

        if len(curr.next_nodes) == 0:
            terminals.append(curr)
            continue

        to_visit += [next_n for next_n in curr.next_nodes if next_n not in visited]

    return terminals


def iterative_solving(start: CFGNode):
    changed = True

    while changed:
        changed = False
        to_visit = [start]
        visited = set()

        while len(to_visit) > 0:
            curr = to_visit.pop()
            visited.add(curr)

            old_in_vars, old_out_vars = curr.in_vars.copy(), curr.out_vars.copy()
            curr.in_vars, curr.out_vars = set(), set()

            for next_n in curr.next_nodes:
                curr.out_vars = curr.out_vars.union(next_n.in_vars)

                if next_n not in visited:
                    to_visit.append(next_n)

            curr.in_vars = curr.uses | (curr.out_vars - curr.defs)

            if (curr.in_vars != old_in_vars) or (curr.out_vars != old_out_vars):
                changed = True


def check_dead_code_assignment(start: CFGNode):
    to_visit = [start]
    visited = set()

    while len(to_visit) > 0:
        curr = to_visit.pop()
        visited.add(curr)

        dead_assignment = next((next_n for next_n in curr.defs if next_n not in curr.out_vars), None)
        if curr.type != "local_var_declaration" and dead_assignment:
            warnings.warn(f"dead code assignment to variable '{dead_assignment}'")

        for next_n in curr.next_nodes:
            if next_n not in visited:
                to_visit.append(next_n)


def check_unreachable(start: CFGNode):
    to_visit = [start]
    visited = set()

    while len(to_visit) > 0:
        curr = to_visit.pop()
        visited.add(curr)

        if curr.type == "return_st":
            continue

        for next_n in curr.next_nodes:
            if next_n not in visited:
                to_visit.append(next_n)

    # Traverse again
    to_visit = [start]
    new_visited = set()

    while len(to_visit) > 0:
        curr = to_visit.pop()
        new_visited.add(curr)

        if curr not in visited:
            raise SemanticError(f"unreachable statement {curr.type}")

        for next_n in curr.next_nodes:
            if next_n not in new_visited:
                to_visit.append(next_n)


def check_returns(start: CFGNode):
    to_visit = [start]
    visited = set()

    while len(to_visit) > 0:
        curr = to_visit.pop()
        visited.add(curr)

        if len(curr.next_nodes) == 0 and curr.type != "return_st":
            raise SemanticError("finite-length non-void terminates without return")

        for next_n in curr.next_nodes:
            if next_n not in visited:
                to_visit.append(next_n)
