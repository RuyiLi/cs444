from lark import Token, Tree, ParseTree

from weeder import get_modifiers
from context import Context, ClassDecl, FieldDecl, InterfaceDecl, LocalVarDecl

def build_environment(tree: ParseTree, context: Context):
    for child in tree.children:
        if isinstance(child, Tree):
            if (symbol := parse_node(child, context)):
                context.declare(symbol)
            
            if child.data in ['class_body', 'block']:
                nested_context = Context(context)
                context.children.append(nested_context)
                build_environment(child, nested_context)
            else:
                build_environment(child, context)

def get_tree_first_child(tree: ParseTree, name: str):
    return next(tree.find_pred(lambda c: c.data == name)).children[0]

def get_nested_token(tree: ParseTree, name: str):
    return next(tree.scan_values(lambda v: isinstance(v, Token) and v.type == name)).value

def get_tree_token(tree: ParseTree, tree_name: str, token_name: str):
    return get_nested_token(next(tree.find_pred(lambda c: c.data == tree_name)), token_name)

def parse_node(tree: ParseTree, context: Context):
    match tree.data:
        case "class_declaration":
            modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))
            class_name = get_nested_token(tree, "IDENTIFIER")

            extends = list(
                map(lambda e: get_nested_token(e, "IDENTIFIER").value,
                    tree.find_pred(lambda c: c.data == "class_type")))

            implements = list(
                map(lambda e: get_nested_token(e, "IDENTIFIER").value,
                    tree.find_pred(lambda c: c.data == "interface_type_list")))

            return ClassDecl(context, class_name, modifiers, extends, implements)
        case "interface_declaration":
            modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))
            class_name = get_nested_token(tree, "IDENTIFIER")

            extends = list(
                map(lambda e: get_nested_token(e, "IDENTIFIER").value,
                    tree.find_pred(lambda c: c.data == "class_type")))

            return InterfaceDecl(context, class_name, modifiers, extends)
        case "field_declaration":
            modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))
            field_type = get_tree_first_child(tree, "type")
            field_name = get_tree_token(tree, "var_declarator_id", "IDENTIFIER")

            return FieldDecl(context, field_name, modifiers, field_type)
        case "local_var_declaration":
            print(tree.children)
            var_type = get_tree_first_child(tree, "type")
            var_name = get_tree_token(tree, "var_declarator_id", "IDENTIFIER")

            return LocalVarDecl(context, var_name, var_type)
        case _:
            pass
