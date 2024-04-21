import logging
from itertools import chain
from typing import List

import type_link
from context import (
    ClassDecl,
    ClassInterfaceDecl,
    ConstructorDecl,
    Context,
    FieldDecl,
    GlobalContext,
    InterfaceDecl,
    LocalVarDecl,
    MethodDecl,
)
from helper import (
    extract_name,
    extract_type,
    get_child_tree,
    get_formal_params,
    get_modifiers,
    get_nested_token,
    get_return_type,
    get_tree_token,
)
from lark import ParseTree, Tree


def build_environment(tree: ParseTree, context: Context):
    if isinstance(context, GlobalContext):
        build_compilation_unit(tree, context)
        return

    for child in tree.children:
        if isinstance(child, Tree):
            parse_node(child, context)


def build_compilation_unit(tree: ParseTree, context: Context):
    package_name = ""
    try:
        package_decl = next(tree.find_data("package_decl"))
        package_name = extract_name(package_decl) + "."
    except StopIteration:
        pass

    # run thru imports, auto import java.lang.*
    imports: List[type_link.ImportDeclaration] = [type_link.OnDemandImport("java.lang")]
    for import_decl in tree.find_data("single_type_import_decl"):
        type_name = extract_name(import_decl)
        imports.append(type_link.SingleTypeImport(type_name))
    for import_decl in tree.find_data("type_import_on_demand_decl"):
        type_name = extract_name(import_decl)
        imports.append(type_link.OnDemandImport(type_name))

    # attempt to build class or interface declaration
    try:
        class_interface_decl = next(
            tree.find_pred(lambda v: v.data in ["class_declaration", "interface_declaration"])
        )
        type_symbol = build_class_interface_decl(class_interface_decl, context, package_name, imports)

        assert isinstance(context, GlobalContext)

        # strip trailing period and add to context package list
        package_name = package_name[:-1]
        context.packages[package_name].append(type_symbol)

        # enqueue type names to be resolved in type link step
        for type_name in class_interface_decl.find_data("type_name"):
            _enqueue_type(type_symbol, extract_name(type_name))

    except StopIteration:
        pass


def build_class_interface_decl(
    tree: ParseTree,
    context: Context,
    package_prefix: str,
    imports: List[type_link.ImportDeclaration],
):
    class_name = package_prefix + get_nested_token(tree, "IDENTIFIER")
    modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))
    extends = list(map(extract_name, tree.find_data("class_type")))
    # if not extends and class_name != "java.lang.Object":
    #     extends = ["Object"]
    inherited_interfaces = next(tree.find_data("interface_type_list"), [])

    if isinstance(inherited_interfaces, Tree):
        inherited_interfaces = list(map(extract_name, inherited_interfaces.find_data("interface_type")))

    if tree.data == "class_declaration":
        symbol = ClassDecl(context, class_name, modifiers, extends, imports, inherited_interfaces)
    else:
        symbol = InterfaceDecl(context, class_name, modifiers, inherited_interfaces, imports)

    # enqueue extends and implements names for type resolution
    for type_name in chain(extends, inherited_interfaces):
        _enqueue_type(symbol, type_name)

    target_node_type = "class_body" if tree.data == "class_declaration" else "interface_body"
    nested_tree = next(tree.find_data(target_node_type))

    nested_context = Context(context, symbol, nested_tree)
    context.declare(symbol)
    context.children.append(nested_context)

    build_environment(nested_tree, nested_context)

    return symbol


def _enqueue_type(class_symbol: ClassInterfaceDecl, type_name: str):
    class_symbol.type_names[type_name] = None


def parse_node(tree: ParseTree, context: Context):
    match tree.data:
        case "constructor_declaration":
            modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))

            formal_param_types, formal_param_names = get_formal_params(tree)

            symbol = ConstructorDecl(context, formal_param_types, modifiers)
            logging.debug(f"constructor_declaration {formal_param_types} {modifiers}")
            context.declare(symbol)

            if (nested_tree := get_child_tree(tree, "block")) is not None:
                nested_context = Context(context, symbol, nested_tree)
                context.children.append(nested_context)
                context.child_map["__constructor"] = nested_context

                for p_type, p_name in zip(formal_param_types, formal_param_names):
                    nested_context.declare(LocalVarDecl(nested_context, p_name, p_type, tree.meta))

                build_environment(nested_tree, nested_context)

        case "method_declaration":
            modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))

            method_declarator = next(tree.find_data("method_declarator"))
            method_name = get_nested_token(method_declarator, "IDENTIFIER")
            formal_param_types, formal_param_names = get_formal_params(tree)

            return_type = get_return_type(tree)
            nested_tree = next(tree.find_data("method_body"), None)
            has_body = nested_tree is not None and isinstance(nested_tree.children[0], Tree)

            symbol = MethodDecl(context, method_name, formal_param_types, modifiers, return_type, has_body)
            context.declare(symbol)
            logging.debug(f"method_declaration {method_name} {formal_param_types} {modifiers} {return_type}")

            if nested_tree is not None:
                nested_context = Context(context, symbol, nested_tree)
                context.children.append(nested_context)
                context.child_map[method_name] = nested_context

                for p_type, p_name in zip(formal_param_types, formal_param_names):
                    nested_context.declare(LocalVarDecl(nested_context, p_name, p_type, tree.meta))

                build_environment(nested_tree, nested_context)

        case "field_declaration":
            modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))
            field_type = extract_type(next(tree.find_data("type")))
            field_name = get_tree_token(tree, "var_declarator_id", "IDENTIFIER")

            logging.debug(f"field_declaration {field_name} {modifiers} {field_type}")
            context.declare(FieldDecl(context, field_name, modifiers, field_type, tree.meta))

        case "local_var_declaration":
            var_type = extract_type(next(tree.find_data("type")))
            var_name = get_tree_token(tree, "var_declarator_id", "IDENTIFIER")

            logging.debug(f"local_var_declaration {var_name} {var_type}")
            context.declare(LocalVarDecl(context, var_name, var_type, tree.meta))

        case "statement":
            scope_stmts = ["block", "if_st", "if_else_st", "for_st", "while_st"]
            if nested_block := next(
                (c for c in tree.children if isinstance(c, Tree) and c.data in scope_stmts), None
            ):
                # Blocks inside blocks have the same parent node
                nested_context = Context(context, context.parent_node, nested_block)
                context.children.append(nested_context)
                context.child_map[f"{hash(nested_block)}"] = nested_context
                build_environment(nested_block, nested_context)

        case _:
            build_environment(tree, context)
