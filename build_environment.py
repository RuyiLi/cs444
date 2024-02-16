import logging

from lark import Token, Tree, ParseTree
from weeder import get_modifiers
from context import (
    Context,
    ClassDecl,
    ConstructorDecl,
    FieldDecl,
    InterfaceDecl,
    LocalVarDecl,
    MethodDecl,
    OnDemandImport,
    SingleImport,
)


def build_environment(tree: ParseTree, context: Context):
    if tree.data == "compilation_unit":
        parse_node(tree, context)
        return

    for child in tree.children:
        if isinstance(child, Tree):
            parse_node(child, context)


def get_tree_first_child(tree: ParseTree, name: str):
    return next(tree.find_pred(lambda c: c.data == name)).children[0]

def get_child_token(tree: ParseTree, name: str) -> str:
    return next(filter(lambda c: isinstance(c, Token) and c.type == name, tree.children)).value

def get_nested_token(tree: ParseTree, name: str) -> str:
    return next(tree.scan_values(lambda v: isinstance(v, Token) and v.type == name)).value

def get_tree_token(tree: ParseTree, tree_name: str, token_name: str):
    return get_nested_token(next(tree.find_pred(lambda c: c.data == tree_name)), token_name)

def get_tree_child_token(tree: ParseTree, tree_name: str, token_name: str):
    return get_child_token(
        next(tree.find_pred(lambda c: c.data == tree_name)), token_name
    )

def get_identifiers(tree: ParseTree):
    return (token.value for token in tree.scan_values(lambda v: v.type == "IDENTIFIER"))


def build_interface_declaration(tree: ParseTree, context: Context, package_prefix: str):
    assert tree.data == "interface_declaration"
    modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))
    class_name = get_nested_token(tree, "IDENTIFIER")

    extends = list(
        map(
            lambda e: get_nested_token(e, "NAME"),
            tree.find_pred(lambda c: c.data == "class_type"),
        )
    )

    symbol = InterfaceDecl(context, package_prefix + class_name, modifiers, extends)
    context.declare(symbol)

    nested_context = Context(context, symbol)
    context.children.append(nested_context)
    build_environment(
        next(tree.find_data("interface_body")),
        nested_context,
    )


def build_class_declaration(tree: ParseTree, context: Context, package_prefix: str):
    assert tree.data == "class_declaration"

    # class_declaration = get_tree_token(tree,)
    modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))
    class_name = get_nested_token(tree, "IDENTIFIER")

    extends = list(
        map(
            lambda e: get_nested_token(e, "IDENTIFIER"),
            tree.find_pred(lambda c: c.data == "class_type"),
        )
    )

    implements = list(
        map(
            lambda e: get_nested_token(e, "IDENTIFIER"),
            tree.find_pred(lambda c: c.data == "interface_type_list"),
        )
    )

    symbol = ClassDecl(context, package_prefix + class_name, modifiers, extends, implements)
    context.declare(symbol)

    nested_context = Context(context, symbol)
    context.children.append(nested_context)
    build_environment(next(tree.find_pred(lambda c: c.data == "class_body")), nested_context)


def parse_node(tree: ParseTree, context: Context):
    match tree.data:
        case "compilation_unit":
            # i dont like this but i dont know any clean way to pass the package name
            # to the class/interface declaration
            package_name = ""
            try:
                package_decl = next(tree.find_data("package_decl"))
                package_name = ".".join(get_identifiers(package_decl)) + "."
            except StopIteration:
                pass

            # run through imports
            for import_decl in tree.find_data("import_decl"):
                parse_node(import_decl, context)

            # attempt to build class declaration
            try:
                class_decl = next(tree.find_data("class_declaration"))
                build_class_declaration(class_decl, context, package_name)
            except StopIteration:
                pass

            # attempt to build interface declaration
            try:
                class_decl = next(tree.find_data("interface_declaration"))
                build_interface_declaration(class_decl, context, package_name)
            except StopIteration:
                pass

        case "constructor_declaration":
            modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))

            formal_params = next(tree.find_data("formal_param_list"), None)
            formal_param_types = list(
                map(
                    lambda fp: next(
                        map(lambda t: next(t.scan_values(lambda v: isinstance(v, Token))), fp.find_data("type"))
                    ),
                    formal_params.children,
                )
            ) if formal_params is not None else []

            symbol = ConstructorDecl(context, formal_param_types, modifiers)
            logging.debug("constructor_declaration %s %s", formal_param_types, modifiers)
            context.declare(symbol)

            #TODO: Declare parameter variables in nested context

            if (
                nested_tree := next(filter(lambda c: isinstance(c, Tree) and c.data == "block", tree.children), None)
            ) is not None:
                nested_context = Context(context, symbol)
                context.children.append(nested_context)
                build_environment(nested_tree, nested_context)

        case "method_declaration":
            modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))
            method_name = get_nested_token(tree, "IDENTIFIER")

            formal_params = next(tree.find_data("formal_param_list"), None)
            formal_param_types = list(
                map(
                    lambda fp: next(
                        map(lambda t: next(t.scan_values(lambda v: isinstance(v, Token))), fp.find_data("type"))
                    ),
                    formal_params.children,
                )
            ) if formal_params is not None else []

            return_type = (
                "void"
                if any(isinstance(x, Token) and x.type == "VOID_KW" for x in tree.children)
                else next(filter(lambda c: isinstance(c, Tree) and c.data == "type", tree.children)).children[0]
            )

            symbol = MethodDecl(context, method_name, formal_param_types, modifiers, return_type)
            logging.debug(
                "method_declaration",
                method_name,
                formal_param_types,
                modifiers,
                return_type,
            )
            context.declare(symbol)

            #TODO: Declare parameter variables in nested context

            if (nested_tree := next(tree.find_data("method_body"), None)) is not None:
                nested_context = Context(context, symbol)
                context.children.append(nested_context)
                print(nested_tree)
                print()
                for t in tree.find_data("method_body"):
                    print(t)
                    print()
                build_environment(nested_tree, nested_context)

        case "field_declaration":
            modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))
            field_type = get_tree_first_child(tree, "type")
            field_name = get_tree_token(tree, "var_declarator_id", "IDENTIFIER")

            logging.debug("field_declaration", field_name, modifiers, field_type)

            context.declare(FieldDecl(context, field_name, modifiers, field_type))

        case "local_var_declaration":
            var_type = get_tree_first_child(tree, "type")
            var_name = get_tree_token(tree, "var_declarator_id", "IDENTIFIER")

            logging.debug("local_var_declaration", var_name, var_type)

            context.declare(LocalVarDecl(context, var_name, var_type))

        case "single_type_import_decl":
            identifiers = list(v.value for v in tree.scan_values(lambda v: isinstance(v, Token)))
            # TODO maybe join type_path into a string so we don't have to pass two parameters?
            type_name = identifiers[-1]
            type_path = identifiers[1:]
            context.declare(SingleImport(context, type_name, type_path))
            logging.debug("single_type_import_decl", type_name, type_path)

        case "type_import_on_demand_decl":
            identifiers = list(tree.scan_values(lambda v: isinstance(v, Token)))
            import_path = ".".join(identifiers[1:])
            context.declare(OnDemandImport(context, import_path))
            logging.debug("type_import_on_demand_decl", import_path)

        case _:
            build_environment(tree, context)
