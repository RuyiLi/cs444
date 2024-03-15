from control_flow import CFGNode, make_cfg,
from context import GlobalContext
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
                cfg = make_cfg(body.children[0], context)
                print(cfg)
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
