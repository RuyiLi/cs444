from __future__ import annotations

from typing import Dict, List, Optional, Set
from collections import defaultdict
from lark import Tree

import type_link


class SemanticError(Exception):
    pass


class Symbol:
    context: Context
    name: str

    # node types are at class level ("static") so we can access them with smth like ClassDecl.node_type
    node_type: str

    def __init__(self, context: Context, name: str):
        self.context = context
        self.name = name

        self._checked = False

    def sym_id(self):
        # TODO attrify
        return self.node_type + "^" + self.name

    def hierarchy_check(self):
        self._checked = True

    # TODO __repr__


class Context:
    parent: Context
    parent_node: Symbol
    symbol_map: Dict[str, Symbol]
    packages: Dict[str, List[ClassInterfaceDecl]]
    tree: Tree

    def __init__(self, parent: Context, parent_node: Symbol, tree: Tree):
        self.parent = parent
        self.parent_node = parent_node
        self.children = []
        self.symbol_map = {}
        self.packages = defaultdict(list)
        self.tree = tree

    def declare(self, symbol: Symbol):
        existing = self.resolve(symbol.sym_id())
        if existing is not None:
            raise SemanticError(f"Overlapping {symbol.node_type} in scope: {symbol.sym_id()}")

        # Duplicated in inherit_methods? Removing doesn't fail any tests.
        if symbol.node_type == "method_decl":
            matching = [
                x
                for x in self.symbol_map
                if x.split("^")[0] == symbol.name and self.symbol_map[x].node_type == "method_decl"
            ]

            for dup in matching:
                modifiers = self.symbol_map[dup].modifiers
                return_type = self.symbol_map[dup].return_type

                if "protected" in symbol.modifiers and "public" in modifiers:
                    raise SemanticError("A protected method must not replace a public method.")

                if "static" in symbol.modifiers and "static" not in modifiers:
                    raise SemanticError("A static method must not replace a nonstatic method.")

                if "static" not in symbol.modifiers and "static" in modifiers:
                    raise SemanticError("A nonstatic method must not replace a static method.")

                if "final" in modifiers:
                    raise SemanticError("A method must not replace a final method.")

                if return_type != symbol.return_type:
                    raise SemanticError("A method must not replace a method with a different return type.")

        self.symbol_map[symbol.sym_id()] = symbol

    def resolve(self, id_hash: str) -> Optional[Symbol]:
        if id_hash in self.symbol_map:
            return self.symbol_map.get(id_hash)

        # Try looking in parent scope
        if self.parent is not None:
            return self.parent.resolve(id_hash)

        return None


def check_cycle(symbol: ClassInterfaceDecl, visited: Set[str]):
    if symbol.sym_id() in visited:
        raise SemanticError(f"Cyclic dependency found, path {'->'.join(visited)} -> {symbol.sym_id()}")

    visited |= {symbol.sym_id()}
    for type_name in symbol.extends + getattr(symbol, "implements", []):
        next_sym = symbol.resolve_name(type_name)
        check_cycle(next_sym, visited.copy())


class PrimitiveType(Symbol):
    node_type = "primitive_type"

    def __init__(self, name: str):
        super().__init__(None, name)

    def sym_id(self):
        return f"primitive_type^{self.name}"

class ArrayType(Symbol):
    node_type = "array_type"

    def __init__(self, name: str):
        super().__init__(None, name)

    def sym_id(self):
        return f"array_type^{self.name}"


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


class ClassInterfaceDecl(Symbol):
    node_type = "class_interface"
    methods: List[MethodDecl]

    def __init__(
        self,
        context: Context,
        name: str,
        modifiers: List[str],
        extends: List[str],
        imports: List[type_link.ImportDeclaration],
    ):
        super().__init__(context, name)
        self.modifiers = modifiers
        self.extends = extends
        self.imports = imports

        self.fields = []
        self.methods = []
        self.type_names = {}

    def sym_id(self):
        return f"class_interface^{self.name}"

    def resolve_name(self, type_name: str) -> Optional[Symbol]:
        if type_name[-2:] == "[]":
            elem_type = self.resolve_name(type_name[:-2])
            return None if elem_type is None else ArrayType(elem_type.name + "[]")
        if type_name in type_link.PRIMITIVE_TYPES:
            return PrimitiveType(type_name)
        return self.type_names.get(type_name, None)

    def check_declare_same_signature(self):
        for i in range(len(self.methods)):
            for j in range(i + 1, len(self.methods)):
                if self.methods[i].signature() == self.methods[j].signature():
                    raise SemanticError(
                        f"Class/interface {self.name} cannot declare two methods with the same signature: {self.methods[i].signature}."
                    )

    def check_repeated_parents(self, parents: List[ClassInterfaceDecl]):
        qualified_parents = [self.resolve_name(parent).name for parent in parents]
        if len(set(qualified_parents)) < len(qualified_parents):
            raise SemanticError(
                f"Class/interface {self.name} cannot inherit a class/interface more than once."
            )

    def hierarchy_check(self):
        self.check_declare_same_signature()
        self.check_repeated_parents(self.extends)
        check_cycle(self, set())
        super().hierarchy_check()

    def resolve_method_return_types(self):
        for method in self.methods:
            if method.return_symbol is None:
                method.return_symbol = self.resolve_name(method.return_type)


class ClassDecl(ClassInterfaceDecl):
    node_type = "class_decl"

    def __init__(
        self,
        context: Context,
        name: str,
        modifiers: List[str],
        extends: List[str],
        imports: List[type_link.ImportDeclaration],
        implements: List[str],
    ):
        super().__init__(context, name, modifiers, extends, imports)
        self.implements = implements
        self.constructors = []

    def hierarchy_check(self):
        if self._checked:
            return

        self.resolve_method_return_types()

        for extend in self.extends:
            if extend == type_link.resolve_simple_name(self.name):
                raise SemanticError(f"Class {self.name} cannot extend itself.")

            exist_sym = self.resolve_name(extend)

            if exist_sym is None:
                raise SemanticError(f"Class {self.name} cannot extend class {extend} that does not exist.")

            # Ensure parents have inherited their methods first
            exist_sym.hierarchy_check()

            if exist_sym.node_type == "interface_decl":
                raise SemanticError(f"Class {self.name} cannot extend an interface ({extend}).")

            assert isinstance(exist_sym, ClassDecl)

            if "final" in exist_sym.modifiers:
                raise SemanticError(f"Class {self.name} cannot extend a final class ({extend}).")

            self.methods += inherit_methods(self, exist_sym)

        for implement in self.implements:
            exist_sym = self.resolve_name(implement)

            if exist_sym is None:
                raise SemanticError(
                    f"Class {self.name} cannot implement interface {implement} that does not exist."
                )

            # Ensure parents have inherited their methods first
            exist_sym.hierarchy_check()

            if exist_sym.node_type == "class_decl":
                raise SemanticError(f"Class {self.name} cannot implement a class ({implement}).")

            assert isinstance(exist_sym, InterfaceDecl)

            self.methods += inherit_methods(self, exist_sym)

        self.check_repeated_parents(self.implements)
        super().hierarchy_check()


class InterfaceDecl(ClassInterfaceDecl):
    node_type = "interface_decl"

    def __init__(
        self,
        context: Context,
        name: str,
        modifiers: List[str],
        extends: List[str],
        imports: List[type_link.ImportDeclaration],
    ):
        super().__init__(context, name, modifiers, extends, imports)

    def hierarchy_check(self):
        if self._checked:
            return

        self.resolve_method_return_types()

        for extend in self.extends:
            if extend == type_link.resolve_simple_name(self.name):
                raise SemanticError(f"Interface {self.name} cannot extend itself.")

            exist_sym = self.resolve_name(extend)

            if exist_sym is None:
                raise SemanticError(
                    f"Interface {self.name} cannot extend interface {extend} that does not exist."
                )

            # Ensure parents have inherited their methods first
            exist_sym.hierarchy_check()

            if exist_sym.node_type == "class_decl":
                raise SemanticError(f"Interface {self.name} cannot extend a class ({extend}).")

            assert isinstance(exist_sym, InterfaceDecl)
            self.methods += inherit_methods(self, exist_sym)

        # Interfaces do not actually extend from Object but rather implicitly
        # declare many of the same methods as Object, so we check if "inherit
        # methods" would pass
        exist_sym = self.resolve_name("Object")
        assert exist_sym is not None

        inherit_methods(self, exist_sym)

        self.check_repeated_parents(self.extends)
        super().hierarchy_check()


class ConstructorDecl(Symbol):
    node_type = "constructor"

    def __init__(self, context, param_types, modifiers):
        super().__init__(context, "constructor")
        self.param_types = param_types
        self.modifiers = modifiers

        assert isinstance(self.context.parent_node, ClassDecl)
        self.context.parent_node.constructors.append(self)

    def sym_id(self):
        return "constructor^" + ",".join(self.param_types) if self.param_types is not None else "constructor"


class FieldDecl(Symbol):
    node_type = "field_decl"

    def __init__(self, context, name, modifiers, field_type):
        super().__init__(context, name)
        self.modifiers = modifiers
        self.sym_type = field_type

        assert isinstance(self.context.parent_node, ClassInterfaceDecl)
        self.context.parent_node.fields.append(self)


class MethodDecl(Symbol):
    node_type = "method_decl"
    modifiers: List[str]
    return_type: str
    return_symbol: ClassInterfaceDecl | PrimitiveType

    def __init__(self, context, name, param_types, modifiers, return_type):
        super().__init__(context, name)
        self._param_types = param_types
        self.modifiers = modifiers
        self.return_type = return_type
        self.return_symbol = PrimitiveType(return_type) if return_type in type_link.PRIMITIVE_TYPES else None

        if self.context.parent_node.node_type == "interface_decl" and "abstract" not in self.modifiers:
            self.modifiers.append("abstract")

        assert isinstance(self.context.parent_node, ClassInterfaceDecl)
        self.context.parent_node.methods.append(self)

    @property
    def param_types(self):
        # a little sus, but here we assume that type linking is already finished
        if self._param_types is None:
            return []
        resolutions = map(self.context.parent_node.resolve_name, self._param_types)
        return [(self._param_types[i] if r is None else r.name) for i, r in enumerate(resolutions)]

    def signature(self):
        return self.name + "^" + ",".join(self.param_types)

    def sym_id(self):
        return self.signature()


class LocalVarDecl(Symbol):
    node_type = "local_var_decl"

    def __init__(self, context, name, var_type):
        super().__init__(context, name)
        self.sym_type = var_type
