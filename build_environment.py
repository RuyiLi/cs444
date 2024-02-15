from lark import Token, Tree, ParseTree

from weeder import get_modifiers
from context import Context, ClassDecl, ConstructorDecl, FieldDecl, InterfaceDecl, LocalVarDecl, MethodDecl

def build_environment(tree: ParseTree, context: Context):
    for child in tree.children:
        if isinstance(child, Tree):
            parse_node(child, context)

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
                map(lambda e: get_nested_token(e, "IDENTIFIER"),
                    tree.find_pred(lambda c: c.data == "class_type")))

            implements = list(
                map(lambda e: get_nested_token(e, "IDENTIFIER"),
                    tree.find_pred(lambda c: c.data == "interface_type_list")))

            symbol = ClassDecl(context, class_name, modifiers, extends, implements)
            context.declare(symbol)

            nested_context = Context(context, symbol)
            context.children.append(nested_context)
            build_environment(next(tree.find_pred(lambda c: c.data == "class_body")), nested_context)

        case "interface_declaration":
            modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))
            class_name = get_nested_token(tree, "IDENTIFIER")

            extends = list(
                map(lambda e: get_nested_token(e, "IDENTIFIER"), tree.find_pred(lambda c: c.data == "class_type")))

            symbol = InterfaceDecl(context, class_name, modifiers, extends)
            context.declare(symbol)

            nested_context = Context(context, symbol)
            context.children.append(nested_context)
            build_environment(next(tree.find_pred(lambda c: c.data == "interface_body")), nested_context)

        case "constructor_declaration":
            modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))

            formal_params = next(tree.find_pred(lambda c: c.data == "formal_param_list"), None)
            if formal_params is not None:
                formal_param_types = list(map(lambda fp:
                    next(map(lambda t: next(t.scan_values(lambda v: isinstance(v, Token))), fp.find_pred(lambda c: c.data == "type")))
                , formal_params.children))
            else:
                formal_param_types = []

            symbol = ConstructorDecl(context, formal_param_types, modifiers)
            print("constructor_declaration", formal_param_types, modifiers)
            context.declare(symbol)

            if (nested_tree := next(tree.find_pred(lambda c: c.data == "block"), None)) is not None:
                nested_context = Context(context, symbol)
                context.children.append(nested_context)
                build_environment(nested_tree, nested_context)

        case "method_declaration":
            modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))
            method_name = get_nested_token(tree, "IDENTIFIER")

            formal_params = next(tree.find_pred(lambda c: c.data == "formal_param_list"), None)
            if formal_params is not None:
                formal_param_types = list(map(lambda fp:
                    next(map(lambda t: next(t.scan_values(lambda v: isinstance(v, Token))), fp.find_pred(lambda c: c.data == "type")))
                , formal_params.children))
            else:
                formal_param_types = []

            return_type = "void" if any(isinstance(x, Token) and x.type == "VOID_KW" for x in tree.children) else next(
                filter(lambda c: isinstance(c, Tree) and c.data == "type", tree.children)).children[0]

            symbol = MethodDecl(context, method_name, formal_param_types, modifiers, return_type)
            print("method_declaration", method_name, formal_param_types, modifiers, return_type)
            context.declare(symbol)

            if (nested_tree := next(tree.find_pred(lambda c: c.data == "block"), None)) is not None:
                nested_context = Context(context, symbol)
                context.children.append(nested_context)
                build_environment(nested_tree, nested_context)

        case "field_declaration":
            modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))
            field_type = get_tree_first_child(tree, "type")
            field_name = get_tree_token(tree, "var_declarator_id", "IDENTIFIER")

            print("field_declaration", field_name, modifiers, field_type)

            context.declare(FieldDecl(context, field_name, modifiers, field_type))

        case "local_var_declaration":
            var_type = get_tree_first_child(tree, "type")
            var_name = get_tree_token(tree, "var_declarator_id", "IDENTIFIER")

            print("local_var_declaration", var_name, var_type)

            context.declare(LocalVarDecl(context, var_name, var_type))

        case _:
            build_environment(tree, context)
