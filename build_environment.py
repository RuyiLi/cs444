import logging
from itertools import chain
from typing import List

from lark import Token, Tree, ParseTree

from weeder import get_modifiers
from type_link import ImportDeclaration, SingleTypeImport, OnDemandImport
from context import (
    Context,
    ClassDecl,
    ClassInterfaceDecl,
    ConstructorDecl,
    FieldDecl,
    InterfaceDecl,
    LocalVarDecl,
    MethodDecl,
)


def build_environment(tree: ParseTree, context: Context, class_symbol: ClassInterfaceDecl = None):
    if class_symbol is None:
        parse_node(tree, context)
        return

    for child in tree.children:
        if isinstance(child, Tree):
            parse_node(child, context, class_symbol)


def get_tree_first_child(tree: ParseTree, name: str):
    return next(tree.find_data(name)).children[0]


def get_child_token(tree: ParseTree, name: str) -> str:
    return next(filter(lambda c: isinstance(c, Token) and c.type == name, tree.children)).value


def get_child_tree(tree: ParseTree, name: str):
    return next(filter(lambda c: isinstance(c, Tree) and c.data == name, tree.children), None)


def get_nested_token(tree: ParseTree, name: str) -> str:
    return next(tree.scan_values(lambda v: isinstance(v, Token) and v.type == name)).value


def get_tree_token(tree: ParseTree, tree_name: str, token_name: str):
    return get_nested_token(next(tree.find_data(tree_name)), token_name)


def get_tree_child_token(tree: ParseTree, tree_name: str, token_name: str):
    return get_child_token(next(tree.find_data(tree_name)), token_name)


def get_identifiers(tree: ParseTree):
    tokens = tree.scan_values(lambda v: isinstance(v, Token) and v.type == "IDENTIFIER")
    return (token.value for token in tokens)


def resolve_name(tree: ParseTree):
    return ".".join(get_identifiers(tree))


def resolve_type(tree: ParseTree):
    assert tree.data == "type"

    child = tree.children[0]
    if isinstance(child, Token):
        return child.value
    elif child.data == "array_type":
        element_type = child.children[0]
        return (element_type.value if isinstance(element_type, Token) else resolve_name(element_type)) + "[]"
    else:
        return resolve_name(child)


def get_formal_params(tree: ParseTree):
    formal_params = next(tree.find_data("formal_param_list"), None)

    formal_param_types = []
    formal_param_names = []

    if formal_params is not None:
        for child in formal_params.children:
            if isinstance(child, Token):
                continue

            formal_param_types.append(resolve_type(next(child.find_data("type"))))
            formal_param_names.append(get_tree_token(child, "var_declarator_id", "IDENTIFIER"))

    return (formal_param_types, formal_param_names)


def build_class_interface_decl(
    tree: ParseTree,
    context: Context,
    package_prefix: str,
    imports: List[ImportDeclaration],
):
    class_name = package_prefix + get_nested_token(tree, "IDENTIFIER")
    modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))
    extends = list(map(resolve_name, tree.find_data("class_type")))
    inherited_interfaces = next(tree.find_data("interface_type_list"), [])
    if inherited_interfaces:
        inherited_interfaces = list(map(resolve_name, inherited_interfaces.find_data("interface_type")))

    if tree.data == "class_declaration":
        symbol = ClassDecl(context, class_name, modifiers, extends, imports, inherited_interfaces)
    else:
        symbol = InterfaceDecl(context, class_name, modifiers, inherited_interfaces, imports)

    # enqueue extends and implements names for type resolution
    for type_name in chain(extends, inherited_interfaces):
        _enqueue_type(symbol, type_name)

    nested_context = Context(context, symbol)
    context.declare(symbol)
    context.children.append(nested_context)

    target_node_type = "class_body" if tree.data == "class_declaration" else "interface_body"
    build_environment(next(tree.find_data(target_node_type)), nested_context, symbol)

    return symbol


def _enqueue_type(class_symbol: ClassInterfaceDecl, type_name: str):
    class_symbol.type_names[type_name] = None


def parse_node(tree: ParseTree, context: Context, class_symbol: ClassInterfaceDecl = None):
    match tree.data:
        case "compilation_unit":
            # i dont like this but i dont know any clean way to pass the package name + imports
            # to the class/interface declaration. context is the global one here
            package_name = ""
            try:
                package_decl = next(tree.find_data("package_decl"))
                package_name = resolve_name(package_decl) + "."
            except StopIteration:
                pass

            # run thru imports, auto import java.lang.*
            imports = [OnDemandImport("java.lang")]
            for import_decl in tree.find_data("single_type_import_decl"):
                type_name = resolve_name(import_decl)
                imports.append(SingleTypeImport(type_name))
            for import_decl in tree.find_data("type_import_on_demand_decl"):
                type_name = resolve_name(import_decl)
                imports.append(OnDemandImport(type_name))

            # attempt to build class or interface declaration
            try:
                class_interface_decl = next(
                    tree.find_pred(lambda v: v.data in ["class_declaration", "interface_declaration"])
                )
                type_symbol = build_class_interface_decl(class_interface_decl, context, package_name, imports)

                # strip trailing period and add to context package list
                package_name = package_name[:-1]
                context.packages[package_name].append(type_symbol)

                # enqueue type names to be resolved in type link step
                # this is sus (e.g. doesnt work with methods foo.bar.A.B())
                for type_name in class_interface_decl.find_data("type_name"):
                    _enqueue_type(type_symbol, resolve_name(type_name))

            except StopIteration:
                pass

        case "constructor_declaration":
            modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))

            formal_param_types, formal_param_names = get_formal_params(tree)

            symbol = ConstructorDecl(context, formal_param_types, modifiers)
            logging.debug(f"constructor_declaration {formal_param_types} {modifiers}")
            context.declare(symbol)

            if (nested_tree := get_child_tree(tree, "block")) is not None:
                nested_context = Context(context, symbol)
                context.children.append(nested_context)

                for p_type, p_name in zip(formal_param_types, formal_param_names):
                    nested_context.declare(LocalVarDecl(nested_context, p_name, p_type))

                build_environment(nested_tree, nested_context, class_symbol)

        case "method_declaration":
            modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))

            method_declarator = next(tree.find_data("method_declarator"))
            method_name = get_nested_token(method_declarator, "IDENTIFIER")
            formal_param_types, formal_param_names = get_formal_params(tree)

            return_type = (
                "void"
                if any(isinstance(x, Token) and x.type == "VOID_KW" for x in tree.children)
                else resolve_type(get_child_tree(tree, "type"))
            )

            symbol = MethodDecl(context, method_name, formal_param_types, modifiers, return_type)
            context.declare(symbol)
            logging.debug(f"method_declaration {method_name} {formal_param_types} {modifiers} {return_type}")

            # check return type for type name
            # _enqueue_type()

            if (nested_tree := next(tree.find_data("method_body"), None)) is not None:
                nested_context = Context(context, symbol)
                context.children.append(nested_context)

                for p_type, p_name in zip(formal_param_types, formal_param_names):
                    nested_context.declare(LocalVarDecl(nested_context, p_name, p_type))

                build_environment(nested_tree, nested_context, class_symbol)

        case "field_declaration":
            modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))
            field_type = resolve_type(next(tree.find_data("type")))
            field_name = get_tree_token(tree, "var_declarator_id", "IDENTIFIER")

            # check field type for type name
            # if next(tree.find_data("type_name"), None) is not None:
            #     _enqueue_type(class_symbol, field_type.replace("[]", ""))

            logging.debug(f"field_declaration {field_name} {modifiers} {field_type}")
            context.declare(FieldDecl(context, field_name, modifiers, field_type))

        case "local_var_declaration":
            var_type = resolve_type(next(tree.find_data("type")))
            var_name = get_tree_token(tree, "var_declarator_id", "IDENTIFIER")

            logging.debug(f"local_var_declaration {var_name} {var_type}")
            context.declare(LocalVarDecl(context, var_name, var_type))

        case "statement":
            scope_stmts = ["block", "if_st", "if_else_st", "for_st", "while_st"]
            if (
                nested_block := next(
                    filter(lambda c: isinstance(c, Tree) and c.data in scope_stmts, tree.children), None
                )
            ) is not None:
                # Blocks inside blocks have the same parent node
                nested_context = Context(context, context.parent_node)
                context.children.append(nested_context)
                build_environment(nested_block, nested_context, class_symbol)

        case _:
            build_environment(tree, context, class_symbol)
