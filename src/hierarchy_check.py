from collections import defaultdict
from typing import Set

import type_link
from context import ClassDecl, ClassInterfaceDecl, Context, InterfaceDecl, MethodDecl, SemanticError


def hierarchy_check(context: Context):
    java_object = context.resolve(f"{ClassInterfaceDecl.node_type}^java.lang.Object")
    class_hierarchy_check(java_object)
    hierarchy_check_recursive(context)


def hierarchy_check_recursive(context: Context):
    for symbol in context.symbol_map.values():
        if isinstance(symbol, ClassInterfaceDecl):
            class_interface_hierarchy_check(symbol)

    for subcontext in context.children:
        hierarchy_check_recursive(subcontext)


def check_cycle(symbol: ClassInterfaceDecl, visited: Set[str]):
    if symbol.sym_id() in visited:
        raise SemanticError(f"Cyclic dependency found, path {'->'.join(visited)} -> {symbol.sym_id()}")

    visited |= {symbol.sym_id()}
    for type_name in symbol.extends + getattr(symbol, "implements", []):
        next_sym = symbol.resolve_name(type_name)
        check_cycle(next_sym, visited.copy())


def validate_replace_method(method: MethodDecl, replacer: MethodDecl):
    parent_name = method.context.parent_node.name
    if replacer.return_symbol.name != method.return_symbol.name:
        raise SemanticError(
            f"Class/interface {parent_name} cannot replace method with signature {method.signature()} with differing return types."
        )

    if ("static" in replacer.modifiers) != ("static" in method.modifiers):
        raise SemanticError(
            f"Class/interface {parent_name} cannot replace method with signature {method.signature()} with differing static-ness."
        )

    if "protected" in replacer.modifiers and "public" in method.modifiers:
        raise SemanticError(
            f"Class/interface {parent_name} cannot replace public method with signature {method.signature()} with a protected method."
        )

    if "final" in method.modifiers:
        raise SemanticError(
            f"Class/interface {parent_name} cannot replace final method with signature {method.signature()}."
        )


def inherit_methods(symbol: ClassInterfaceDecl, methods: list[MethodDecl]):
    inherited_methods = []
    # print("class methods:", [m.signature() for m in symbol.methods])
    # print("inherited:", [m.signature() for m in methods])
    for method in methods:
        # method is the method from the parent class/interface that we're about to replace
        replacer = next(filter(lambda m: m.signature() == method.signature(), symbol.methods), None)

        # in Replace()?
        if replacer is not None:
            validate_replace_method(method, replacer)
        else:
            if (
                symbol.node_type == "class_decl"
                and "abstract" in method.modifiers
                and "abstract" not in symbol.modifiers
            ):
                raise SemanticError(
                    f"Non-abstract class {symbol.name} cannot inherit abstract method with signature {method.signature()} without implementing it."
                )

            inherited_methods.append(method)

    return inherited_methods


def inherit_fields(symbol: ClassInterfaceDecl, inherited_sym: ClassInterfaceDecl):
    return [
        inherited_field
        for inherited_field in inherited_sym.fields
        if not any(inherited_field.name == declared_field.name for declared_field in symbol.fields)
    ]


def class_interface_hierarchy_check(symbol: ClassInterfaceDecl):
    if isinstance(symbol, ClassDecl):
        class_hierarchy_check(symbol)
    elif isinstance(symbol, InterfaceDecl):
        interface_hierarchy_check(symbol)

    symbol.check_declare_same_signature()
    symbol.check_repeated_parents(symbol.extends)
    check_cycle(symbol, set())


def merge_methods(method_dict: dict[str, list[MethodDecl]]):
    methods_to_return = []

    for signature, methods in method_dict.items():
        # i dont know how to deal with case where theres multiple
        method_with_body = next((m for m in methods if m.has_body), None)
        if method_with_body is not None:
            for method in methods:
                if method != method_with_body:
                    validate_replace_method(method, method_with_body)

        if non_abstract := next((m for m in methods if "abstract" not in m.modifiers), None):
            if any(m.return_type != non_abstract.return_type for m in methods):
                raise SemanticError(
                    f"Return types of multiple-inherited functions with signature {signature} don't match."
                )

            methods_to_return.append(non_abstract)
        else:
            if any(m.return_type != n.return_type for m in methods for n in methods):
                raise SemanticError(
                    f"Return types of multiple-abstract-inherited functions with signature {signature} don't match."
                )

            # Append the public one since it's the most strict
            methods_to_return.append(next((m for m in methods if "public" in m.modifiers), methods[0]))

    return methods_to_return


def extends_java_object(symbol: ClassDecl):
    for extend in symbol.extends:
        extend_sym = symbol.resolve_name(extend)
        if extend_sym.name == "java.lang.Object":
            return True
        if extends_java_object(extend_sym):
            return True
    return False


def class_hierarchy_check(symbol: ClassDecl):
    if symbol._checked:
        return

    symbol.populate_method_return_symbols()
    methods_to_inherit = defaultdict(list)

    for extend in symbol.extends:
        if extend == type_link.get_simple_name(symbol.name):
            raise SemanticError(f"Class {symbol.name} cannot extend itself.")

        exist_sym = symbol.resolve_name(extend)

        if exist_sym is None:
            raise SemanticError(f"Class {symbol.name} cannot extend class {extend} that does not exist.")

        if isinstance(exist_sym, InterfaceDecl):
            raise SemanticError(f"Class {symbol.name} cannot extend an interface ({extend}).")

        assert isinstance(exist_sym, ClassDecl)

        # Ensure parents have inherited their methods first
        class_hierarchy_check(exist_sym)

        if "final" in exist_sym.modifiers:
            raise SemanticError(f"Class {symbol.name} cannot extend a final class ({extend}).")

        for method in exist_sym.methods:
            methods_to_inherit[method.signature()].append(method)

        # symbol.methods += inherit_methods(symbol, exist_sym)
        symbol.fields += inherit_fields(symbol, exist_sym)

    for implement in symbol.implements:
        exist_sym = symbol.resolve_name(implement)

        if exist_sym is None:
            raise SemanticError(
                f"Class {symbol.name} cannot implement interface {implement} that does not exist."
            )

        if isinstance(exist_sym, ClassDecl):
            raise SemanticError(f"Class {symbol.name} cannot implement a class ({implement}).")

        assert isinstance(exist_sym, InterfaceDecl)

        # Ensure parents have inherited their methods first
        interface_hierarchy_check(exist_sym)

        for method in exist_sym.methods:
            methods_to_inherit[method.signature()].append(method)

        # symbol.methods += inherit_methods(symbol, exist_sym)
        symbol.fields += inherit_fields(symbol, exist_sym)

    symbol.methods += inherit_methods(symbol, merge_methods(methods_to_inherit))

    # don't acctually extend object, do it implicitly (see resolve_method)
    if symbol.name != "java.lang.Object" and not extends_java_object(symbol):
        java_object = symbol.resolve_name("java.lang.Object")
        java_object_methods = set(m.signature() for m in java_object.methods)
        inherit_methods(
            java_object,
            [m for m in symbol.methods if m.signature() in java_object_methods and not m.has_body],
        )
        inherit_methods(symbol, java_object.methods)

    symbol.check_repeated_parents(symbol.implements)
    symbol._checked = True


def interface_hierarchy_check(symbol: InterfaceDecl):
    if symbol._checked:
        return

    symbol.populate_method_return_symbols()

    for extend in symbol.extends:
        if extend == type_link.get_simple_name(symbol.name):
            raise SemanticError(f"Interface {symbol.name} cannot extend itself.")

        exist_sym = symbol.resolve_name(extend)

        if exist_sym is None:
            raise SemanticError(
                f"Interface {symbol.name} cannot extend interface {extend} that does not exist."
            )

        if isinstance(exist_sym, ClassDecl):
            raise SemanticError(f"Interface {symbol.name} cannot extend a class ({extend}).")

        assert isinstance(exist_sym, InterfaceDecl)

        # Ensure parents have inherited their methods first
        interface_hierarchy_check(exist_sym)

        symbol.methods += inherit_methods(symbol, exist_sym.methods)
        symbol.fields += inherit_fields(symbol, exist_sym)

    # Interfaces do not actually extend from Object but rather implicitly
    # declare many of the same methods as Object, so we check if "inherit
    # methods" would pass
    exist_sym = symbol.resolve_name("java.lang.Object")
    assert exist_sym is not None

    inherit_methods(symbol, exist_sym.methods)

    symbol.check_repeated_parents(symbol.extends)
    symbol._checked = True
