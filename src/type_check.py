import logging

from lark import ParseTree, Token, Tree
from context import (
    ArrayType,
    ClassDecl,
    ClassInterfaceDecl,
    Context,
    FieldDecl,
    InterfaceDecl,
    LocalVarDecl,
    NullReference,
    SemanticError,
    PrimitiveType,
    Symbol,
    MethodDecl,
    ReferenceType,
)

from build_environment import extract_name, get_tree_token, get_modifiers
from name_disambiguation import get_enclosing_type_decl
from type_link import is_primitive_type, get_prefixes


NUMERIC_TYPES = {"byte", "short", "int", "char"}


def get_enclosing_decl(context: Context, decl_type: Symbol):
    while context and not isinstance(context.parent_node, decl_type):
        context = context.parent
    if context is None:
        return None
    return context.parent_node


def is_static_context(context: Context):
    if context.is_static:
        return True
    function_decl = get_enclosing_decl(context, MethodDecl)
    if function_decl is not None:
        return "static" in function_decl.modifiers
    field_decl = get_enclosing_decl(context, FieldDecl)
    return field_decl is not None and "static" in field_decl.modifiers


def is_numeric_type(type_name: Symbol | str):
    # we prolly need to clean up these random helper functions
    if isinstance(type_name, PrimitiveType):
        type_name = type_name.name
    return type_name in NUMERIC_TYPES


def type_check(context: Context):
    for child_context in context.children:
        parse_node(child_context.tree, child_context)
        type_check(child_context)


def extract_type(tree: ParseTree | Token):
    if isinstance(tree, Token):
        # primitive
        return tree.value
    elif tree.data == "array_type":
        return extract_type(tree.children[0]) + "[]"
    elif tree.data == "type_name":
        return extract_name(tree)
    return extract_type(tree.children[0])


def parse_node(tree: ParseTree, context: Context):
    match tree.data:
        case "constructor_declaration" | "method_declaration":
            # Nested, ignore
            pass

        case "field_declaration":
            type_decl = get_enclosing_type_decl(context)
            modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))

            type_tree = next(tree.find_data("type"))
            type_name = extract_type(type_tree)
            field_type = type_decl.resolve_name(type_name)

            rhs = next(tree.find_data("var_initializer"), None)
            if rhs is not None:
                static_context = Context(
                    context.parent,
                    context.parent_node,
                    context.tree,
                    "static" in modifiers,
                )
                rhs_type = resolve_expression(rhs.children[0], static_context)
                if not assignable(rhs_type, field_type, type_decl):
                    raise SemanticError(f"Cannot assign type {rhs_type.name} to {field_type.name}")

        case "local_var_declaration":
            # print(tree)
            var_name = get_tree_token(tree, "var_declarator_id", "IDENTIFIER")
            symbol = context.resolve(f"{LocalVarDecl.node_type}^{var_name}")
            expr = next(tree.find_data("var_initializer"), None).children[0]

            assert isinstance(symbol, LocalVarDecl)
            assert isinstance(expr, Tree)

            # Get type
            initialized_expr_type = resolve_expression(expr, context)
            type_decl = get_enclosing_type_decl(context)

            # Check if assignable
            if not assignable(initialized_expr_type, symbol.resolved_sym_type, type_decl):
                raise SemanticError(f"Cannot assign type {initialized_expr_type.name} to {symbol.sym_type}")

        case "statement":
            child = tree.children[0]
            scope_stmts = ["block", "if_st", "if_else_st", "for_st", "while_st"]

            if isinstance(child, Tree) and child.data not in scope_stmts:
                parse_node(child, context)

        case "assignment" | "method_invocation" | "field_access" | "array_access" | "expr":
            return resolve_expression(tree, context)

        case _:
            for child in tree.children:
                if isinstance(child, Tree):
                    parse_node(child, context)


def resolve_token(token: Token, context: Context):
    match token.type:
        case "INTEGER_L":
            return PrimitiveType("int")
        case "BOOLEAN_L":
            return PrimitiveType("boolean")
        case "char_l":
            return PrimitiveType("char")
        case "string_l":
            return PrimitiveType("String")
        case "NULL":
            return NullReference()
        case "THIS_KW":
            symbol = get_enclosing_type_decl(context)
            if symbol is None:
                raise SemanticError("Keyword 'this' found without an enclosing class.")
            if is_static_context(context):
                raise SemanticError("Keyword 'this' found in static context.")
            return symbol
        case "INSTANCEOF_KW":
            return PrimitiveType("instanceof")
        case "LT_EQ":
            return PrimitiveType("<=")
        case "GT_EQ":
            return PrimitiveType(">=")
        case "LOGICAL_AND":
            return PrimitiveType("&&")
        case "LOGICAL_OR":
            return PrimitiveType("||")
        case "EAGER_AND":
            return PrimitiveType("&")
        case "EAGER_OR":
            return PrimitiveType("|")
        case "EQ":
            return PrimitiveType("==")
        case "NOT_EQ":
            return PrimitiveType("!=")
        case x:
            raise SemanticError(f"Unknown token {x}")


def resolve_bare_refname(name: str, context: Context) -> Symbol:
    # resolves a refname with no dots

    # if None, then we're at the class or ctor level (where we dont care about static)
    type_decl = get_enclosing_type_decl(context)

    if name == "this":
        if is_static_context(context):
            raise SemanticError("Keyword 'this' found in static context.")
        return type_decl

    symbol = context.resolve(f"{LocalVarDecl.node_type}^{name}")
    if not is_static_context(context):
        # disallow implicit this in static context
        # assume no static imports
        symbol = symbol or context.resolve(f"{FieldDecl.node_type}^{name}")
    symbol = symbol or type_decl.resolve_name(name)

    if symbol is None:
        raise SemanticError(f"Name '{name}' could not be resolved in expression.")

    # default to symbol itself (not localvar/field)
    return getattr(symbol, "resolved_sym_type", ReferenceType(symbol))


def resolve_refname(name: str, context: Context):
    # assert non primitive type?
    type_decl = get_enclosing_type_decl(context)

    ref_type = None
    for prefix in reversed(get_prefixes(name)):
        symbol = type_decl.resolve_name(prefix)
        if symbol is not None:
            # fully qualified name
            ref_type = ReferenceType(symbol)
            name = name[len(prefix) :]
            break

    refs = name.split(".")
    if refs[0] == "":
        refs.pop(0)

    if ref_type is None:
        ref_type = resolve_bare_refname(refs[0], context)
        for i in range(1, len(refs)):
            ref_type = ref_type.resolve_field(refs[i]).resolved_sym_type
    else:
        for ref in refs:
            ref_type = ref_type.resolve_field(ref).resolved_sym_type

    return ref_type


VALID_PRIMITIVE_CONVERSIONS_WIDENING = dict(
    byte={"short", "int", "long", "float", "double"},
    short={"int", "long", "float", "double"},
    char={"int", "long", "float", "double"},
    int={"long", "float", "double"},
    long={"float", "double"},
    float={"double"},
)

VALID_PRIMITIVE_CONVERSIONS_SHORTENING = dict(
    byte={"char"},
    short={"byte", "char"},
    char={"byte", "short"},
    int={"byte", "short", "char"},
    long={"byte", "short", "char", "int"},
    float={"byte", "short", "char", "int", "long"},
    double={"byte", "byte", "short", "char", "int", "long", "float"},
)


def assignable(s: Symbol, t: Symbol, type_decl: ClassInterfaceDecl):
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

    if s.node_type == ClassDecl.node_type:
        match t.node_type:
            case ClassDecl.node_type:
                return s.is_subclass_of(t.name)
            case InterfaceDecl.node_type:
                return s.implements_interface(t.name)

    if s.node_type == InterfaceDecl.node_type:
        match t.node_type:
            case InterfaceDecl.node_type:
                return s.is_subclass_of(t.name)

    if s.node_type == ArrayType.node_type:
        match t.node_type:
            case InterfaceDecl.node_type:
                return t.name == "java.lang.Cloneable" or t.name == "java.io.Serializable"
            case ArrayType.node_type:
                s_type = type_decl.resolve_name(s.name[:-2])
                t_type = type_decl.resolve_name(t.name[:-2])

                if all(map(is_primitive_type, [s_type, t_type])):
                    return s_type == t_type
                elif all(isinstance(ty, ClassInterfaceDecl) for ty in [s_type, t_type]):
                    return assignable(s_type, t_type, type_decl)
                else:
                    return False

    return False


def castable(s: Symbol, t: Symbol, type_decl: ClassInterfaceDecl):
    if assignable(s, t, type_decl) or assignable(t, s, type_decl):
        return True

    for a, b in (s, t), (t, s):
        if a.node_type == InterfaceDecl.node_type:
            if b.node_type == InterfaceDecl.node_type or (
                b.node_type == ClassDecl.node_type and "final" not in b.modifiers
            ):
                return True

    return False


def resolve_expression(tree: ParseTree | Token, context: Context) -> Symbol | None:
    """
    Resolves the type of an expression tree.
    TODO fix arraytype
    """

    if isinstance(tree, Token):
        return resolve_token(tree, context)

    match tree.data:
        case "expr":
            assert len(tree.children) == 1
            return resolve_expression(tree.children[0], context)

        case "class_instance_creation":
            new_type = extract_name(tree.children[1])
            ref_type = resolve_refname(new_type, context)
            assert isinstance(ref_type, ReferenceType)
            return ref_type.referenced_type

        case "array_creation_expr":
            array_type = tree.children[1]
            if is_primitive_type(array_type):
                return ArrayType(f"{array_type}[]")

            type_name = extract_name(tree.children[1])
            symbol = get_enclosing_type_decl(context).type_names.get(type_name)

            if symbol is None:
                raise SemanticError(f"Type name '{type_name}' could not be resolved.")
            return ArrayType(f"{symbol.name}[]")

        case "mult_expr":
            left_type, right_type = map(lambda c: resolve_expression(c, context), tree.children)
            if not is_numeric_type(left_type) or not is_numeric_type(right_type):
                raise SemanticError(
                    f"Cannot use operands of type {left_type},{right_type} in mult expression"
                )

            # Binary numeric promotion into int
            return PrimitiveType("int")

        case "add_expr":
            left_type, right_type = map(lambda c: resolve_expression(c, context), tree.children)

            if left_type.name == "java.lang.String":
                return left_type
            if right_type.name == "java.lang.String":
                return right_type

            if not is_numeric_type(left_type) or not is_numeric_type(right_type):
                raise SemanticError(f"Cannot use operands of type {left_type},{right_type} in add expression")

            # Binary numeric promotion into int
            return PrimitiveType("int")

        case "sub_expr":
            left_type, right_type = map(lambda c: resolve_expression(c, context), tree.children)

            if not is_numeric_type(left_type) or not is_numeric_type(right_type):
                raise SemanticError(f"Cannot use operands of type {left_type},{right_type} in add expression")

            # Binary numeric promotion into int
            return PrimitiveType("int")

        case "rel_expr":
            operands = list(map(lambda c: resolve_expression(c, context), tree.children))
            op = None

            if len(operands) == 3:
                left_type, op, right_type = operands
            else:
                left_type, right_type = operands

            if op == "instanceof":
                if not (
                    left_type.name == "null"
                    or isinstance(left_type, ClassDecl)
                    or isinstance(left_type, ArrayType)
                ):
                    raise SemanticError(
                        f"Left side of instanceof must be a reference type or the null type (found {left_type})"
                    )
            else:
                if not is_numeric_type(left_type) or not is_numeric_type(right_type):
                    raise SemanticError(
                        f"Cannot use operands of type {left_type},{right_type} in relational expression"
                    )

            return PrimitiveType("boolean")

        case "eq_expr":
            left_type, _, right_type = map(lambda c: resolve_expression(c, context), tree.children)

            if not (
                all(map(is_numeric_type, [left_type, right_type]))
                or all(t.name == "boolean" for t in [left_type, right_type])
                or all(
                    isinstance(t, ClassInterfaceDecl) or isinstance(t, NullReference)
                    for t in [left_type, right_type]
                )
            ):
                raise SemanticError(
                    f"Cannot use operands of type {left_type},{right_type} in equality expression"
                )

            return PrimitiveType("boolean")

        case "eager_and_expr" | "eager_or_expr" | "and_expr" | "or_expr":
            left_type, _, right_type = map(lambda c: resolve_expression(c, context), tree.children)

            if left_type.name != "boolean" or right_type.name != "boolean":
                raise SemanticError(
                    f"Cannot use operands of type {left_type},{right_type} (must be boolean) in and/or expression"
                )

            return PrimitiveType("boolean")

        case "expression_name" | "type_name":
            name = extract_name(tree)
            return resolve_refname(name, context)

        case "field_access":
            left, field_name = tree.children
            left_type = resolve_expression(left, context)
            field = left_type.resolve_field(field_name)
            return field.resolved_sym_type

        case "method_invocation":
            type_decl = get_enclosing_type_decl(context)

            if tree.children[0].data == "method_name":
                # method_name ( ... )
                invocation_name = extract_name(tree.children[0])
                *ref_name, method_name = invocation_name.split(".")

                if ref_name:
                    # assert non primitive type?
                    ref_name = ".".join(ref_name)
                    # if (ref_type := type_decl.resolve_name(ref_name)) is not None:
                    #     # check if it resolves to a type (static)
                    #     is_static_call = True
                    # else:
                    ref_type = resolve_refname(ref_name, context)
                else:
                    # assume no static imports
                    if is_static_context(context):
                        raise SemanticError(
                            f"No implicit this in static context (attempting to invoke {method_name})"
                        )
                    ref_type = type_decl
            else:
                # lhs is expression
                # TODO handle case where lhs resolves to a type? (static)
                left, method_name = tree.children
                ref_type = resolve_expression(left, context)

            # print(ref_name, ref_type)
            if is_primitive_type(ref_type):
                raise SemanticError(f"Cannot call method {method_name} on simple type {ref_type}")

            arg_list = next(tree.find_data("argument_list"), None)
            if arg_list is None:
                arg_types = []
            else:
                arg_types = map(lambda c: resolve_expression(c, context), arg_list.children)
                arg_types = [arg_type.name for arg_type in arg_types]
            method = ref_type.resolve_method(method_name, arg_types)

            # if is_static_call and "static" not in method.modifiers:
            #     raise SemanticError(f"Cannot statically call non-static method {method_name}")

            # if not is_static_call and "static" in method.modifiers:
            #     raise SemanticError(f"Cannot non-statically call static method {method_name}")

            return method.return_symbol

        case "unary_negative_expr":
            expr_type = resolve_expression(tree.children[0], context)
            if not is_numeric_type(expr_type):
                raise SemanticError(f"Cannot use operand of type {expr_type} in unary negative expression")
            return expr_type

        case "unary_complement_expr":
            expr_type = resolve_expression(tree.children[0], context)
            if expr_type != "boolean":
                raise SemanticError(f"Cannot use operand of type {expr_type} in unary complement expression")
            return expr_type

        case "array_access":
            assert len(tree.children) == 2
            ref_array, index = tree.children

            index_type = resolve_expression(index, context)
            if not is_numeric_type(index_type):
                raise SemanticError(f"Array index must be an integer type, not {index_type}")

            array_type = resolve_expression(ref_array, context)
            if not isinstance(array_type, ArrayType):
                raise SemanticError(f"Cannot index non-array type {array_type}")

            type_decl = get_enclosing_type_decl(context)
            return type_decl.resolve_name(array_type.name[:-2])

        case "cast_expr":
            type_decl = get_enclosing_type_decl(context)
            if len(tree.children) == 2:
                cast_type, cast_target = tree.children
                type_name = extract_type(cast_type)
                cast_type = type_decl.resolve_name(type_name)
            else:
                cast_type, square_brackets, cast_target = tree.children
                assert square_brackets.value == "[]"
                cast_type = type_decl.resolve_name(cast_type.value + "[]")

            source_type = resolve_expression(cast_target, context)
            if is_primitive_type(source_type) and isinstance(source_type, str):
                source_type = PrimitiveType(source_type)

            if castable(source_type, cast_type, type_decl):
                return cast_type

            raise SemanticError(f"Cannot cast type {source_type.name} to {cast_type.name}")

        case "assignment":
            lhs = next(tree.find_data("lhs"))
            lhs = resolve_expression(lhs.children[0], context)
            expr = resolve_expression(tree.children[1], context)
            # print(99, lhs, expr)
            if not assignable(expr, lhs, get_enclosing_type_decl(context)):
                raise SemanticError(f"Cannot assign type {expr} to {lhs}")

            # if lhs != expr:
            #     if is_numeric_type(lhs):
            #         if not (
            #             (lhs == "int" and expr in ["char", "byte", "short"])
            #             or (lhs == "short" and expr == "byte")
            #         ):
            #             raise SemanticError(f"Can't convert type {expr} to {lhs} in assignment.")
            #     else:
            #         if is_primitive_type(expr):
            #             raise SemanticError(f"Can't convert type {expr} to {lhs} in assignment.")

            #         if isinstance(expr, ArrayType):
            #             # allow a widening conversion for reference types
            #             if lhs not in ["java.lang.Object", "java.lang.Cloneable", "java.io.Serializable"]:
            #                 pass

            return expr

        case "char_l":
            return PrimitiveType("char")

        case "string_l":
            return context.resolve(f"{ClassInterfaceDecl.node_type}^java.lang.String")

        case x:
            print("assdsd", x)
            logging.warn(f"Unknown tree data {x}")
