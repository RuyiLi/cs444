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

        self.symbol_map[symbol.sym_id()] = symbol

    def resolve(self, id_hash: str) -> Optional[Symbol]:
        if id_hash in self.symbol_map:
            return self.symbol_map.get(id_hash)

        # Try looking in parent scope
        if self.parent is not None:
            return self.parent.resolve(id_hash)

        return None


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

    def check_repeated_parents(self, parents: List[str]):
        qualified_parents = [self.resolve_name(parent).name for parent in parents]
        if len(set(qualified_parents)) < len(qualified_parents):
            raise SemanticError(
                f"Class/interface {self.name} cannot inherit a class/interface more than once."
            )

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
