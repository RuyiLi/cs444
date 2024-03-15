from control_flow import make_cfg
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
