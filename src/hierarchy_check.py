from typing import Set
from context import ClassDecl, ClassInterfaceDecl, Context, InterfaceDecl, SemanticError

import type_link

def hierarchy_check(context: Context):
    for symbol in context.symbol_map.values():
        if isinstance(symbol, ClassInterfaceDecl):
            class_interface_hierarchy_check(symbol)

    for subcontext in context.children:
        hierarchy_check(subcontext)


def check_cycle(symbol: ClassInterfaceDecl, visited: Set[str]):
    if symbol.sym_id() in visited:
        raise SemanticError(f"Cyclic dependency found, path {'->'.join(visited)} -> {symbol.sym_id()}")

    visited |= {symbol.sym_id()}
    for type_name in symbol.extends + getattr(symbol, "implements", []):
        next_sym = symbol.resolve_name(type_name)
        check_cycle(next_sym, visited.copy())

def inherit_methods(symbol: ClassInterfaceDecl, inherited_sym: ClassInterfaceDecl):
    inherited_methods = []
    for method in inherited_sym.methods:
        # method is the method from the parent class/interface that we're about to replace
        replacing = next(filter(lambda m: m.signature() == method.signature(), symbol.methods), None)

        # in Replace()?
        if replacing is not None:
            if replacing.return_symbol.name != method.return_symbol.name:
                raise SemanticError(
                    f"Class/interface {symbol.name} cannot replace method with signature {method.signature()} with differing return types."
                )

            if ("static" in replacing.modifiers) != ("static" in method.modifiers):
                raise SemanticError(
                    f"Class/interface {symbol.name} cannot replace method with signature {method.signature()} with differing static-ness."
                )

            if "protected" in replacing.modifiers and "public" in method.modifiers:
                raise SemanticError(
                    f"Class/interface {symbol.name} cannot replace public method with signature {method.signature()} with a protected method."
                )

            if "final" in method.modifiers:
                raise SemanticError(
                    f"Class/interface {symbol.name} cannot replace final method with signature {method.signature()}."
                )
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
    return [inherited_field for inherited_field in inherited_sym.fields
        if not any(inherited_field.name == declared_field.name for declared_field in symbol.fields)]


def class_interface_hierarchy_check(symbol: ClassInterfaceDecl):
    if isinstance(symbol, ClassDecl):
        class_hierarchy_check(symbol)
    elif isinstance(symbol, InterfaceDecl):
        interface_hierarchy_check(symbol)

    symbol.check_declare_same_signature()
    symbol.check_repeated_parents(symbol.extends)
    check_cycle(symbol, set())


def class_hierarchy_check(symbol: ClassDecl):
    if symbol._checked:
        return

    symbol.resolve_method_return_types()

    for extend in symbol.extends:
        if extend == type_link.resolve_simple_name(symbol.name):
            raise SemanticError(f"Class {symbol.name} cannot extend itsymbol.")

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

        symbol.methods += inherit_methods(symbol, exist_sym)
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

        symbol.methods += inherit_methods(symbol, exist_sym)
        symbol.fields += inherit_fields(symbol, exist_sym)

    symbol.check_repeated_parents(symbol.implements)
    symbol._checked = True


def interface_hierarchy_check(symbol: InterfaceDecl):
    if symbol._checked:
        return

    symbol.resolve_method_return_types()

    for extend in symbol.extends:
        if extend == type_link.resolve_simple_name(symbol.name):
            raise SemanticError(f"Interface {symbol.name} cannot extend itsymbol.")

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

        symbol.methods += inherit_methods(symbol, exist_sym)
        symbol.fields += inherit_fields(symbol, exist_sym)

    # Interfaces do not actually extend from Object but rather implicitly
    # declare many of the same methods as Object, so we check if "inherit
    # methods" would pass
    exist_sym = symbol.resolve_name("Object")
    assert exist_sym is not None

    inherit_methods(symbol, exist_sym)

    symbol.check_repeated_parents(symbol.extends)
    symbol._checked = True
