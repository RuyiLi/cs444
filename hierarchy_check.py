from lark import Token, Tree, ParseTree

from weeder import get_modifiers
from context import Context, ClassDecl, LocalVarDecl

def hierarchy_check(tree: ParseTree, context: Context = Context()):
    for child in tree.children:
        if isinstance(child, Tree):
            if (symbol := parse_node(child, context)):
                context.declare(symbol)

            nested_context = child.data in ['class_body', 'block']
            hierarchy_check(child, Context(context) if nested_context else context)

def parse_node(tree: ParseTree, context: Context):
    match tree.data:
        case "class_declaration":
            modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))
            class_name = next(filter(lambda c: isinstance(c, Token) and c.type == "IDENTIFIER", tree.children))

            extends = list(
                map(lambda e: next(e.scan_values(lambda v: isinstance(v, Token) and v.type == "IDENTIFIER")).value,
                    filter(lambda c: isinstance(c, Tree) and c.data == "class_type",
                    tree.children)))

            implements = list(
                map(lambda e: next(e.scan_values(lambda v: isinstance(v, Token) and v.type == "IDENTIFIER")).value,
                    filter(lambda c: isinstance(c, Tree) and c.data == "interface_type_list",
                    tree.children)))

            return ClassDecl(context, class_name, modifiers, extends, implements)
        case "local_var_declaration":
            var_type = next(filter(lambda c: isinstance(c, Tree) and c.data == "type", tree.children)).children[0]
            var_name = next(tree.scan_values(lambda v: isinstance(v, Token) and v.type == "IDENTIFIER")).value
            return LocalVarDecl(context, var_name, var_type)
        case _:
            pass
