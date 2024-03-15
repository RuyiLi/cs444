import logging
import warnings

from context import GlobalContext, SemanticError
from control_flow import CFGNode, make_cfg
from helper import extract_name
from lark import Tree


def analyze_reachability(context: GlobalContext):
    for child_context in context.children:
        tree = child_context.tree

        class_name = next(tree.find_data("constructor_declaration"), None)
        if class_name is not None:
            class_name = extract_name(class_name.children[1])
            logging.debug(f"Analyzing reachability for {class_name}")

        method_bodies = tree.find_data("method_body")
        for body in method_bodies:
            check_tree_reachability(body)

        constructors = tree.find_data("constructor_declaration")
        for ctor in constructors:
            body = ctor.children[-1]
            check_tree_reachability(body)


def check_tree_reachability(tree: Tree):
    if tree.children and isinstance(tree.children[0], Tree):
        cfg_root = CFGNode("root_node", set(), set())
        print("--------------")
        make_cfg(tree.children[0], tree.context, cfg_root)
        fix_if_links(cfg_root)
        logging.debug(cfg_root)
        iterative_solving(cfg_root)
        check_dead_code_assignment(cfg_root)


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


def fix_if_links(root: CFGNode):
    to_visit = [root]
    visited = set()

    while len(to_visit) > 0:
        curr = to_visit.pop()
        visited.add(curr)

        if curr.type[:2] == "if":
            after_stmts = curr.next_nodes.pop()

            for next_n in curr.next_nodes:
                for terminal in get_terminals(next_n):
                    terminal.next_nodes.append(after_stmts)

        for next_n in curr.next_nodes:
            to_visit.append(next_n)


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

            print(curr.type, "old_in", old_in_vars, "old_out", old_out_vars, "in", curr.in_vars, "out", curr.out_vars, "defs", curr.defs, "uses", curr.uses)
            print([next_n.__str__() for next_n in curr.next_nodes])

            if (curr.in_vars != old_in_vars) or (curr.out_vars != old_out_vars):
                changed = True

        if changed:
            print('CHANGED!')


def check_dead_code_assignment(start: CFGNode):
    print('checking ~~~~~~~~')
    print(start)
    to_visit = [start]
    visited = set()

    while len(to_visit) > 0:
        curr = to_visit.pop()
        visited.add(curr)

        print(f"{curr.type}, defs={curr.defs}, out={curr.out_vars}")

        dead_assignment = next((next_n for next_n in curr.defs if next_n not in curr.out_vars), None)
        if dead_assignment:
            raise SemanticError(f"dead code assignment to variable '{dead_assignment}'")
            #warnings.warn(f"dead code assignment to variable {dead_assignment}")

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
            warnings.warn(f"unreachable statement {curr.type}")

        for next_n in curr.next_nodes:
            if next_n not in new_visited:
                to_visit.append(next_n)
