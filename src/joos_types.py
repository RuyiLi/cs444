from __future__ import annotations

from typing import List, Optional

import context as C

PRIMITIVE_TYPES = {"byte", "short", "int", "char", "void", "boolean", "void"}
NUMERIC_TYPES = {"byte", "short", "int", "char"}

VALID_PRIMITIVE_CONVERSIONS_WIDENING = dict(
    byte={"short", "int", "long", "float", "double"},
    short={"int", "long", "float", "double"},
    char={"int", "long", "float", "double"},
    int={"long", "float", "double"},
    long={"float", "double"},
    float={"double"},
)

VALID_PRIMITIVE_CONVERSIONS_NARROWING = dict(
    byte={"char"},
    short={"byte", "char"},
    char={"byte", "short"},
    int={"byte", "short", "char"},
    long={"byte", "short", "char", "int"},
    float={"byte", "short", "char", "int", "long"},
    double={"byte", "byte", "short", "char", "int", "long", "float"},
)


def is_primitive_type(type_name: SymbolType | str):
    name = type_name.name if isinstance(type_name, PrimitiveType) else type_name
    return name in PRIMITIVE_TYPES


def is_numeric_type(type_name: SymbolType | str):
    name = type_name.name if isinstance(type_name, PrimitiveType) else type_name
    return name in NUMERIC_TYPES


class SymbolType:
    node_type: str

    def __init__(self, name: str):
        self.name = name


class PrimitiveType(SymbolType):
    node_type = "primitive_type"

    def __init__(self, name: str):
        assert name in PRIMITIVE_TYPES
        super().__init__(name)

    def __eq__(self, other):
        return self.name == other

    def __str__(self):
        return f"PrimitiveType({self.name})"

    def __repr__(self):
        return f"PrimitiveType({self.name})"


class ReferenceType(SymbolType):
    node_type = "reference_type"
    static: bool

    def __init__(self, type_decl: C.ClassInterfaceDecl, static=False):
        self.name = type_decl.name
        self.referenced_type = type_decl
        self.static = static

    def __str__(self):
        return f"ReferenceType({self.name})"

    def __repr__(self):
        return f"ReferenceType({self.name})"

    def resolve_field(self, field_name: str, accessor: C.ClassInterfaceDecl) -> Optional[C.FieldDecl]:
        return self.referenced_type.resolve_field(field_name, accessor, self.static)

    def resolve_method(
        self, method_name: str, argtypes: List[str], accessor: C.ClassInterfaceDecl, static=False
    ) -> Optional[C.MethodDecl]:
        return self.referenced_type.resolve_method(method_name, argtypes, accessor, static)


class ArrayType(ReferenceType):
    node_type = "array_type"

    def __init__(self, element_type: SymbolType):
        self.name = f"{element_type.name}[]"
        self.referenced_type = element_type

    def resolve_field(self, field_name: str, accessor, static=False) -> Optional[C.FieldDecl]:
        if field_name == "length":
            # hardcode builtin property length for array types
            fake_context = C.Context(None, C.ClassDecl(None, None, [], [], [], []), None)
            sym = C.FieldDecl(fake_context, "length", ["public", "final"], "int", None)
            return sym
        return None

    def resolve_method(
        self, method_name: str, argtypes: List[str], accessor: C.ClassInterfaceDecl, static=False
    ) -> Optional[C.MethodDecl]:
        return None


class NullReference(ReferenceType):
    node_type = "null_reference"

    def __init__(self):
        self.name = "null"
        self.referenced_type = "null"

    def resolve_field(self, field_name: str, accessor: C.ClassInterfaceDecl) -> Optional[C.FieldDecl]:
        return None

    def resolve_method(
        self, method_name: str, argtypes: List[str], accessor: C.ClassInterfaceDecl, static=False
    ) -> Optional[C.MethodDecl]:
        return None


def assignable(s: SymbolType, t: SymbolType, type_decl: C.ClassInterfaceDecl):
    "Returns true if s is assignable to t."

    if s.name == t.name:
        return True

    if is_primitive_type(s) != is_primitive_type(t):
        return False

    if is_primitive_type(s):
        # s and t are both primitive types
        return t.name in VALID_PRIMITIVE_CONVERSIONS_WIDENING[s.name]

    # s and t are both reference types

    if t.name == "java.lang.Object" or s.name == "null":
        return True

    if t.name == "null":
        return False

    assert isinstance(s, ReferenceType)
    assert isinstance(t, ReferenceType)

    ss, tt = s.referenced_type, t.referenced_type

    if isinstance(s, ArrayType):
        if isinstance(tt, C.InterfaceDecl):
            return t.name == "java.lang.Cloneable" or t.name == "java.io.Serializable"

        if isinstance(t, ArrayType):
            s_type = type_decl.resolve_type(s.name[:-2])
            t_type = type_decl.resolve_type(t.name[:-2])

            if all(map(is_primitive_type, [s_type, t_type])):
                return s_type == t_type

            if all(isinstance(ty, ReferenceType) for ty in [s_type, t_type]):
                return assignable(s_type, t_type, type_decl)

        return False

    if isinstance(ss, C.ClassDecl):
        if isinstance(tt, C.ClassDecl):
            return ss.is_subclass_of(t.name)

        return ss.implements_interface(t.name)

    if isinstance(ss, C.InterfaceDecl) and isinstance(tt, C.InterfaceDecl):
        return ss.is_subclass_of(t.name)

    return False


def castable(s: SymbolType, t: SymbolType, type_decl: C.ClassInterfaceDecl):
    if s.name == t.name:
        return True

    if is_primitive_type(s) != is_primitive_type(t):
        return False

    if is_primitive_type(s):
        # s and t are both primitive types
        return (
            t.name in VALID_PRIMITIVE_CONVERSIONS_WIDENING[s.name]
            or t.name in VALID_PRIMITIVE_CONVERSIONS_NARROWING[s.name]
        )

    for a, b in (s, t), (t, s):
        if assignable(a, b, type_decl):
            return True

    assert isinstance(s, ReferenceType)
    assert isinstance(t, ReferenceType)

    ss, tt = s.referenced_type, t.referenced_type

    for a, b in (ss, tt), (tt, ss):
        if isinstance(a, C.InterfaceDecl):
            if isinstance(b, C.InterfaceDecl) or (isinstance(b, C.ClassDecl) and "final" not in b.modifiers):
                return True

    return False
