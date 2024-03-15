import warnings

from context import GlobalContext, SemanticError
from control_flow import CFGNode, make_cfg
from helper import extract_name
from lark import Tree


def analyze_reachability(context: GlobalContext):
    for child_context in context.children:
        tree = child_context.tree
        class_name = next(tree.find_data("constructor_declaration"), None)
        if class_name:
            class_name = extract_name(class_name.children[1])
        method_body = tree.find_data("method_body")
        print("=" * 20)
        print(class_name)
        print("=" * 20)
        for body in method_body:
            if isinstance(body.children[0], Tree):
                # only check methods with implementations
                cfg_root = CFGNode("root_node", set(), set())
                make_cfg(body.children[0], context, cfg_root)
                print(cfg_root)
                print("=" * 10)


def iterative_solving(start: CFGNode):
    changed = True

    while changed:
        changed = False
        to_visit = [start]
        visited = set()

        while len(to_visit) > 0:
            curr = to_visit.pop()
            visited.add(curr)

            old_in_vars, old_out_vars = curr.in_vars, curr.out_vars
            curr.in_vars, curr.out_vars = set(), set()

            for next_n in curr.next_nodes:
                curr.out_vars.union(next_n.in_vars)

                if next_n not in visited:
                    to_visit.append(next_n)

            curr.in_vars = curr.uses | (curr.out_vars - curr.defs)

            if curr.in_vars != old_in_vars or curr.out_vars != old_out_vars:
                changed = True


def check_dead_code_assignment(start: CFGNode):
    to_visit = [start]
    visited = set()

    while len(to_visit) > 0:
        curr = to_visit.pop()
        visited.add(curr)

        if dead_assignment := next((next_n not in curr.out_vars for next_n in curr.defs), None):
            warnings.warn(f"dead code assignment to variable {dead_assignment}")

        for next_n in curr.next_nodes:
            if next_n not in visited:
                to_visit.append(next_n)
