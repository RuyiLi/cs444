from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Type, TypeVar

import type_link
from joos_types import ArrayType, PrimitiveType, ReferenceType, SymbolType, is_primitive_type
from lark import Tree
from lark.tree import Meta


class SemanticError(Exception):
    pass


class Symbol:
    context: Context
    name: str
    meta: Meta

    # node types are at class level ("static") so we can access them with smth like ClassDecl.node_type
    node_type: str

    def __init__(self, context: Context, name: str):
        self.context = context
        self.name = name

    def sym_id(self):
        return self.node_type + "^" + self.name

    def __repr__(self):
        # idk how to fix circular refs
        # items = ", ".join(f"{k}=?" for k, v in self.__dict__.items())
        return f"{self.__class__.__name__}(name={self.name}, context={self.context})"


T = TypeVar("T", bound=Symbol)


class Context:
    parent: Context
    parent_node: Symbol
    symbol_map: Dict[str, Symbol]
    tree: Tree
    is_static: bool
    children: List[Context]
    child_map: Dict[str, Context]

    def __init__(self, parent: Context, parent_node: Symbol, tree: Tree, is_static: bool = False):
        self.parent = parent
        self.parent_node = parent_node
        self.children = []
        self.child_map = dict()
        self.symbol_map = {}
        self.tree = tree
        self.is_static = is_static

        if self.tree is not None:
            setattr(self.tree, "context", self)

    def declare(self, symbol: Symbol):
        existing = self.resolve_hash(symbol.sym_id())
        if existing is not None:
            raise SemanticError(f"Overlapping {symbol.node_type} in scope: {symbol.sym_id()}")

        self.symbol_map[symbol.sym_id()] = symbol

    def resolve(self, sym_type: Type[T], name: str) -> Optional[T]:
        return self.resolve_hash(f"{sym_type.node_type}^{name}")

    def resolve_hash(self, id_hash: str) -> Optional[Symbol]:
        if id_hash in self.symbol_map:
            return self.symbol_map.get(id_hash)

        # Try looking in parent scope
        if self.parent is not None:
            return self.parent.resolve_hash(id_hash)

        return None


class GlobalContext(Context):
    packages: Dict[str, List[ClassInterfaceDecl]]

    def __init__(self):
        super().__init__(None, None, None)
        self.packages = defaultdict(list)


def validate_field_access(
    field: FieldDecl | MethodDecl,
    accessor: ClassInterfaceDecl,
    static: bool,
    orig_owner: ClassInterfaceDecl,
):
    if static and "static" not in field.modifiers:
        raise SemanticError(f"Cannot access non-static name {field.name} from static context.")

    if not static and "static" in field.modifiers:
        raise SemanticError(f"Cannot access static name {field.name} from non-static context.")

    if "protected" in field.modifiers:
        container = field.context.parent_node
        if not (
            (
                # accessor must always be a subclass of the declaring class
                accessor.is_subclass_of(container.name)
                # if the field is not static (ie instance), the ref type of the field access
                # must be a subclass of the accessor
                and ("static" in field.modifiers or orig_owner.is_subclass_of(accessor.name))
            )
            # or they can just be in the same package
            or accessor.package == container.package
        ):
            raise SemanticError(f"Cannot access protected name {field.name} from unrelated context.")


class ClassInterfaceDecl(Symbol):
    node_type = "class_interface"

    modifiers: List[str]
    extends: List[str]
    imports: List[type_link.ImportDeclaration]
    fields: List[FieldDecl]
    methods: List[MethodDecl]
    type_names: Dict[str, ClassInterfaceDecl]

    instance_fields: Dict[FieldDecl, int]
    instance_methods: Dict[MethodDecl, int]

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
        self.instance_fields = dict()
        self.methods = []
        self.instance_methods = dict()
        self.type_names = {}

        self._checked = False

    def sym_id(self):
        return f"class_interface^{self.name}"

    def resolve_type(self, type_name: str) -> Optional[SymbolType]:
        if is_primitive_type(type_name):
            return PrimitiveType(type_name)

        if type_name[-2:] == "[]":
            elem_type = self.resolve_type(type_name[:-2])
            return None if elem_type is None else ArrayType(elem_type)

        if symbol := self.resolve_name(type_name):
            return ReferenceType(symbol)

    def resolve_name(self, type_name: str) -> Optional[ClassInterfaceDecl]:
        if symbol := self.type_names.get(type_name, None):
            return symbol

        try:
            # late resolution
            type_link.resolve_type(self.context, type_name, self)
            return self.type_names[type_name]
        except SemanticError:
            if type_decl := self.context.resolve(ClassInterfaceDecl, type_name):
                if type_decl.package == "" and self.package != "":
                    # type_decl is in default package, but accessor (self) is not
                    return None
                return type_decl

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

    def resolve_method(
        self,
        method_name: str,
        argtypes: List[str],
        accessor: ClassInterfaceDecl,
        allow_static: bool = False,
        orig_owner: ClassInterfaceDecl = None,
    ) -> Optional[MethodDecl]:
        orig_owner = orig_owner or self

        signature = method_name + "^" + ",".join(argtypes)
        for method in self.methods:
            if method.signature() == signature:
                validate_field_access(method, accessor, allow_static, orig_owner)
                return method

        # TODO interfaces?
        for extend in self.extends:
            parent = self.resolve_name(extend)
            if parent is not None:
                method = parent.resolve_method(method_name, argtypes, accessor, allow_static, orig_owner)
                if method is not None:
                    validate_field_access(method, accessor, allow_static, orig_owner)
                    return method

        java_object = self.resolve_name("java.lang.Object")
        signature = method_name + "^" + ",".join(argtypes)
        for method in java_object.methods:
            if method.signature() == signature:
                validate_field_access(method, accessor, allow_static, orig_owner)
                return method

        return None

    def resolve_field(
        self,
        field_name: str,
        accessor: ClassInterfaceDecl,
        allow_static: bool = False,
        orig_owner: ClassInterfaceDecl = None,
    ) -> Optional[FieldDecl]:
        orig_owner = orig_owner or self

        for field in self.fields:
            if field.name == field_name:
                validate_field_access(field, accessor, allow_static, orig_owner)
                return field

        # TODO interfaces?
        for extend in self.extends:
            if (parent := self.resolve_name(extend)) and (
                field := parent.resolve_field(field_name, accessor, allow_static, orig_owner)
            ):
                validate_field_access(field, accessor, allow_static, orig_owner)
                return field
        return None

    @property
    def all_instance_fields(self) -> List[str]:
        # need to maintain order
        fields = []
        for extend in self.extends:
            if parent := self.resolve_name(extend):
                for field in parent.all_instance_fields:
                    if field not in fields:
                        fields.append(field)
        for field in self.fields:
            if "static" not in field.modifiers and field.name not in fields:
                fields.append(field.name)
        return fields

    @property
    def all_instance_methods(self) -> List[str]:
        # need to maintain order
        methods: List[str] = []
        for extend in self.extends:
            if parent := self.resolve_name(extend):
                for method in parent.all_instance_methods:
                    if method not in methods:
                        methods.append(method)
        for method in self.methods:
            if "static" not in method.modifiers and method.name not in methods:
                methods.append(method.signature())
        return methods

    def populate_method_return_symbols(self):
        for method in self.methods:
            if method.return_symbol is None:
                method.return_symbol = self.resolve_type(method.return_type)

    def is_subclass_of(self, name: str):
        if self.name == name:
            return True
        for extend in self.extends:
            if (parent := self.resolve_name(extend)) and (name == parent.name or parent.is_subclass_of(name)):
                return True
        return False

    @property
    def package(self):
        return type_link.get_package_name(self.name)


class ClassDecl(ClassInterfaceDecl):
    node_type = "class_decl"

    implements: List[str]
    constructors: List[ConstructorDecl]

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

    def resolve_constructor(self, arg_types: List[str]) -> Optional[ConstructorDecl]:
        signature = "constructor^" + ",".join(param for param in arg_types)
        for constructor in self.constructors:
            if constructor.sym_id() == signature:
                return constructor
        return None

    def implements_interface(self, name: str):
        for interface in self.implements:
            if (interface := self.resolve_name(interface)) and name == interface.name:
                return True

        for extend in self.extends:
            if (parent := self.resolve_name(extend)) and parent.implements_interface(name):
                return True

        return False


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

    def __init__(self, context, raw_param_types, modifiers):
        super().__init__(context, "constructor")
        self.raw_param_types = raw_param_types or []
        self.modifiers = modifiers

        assert isinstance(self.context.parent_node, ClassDecl)
        self.context.parent_node.constructors.append(self)

    def sym_id(self):
        if len(self.param_types) > 0 and self.param_types[0] is None:
            return "constructor^" + ",".join(param for param in self.raw_param_types)

        return "constructor^" + ",".join(param.name for param in self.param_types)

    @property
    def param_types(self):
        # assumes type linking is finished
        return [self.context.parent_node.resolve_type(param) for param in self.raw_param_types]


class FieldDecl(Symbol):
    node_type = "field_decl"

    def __init__(self, context, name, modifiers, field_type, meta):
        super().__init__(context, name)
        self.modifiers = modifiers
        self.sym_type = field_type
        self.meta = meta

        assert isinstance(self.context.parent_node, ClassInterfaceDecl)
        self.context.parent_node.fields.append(self)

        if "static" not in self.modifiers:
            self.context.parent_node.instance_fields[self] = len(self.context.parent_node.instance_fields)

    @property
    def resolved_sym_type(self) -> SymbolType:
        # assumes type linking is finished
        return self.context.parent_node.resolve_type(self.sym_type)


class MethodDecl(Symbol):
    node_type = "method_decl"
    modifiers: List[str]
    return_type: str
    return_symbol: SymbolType | None
    has_body: bool

    def __init__(self, context, name, param_types, modifiers, return_type, has_body):
        super().__init__(context, name)
        self.raw_param_types = param_types
        self.modifiers = modifiers
        self.return_type = return_type
        self.return_symbol = PrimitiveType(return_type) if is_primitive_type(return_type) else None
        self.has_body = has_body

        if self.context.parent_node.node_type == "interface_decl" and "abstract" not in self.modifiers:
            self.modifiers.append("abstract")

        assert isinstance(self.context.parent_node, ClassInterfaceDecl)
        self.context.parent_node.methods.append(self)

        if "static" not in self.modifiers:
            self.context.parent_node.instance_methods[self] = len(self.context.parent_node.instance_methods)

    @property
    def param_types(self):
        # a little sus, but here we assume that type linking is already finished
        if self.raw_param_types is None:
            return []
        resolutions = map(self.context.parent_node.resolve_type, self.raw_param_types)
        # print("MethodDecl", self.name, self.raw_param_types, resolutions)
        return [(self.raw_param_types[i] if r is None else r.name) for i, r in enumerate(resolutions)]

    def signature(self):
        return self.name + "^" + ",".join(self.param_types)

    def sym_id(self):
        return self.name + "^" + ",".join(self.raw_param_types)


class LocalVarDecl(Symbol):
    node_type = "local_var_decl"

    def __init__(self, context, name, var_type, meta):
        super().__init__(context, name)
        self.sym_type = var_type
        self.meta = meta

    @property
    def resolved_sym_type(self) -> SymbolType:
        # assumes type linking is finished
        parent = self.context.parent_node.context.parent_node
        assert isinstance(parent, ClassInterfaceDecl)
        return parent.resolve_type(self.sym_type)
