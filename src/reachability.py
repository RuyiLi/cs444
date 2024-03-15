from control_flow import make_cfg
from context import GlobalContext

from lark import Tree


def analyze_reachability(context: GlobalContext):
    for child_context in context.children:
        tree = child_context.tree
        method_body = tree.find_data("method_body")
        for body in method_body:
            if isinstance(body.children[0], Tree):
                cfg = make_cfg(body.children[0], context)
                print(cfg)
