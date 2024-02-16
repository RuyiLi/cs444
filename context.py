from __future__ import annotations
from typing import Dict, List, Literal, Optional

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

    def sym_id(self):
        # TODO attrify
        return self.node_type + "^" + self.name

    def hierarchy_check(self):
        pass


class Context:
    parent: Context
    parent_node: Symbol
    symbol_map: Dict[str, Symbol]

    def __init__(self, parent: Context, parent_node: Symbol):
        self.parent = parent
        self.parent_node = parent_node
        self.children = []
        self.symbol_map = {}

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


def inherit_methods(symbol: ClassInterfaceDecl, methods: List[MethodDecl]):
    inherited_methods = []
    for method in methods:
        replacing = next(filter(lambda m: m.signature() == method.signature(), methods), None)

        # in Replace()?
        if replacing is not None:
            if replacing.return_type != method.return_type:
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
                    f"Non-abstract class {symbol.name} cannot inherit abstract method with signature {method.signature} without implementing it."
                )

            inherited_methods.append(method)

    return inherited_methods


def check_declare_same_signature(symbol: ClassInterfaceDecl):
    for i in range(len(symbol.methods)):
        for j in range(i + 1, len(symbol.methods)):
            if symbol.methods[i].signature() == symbol.methods[j].signature():
                raise SemanticError(
                    f"Class/interface {symbol.name} cannot declare two methods with the same signature: {symbol.methods[i].signature}."
                )


class ClassInterfaceDecl(Symbol):
    node_type = "class_interface"

    def __init__(
        self,
        context: Context,
        name: str,
        modifiers: List[str],
        extends: List[str],
    ):
        super().__init__(context, name)
        self.modifiers = modifiers
        self.extends = extends

        self.fields = []
        self.methods = []

    def sym_id(self):
        return f"class_interface^{self.name}"


class ClassDecl(ClassInterfaceDecl):
    node_type = "class_decl"

    def __init__(self, context, name, modifiers, extends, implements):
        super().__init__(context, name, modifiers, extends)
        self.implements = implements
        self.constructors = []

    def hierarchy_check(self):
        contained_methods = self.methods

        for extend in self.extends:
            exist_sym = self.context.resolve(f"class_interface^{extend}")

            if exist_sym is None:
                raise SemanticError(f"Class {self.name} cannot extend class {extend} that does not exist.")

            if exist_sym.node_type == "interface_decl":
                raise SemanticError(f"Class {self.name} cannot extend an interface ({extend}).")

            assert isinstance(exist_sym, ClassDecl)

            if "final" in exist_sym.modifiers:
                raise SemanticError(f"Class {self.name} cannot extend a final class ({extend}).")

            contained_methods = contained_methods + inherit_methods(self, exist_sym.methods)

        if len(set(self.extends)) < len(self.extends):
            raise SemanticError(f"Duplicate class/interface in extends for class {self.name}")

        for implement in self.implements:
            exist_sym = self.context.resolve(f"class_interface^{implement}")

            if exist_sym is None:
                raise SemanticError(f"Class {self.name} cannot extend class {implement} that does not exist.")

            if exist_sym.node_type == "class_decl":
                raise SemanticError(f"Class {self.name} cannot implement a class ({implement}).")

            assert isinstance(exist_sym, InterfaceDecl)

            contained_methods = contained_methods + inherit_methods(self, exist_sym.methods)

        if len(set(self.extends)) < len(self.extends):
            raise SemanticError(f"Duplicate class/interface in implements for class {self.name}")

        check_declare_same_signature(self)

class InterfaceDecl(ClassInterfaceDecl):
    node_type = "interface_decl"

    def __init__(self, context: Context, name: str, modifiers: List[str], extends: List[str]):
        super().__init__(context, name, modifiers, extends)

    def hierarchy_check(self):
        contained_methods = self.methods

        for extend in self.extends:
            exist_sym = self.context.resolve(f"class_interface^{extend}")

            if exist_sym is None:
                raise SemanticError(
                    f"Interface {self.name} cannot extend interface {extend} that does not exist."
                )

            if exist_sym.node_type == "class_decl":
                raise SemanticError(f"Interface {self.name} cannot extend a class ({extend}).")

            assert isinstance(exist_sym, InterfaceDecl)
            contained_methods = contained_methods + inherit_methods(self, exist_sym.methods)

        if len(set(self.extends)) < len(self.extends):
            raise SemanticError(f"Duplicate class/interface in extends for interface {self.name}")

        check_declare_same_signature(self)


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

    def __init__(self, context, name, param_types, modifiers, return_type):
        super().__init__(context, name)
        self.param_types = param_types
        self.modifiers = modifiers
        self.return_type = return_type

        assert isinstance(self.context.parent_node, ClassInterfaceDecl)
        self.context.parent_node.methods.append(self)

    def signature(self):
        return self.name + "^" + ",".join(self.param_types) if self.param_types is not None else self.name

    def sym_id(self):
        return self.signature()


class LocalVarDecl(Symbol):
    node_type = "local_var_decl"

    def __init__(self, context, name, var_type):
        super().__init__(context, name)
        self.sym_type = var_type


class IfStmt(Symbol):
    def __init__(self, context, name):
        super().__init__(context, name)


class WhileStmt(Symbol):
    def __init__(self, context, name):
        super().__init__(context, name)


class OnDemandImport(Symbol):
    node_type = "type_import_on_demand_decl"

    def __init__(self, context, name):
        super().__init__(context, name)


class SingleImport(Symbol):
    """
    A "path" is the full type_name of the import (e.g. foo.bar.Baz)
    A "name" is just the name of the object being imported (e.g. Baz)
    """

    node_type = "single_type_import_decl"

    def __init__(self, context, name, type_path):
        super().__init__(context, name)
        self.type_path = type_path

    @property
    def type_name(self):
        return ".".join(self.type_path)

    def type_link(self):
        imported_object = f"{ClassInterfaceDecl.node_type}^{self.name}"
        # Import names cannot be the same as the class or interface being declared in the same file.
        if imported_object in self.context.symbol_map:
            raise SemanticError(f"Single type import name clashes with class declaration: {self.type_name}")

        # Import paths must resolve to some class or interface in the global environment.
        # if self.context.resolve()
        # print(list(self.context.symbol_map.keys()))
        # print(self.context.resolve(self.sym_id()).name)
