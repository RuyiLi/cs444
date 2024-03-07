import logging
import copy

from lark import ParseTree, Token, Tree
from lark.tree import Meta
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
    validate_field_access,
)

from build_environment import extract_name, get_tree_token, get_modifiers, get_formal_params
from name_disambiguation import get_enclosing_type_decl
from type_link import is_primitive_type, get_simple_name, get_prefixes

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
    elif tree.data == "reference_type":
        return extract_name(tree)
    return extract_type(tree.children[0])


def get_argument_types(context: Context, tree: Tree, meta: Meta = None):
    arg_lists = list(tree.find_data("argument_list"))
    arg_types = []
    if arg_lists:
        # get the last one, because find_data fetches bottom-up
        target = arg_lists[-1].children
        arg_types = [resolve_expression(c, context, meta).name for c in target]
    return arg_types


def parse_node(tree: ParseTree, context: Context):
    match tree.data:
        case "constructor_declaration" | "method_declaration":
            # Nested, ignore
            pass

        case "class_body":
            type_decl = get_enclosing_type_decl(context)
            if type_decl.name == "java.lang.Object":
                return

            for extend in type_decl.extends:
                parent: ClassDecl = type_decl.resolve_name(extend)
                if not any(len(ctor.param_types) == 0 for ctor in parent.constructors):
                    raise SemanticError(
                        f"Class {parent.name} is subclassed, and thus must have a zero-argument constructor"
                    )

            for child in tree.children:
                if isinstance(child, Tree):
                    parse_node(child, context)

        case "return_st":
            type_decl = get_enclosing_type_decl(context)
            method_decl = get_enclosing_decl(context, MethodDecl)
            if method_decl.return_type == "void":
                if len(tree.children) > 1:
                    raise SemanticError(f"Method {method_decl.name} must not return a value")
                return

            return_type = resolve_expression(tree.children[1], context)
            if not assignable(return_type, method_decl.return_symbol, type_decl):
                raise SemanticError(
                    f"Cannot return type {return_type.name} from method {method_decl.name} (expecting {method_decl.return_type})"
                )

        case "field_declaration":
            type_decl = get_enclosing_type_decl(context)
            modifiers = list(map(lambda m: m.value, get_modifiers(tree.children)))

            type_tree = next(tree.find_data("type"))
            type_name = extract_type(type_tree)
            field_type = type_decl.resolve_name(type_name)

            rhs = next(tree.find_data("var_initializer"), None)
            if rhs is not None:
                static_context = copy.copy(context)
                static_context.is_static = "static" in modifiers
                rhs_type = resolve_expression(rhs.children[0], static_context, tree.meta, field=True)
                if not assignable(rhs_type, field_type, type_decl):
                    raise SemanticError(f"Cannot assign type {rhs_type.name} to {field_type.name}")

                # only allow self ref if appears as LHS in assignment expr
                my_name = get_tree_token(tree, "var_declarator_id", "IDENTIFIER")
                for expr in rhs.find_data("lhs"):
                    if expr.children[0].data == "expression_name":
                        name = extract_name(expr.children[0])
                        if name == my_name:
                            return

                for expr in rhs.find_data("expression_name"):
                    name = extract_name(expr)
                    sym = context.resolve(f"{FieldDecl.node_type}^{name}")
                    if sym and sym.name == my_name:
                        raise SemanticError("Self-reference in field declaration")

        case "class_instance_creation":
            type_decl = get_enclosing_type_decl(context)
            arg_types = get_argument_types(context, tree)
            formal_param_types = []
            for constructor in type_decl.constructors:
                formal_param_types, _ = get_formal_params(constructor.context.tree)

            if len(formal_param_types) != len(arg_types):
                raise SemanticError(
                    f"constructor declaration {formal_param_types} differs in argument count from class declaration {arg_types}"
                )

            for arg_type, formal_param_type in zip(arg_types, formal_param_types):
                if get_simple_name(arg_type) != get_simple_name(formal_param_type):
                    raise SemanticError(
                        f"constructor declaration {formal_param_types} differs in type from class declaration {arg_types}"
                    )

            resolve_expression(tree, context)

        case "local_var_declaration":
            # print(tree)
            var_name = get_tree_token(tree, "var_declarator_id", "IDENTIFIER")
            symbol = context.resolve(f"{LocalVarDecl.node_type}^{var_name}")
            expr = next(tree.find_data("var_initializer"), None).children[0]

            assert isinstance(symbol, LocalVarDecl)
            assert isinstance(expr, Tree)

            # Get type
            initialized_expr_type = resolve_expression(expr, context, tree.meta)
            type_decl = get_enclosing_type_decl(context)

            # Check if assignable
            if not assignable(initialized_expr_type, symbol.resolved_sym_type, type_decl):
                raise SemanticError(f"Cannot assign type {initialized_expr_type.name} to {symbol.sym_type}")

        case "statement":
            child = tree.children[0]
            scope_stmts = ["block", "if_st", "if_else_st", "for_st", "while_st"]

            if isinstance(child, Tree) and child.data not in scope_stmts:
                parse_node(child, context)

        case (
            "if_st"
            | "if_else_st"
            | "if_else_st_no_short_if"
            | "while_st"
            | "while_st_no_short_if"
            | "for_st"
        ):
            expr = next(filter(lambda c: isinstance(c, Tree) and c.data == "expr", tree.children), None)

            # For statements are allowed to have an optional expression
            if expr is None:
                return

            condition_type = resolve_expression(expr, context)

            if condition_type.name != "boolean":
                raise SemanticError(
                    f"If/While/For condition must have type boolean (found {condition_type.name})"
                )

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
    if symbol is None and not is_static_context(context):
        # disallow implicit this in static context
        # assume no static imports
        symbol = type_decl.resolve_field(name, type_decl)
    symbol = symbol or type_decl.resolve_name(name)

    if symbol is None:
        raise SemanticError(f"Name '{name}' could not be resolved in expression.")

    # default to symbol itself (not localvar/field)
    return getattr(symbol, "resolved_sym_type", ReferenceType(symbol))


def parse_ambiguous_name_with_types(
    context, ids, meta: Meta = None, get_final_modifier=False, arg_types=None, field=False
):
    last_id = ids[-1]
    enclosing_type_decl = get_enclosing_type_decl(context)

    # print("parsing amb name", ids, field)

    if len(ids) == 1:
        symbol = context.resolve(f"{LocalVarDecl.node_type}^{last_id}") or context.resolve(
            f"{FieldDecl.node_type}^{last_id}"
        )
        if symbol is not None:
            if meta is not None:
                check_forward_reference(last_id, context, meta, field)
            return ("expression_name", symbol)
        elif type_name := enclosing_type_decl.resolve_name(last_id):
            return ("type_name", type_name)
        else:
            return ("package_name", None)
    else:
        result, pre_symbol = parse_ambiguous_name_with_types(
            context, ids[:-1], meta, get_final_modifier, arg_types, field
        )
        pre_name = ".".join(ids[:-1])

        if result == "package_name":
            if type_name := enclosing_type_decl.resolve_name(".".join(ids)):
                return ("type_name", type_name)
            else:
                return ("package_name", None)

        elif result == "type_name":
            if symbol := pre_symbol.resolve_method(last_id, arg_types or [], enclosing_type_decl, True):
                return ("expression_name", symbol)

            if symbol := pre_symbol.resolve_field(last_id, enclosing_type_decl, True):
                return ("expression_name", symbol)

            raise SemanticError(f"'{last_id}' is not the name of a field or method in type '{pre_name}'.")

        elif result == "expression_name":
            symbol_type = getattr(pre_symbol, "resolved_sym_type", ReferenceType(pre_symbol))
            if not isinstance(symbol_type, ArrayType) and (
                symbol := symbol_type.resolve_method(last_id, arg_types or [], enclosing_type_decl)
            ):
                return ("expression_name", symbol)

            if symbol := symbol_type.resolve_field(last_id, enclosing_type_decl):
                if get_final_modifier and isinstance(symbol_type, ArrayType) and symbol.name == "length":
                    raise SemanticError("A final field cannot be assigned to.")

                return ("expression_name", symbol)

            raise SemanticError(
                f"'{last_id}' is not the name of a field or method in expression '{pre_name}' of type '{symbol_type}'."
            )

        else:
            raise SemanticError("how did you get here")


def check_forward_reference(name: str, context: Context, meta: Meta, field: bool):
    if declare := context.resolve(f"{FieldDecl.node_type}^{name}"):
        if (
            field
            and "static" not in declare.modifiers
            and declare.meta.line > meta.line
            or (declare.meta.line == meta.line and declare.meta.column >= meta.column)
        ):
            raise SemanticError(
                "Initializer of non-static field cannot use a non-static field declared later without explicit 'this'."
            )

    elif declare := context.resolve(f"{LocalVarDecl.node_type}^{name}"):
        if declare.meta.line > meta.line or (
            declare.meta.line == meta.line and declare.meta.column >= meta.column
        ):
            raise SemanticError(f"Local var {name} cannot be used before it was declared.")


def resolve_refname(
    name: str, context: Context, meta: Meta = None, get_final_modifier=False, arg_types=None, field=False
):
    refs = name.split(".")
    expr_id = refs[-1]

    # print("resolving", refs, meta)

    if len(refs) == 1:
        symbol = context.resolve(f"{LocalVarDecl.node_type}^{expr_id}")

        if symbol is None and not is_static_context(context):
            type_decl = get_enclosing_type_decl(context)
            symbol = context.resolve(f"{FieldDecl.node_type}^{expr_id}") or type_decl.resolve_field(
                expr_id, type_decl
            )

        if symbol is None:
            raise SemanticError(f"Couldn't resolve symbol {refs}")

        if meta is not None:
            check_forward_reference(name, context, meta, field)

        return getattr(symbol, "resolved_sym_type", ReferenceType(symbol))
    else:
        name_type, symbol = parse_ambiguous_name_with_types(
            context, refs, meta, get_final_modifier, arg_types, field
        )
        return getattr(symbol, "resolved_sym_type", ReferenceType(symbol))


def resolve_refname2(name: str, context: Context, meta: Meta = None, get_final_modifier=False):
    # assert non primitive type?
    final_modifier = False
    type_decl = get_enclosing_type_decl(context)
    ref_type = None
    for prefix in reversed(get_prefixes(name)):
        symbol = type_decl.resolve_name(prefix)
        if symbol is not None:
            # fully qualified name
            ref_type = ReferenceType(symbol)
            ref_type.name = symbol.name
            name = name[len(prefix) :]
            break

    refs = name.split(".")
    if refs[0] == "":
        refs.pop(0)

    start_idx = 0
    if ref_type is None:
        ref_type = resolve_bare_refname(refs[0], context)
        start_idx = 1

    for i in range(start_idx, len(refs)):
        old_ref_type = ref_type
        ref_type = ref_type.resolve_field(refs[i], type_decl).resolved_sym_type

        if (
            get_final_modifier
            and isinstance(old_ref_type, ArrayType)
            and ref_type == "int"
            and refs[i] == "length"
        ):
            final_modifier = True

    if get_final_modifier and final_modifier:
        return (ref_type, final_modifier)
    return ref_type


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

    if assignable(s, t, type_decl) or assignable(t, s, type_decl):
        return True

    for a, b in (s, t), (t, s):
        if a.node_type == InterfaceDecl.node_type:
            if b.node_type == InterfaceDecl.node_type or (
                b.node_type == ClassDecl.node_type and "final" not in b.modifiers
            ):
                return True

    return False


def resolve_expression(
    tree: ParseTree | Token,
    context: Context,
    meta: Meta = None,
    get_final_modifier: bool = False,
    field: bool = False,
) -> Symbol | None:
    """
    Resolves the type of an expression tree.
    TODO fix arraytype
    """

    if isinstance(tree, Token):
        return resolve_token(tree, context)

    match tree.data:
        case "expr":
            assert len(tree.children) == 1
            return resolve_expression(tree.children[0], context, meta, field=field)

        case "class_instance_creation":
            new_type = extract_name(tree.children[1])
            ref_type = resolve_refname2(new_type, context).referenced_type

            if "abstract" in ref_type.modifiers:
                raise SemanticError(f"Cannot create object of {ref_type.name} due to abstract class")

            type_decl = get_enclosing_type_decl(context)
            arg_types = get_argument_types(context, tree)

            for constructor in ref_type.constructors:
                # find matching constructor
                ctor_param_names = [param.name for param in constructor.resolved_param_types]
                if ctor_param_names == arg_types:
                    # construction using new keyword is only allowed if
                    # 1) calling class is a subclass of the class being constructed
                    # 2) they are in the same package
                    # print(constructor.modifiers)
                    if "protected" in constructor.modifiers:
                        if not (
                            type_decl.is_subclass_of(ref_type.name) and type_decl.package == ref_type.package
                        ):
                            raise SemanticError(
                                f"Cannot access protected constructor of {ref_type.name} from {type_decl.name}"
                            )
                    return ref_type

            raise SemanticError(f"Constructor {ref_type.name}({arg_types}) not found")

        case "array_creation_expr" | "array_type":
            array_type = tree.children[1 if tree.data == "array_creation_expr" else 0]

            if tree.data == "array_creation_expr":
                size_expr = next(tree.find_data("expr"))
                size_expr_type = resolve_expression(size_expr, context, meta, field=field)

                if not is_numeric_type(size_expr_type):
                    raise SemanticError(
                        f"Size expression of array creation must be a numeric type (found {size_expr_type.name})"
                    )

            if is_primitive_type(array_type):
                return ArrayType(f"{array_type}[]")

            type_name = extract_name(array_type)
            symbol = get_enclosing_type_decl(context).type_names.get(type_name)

            if symbol is None:
                raise SemanticError(f"Type name '{type_name}' could not be resolved.")

            return ArrayType(f"{symbol.name}[]")

        case "mult_expr":
            left_type, right_type = map(
                lambda c: resolve_expression(c, context, meta, field=field), tree.children
            )

            if any(t.name == "void" for t in [left_type, right_type]):
                raise SemanticError("Operand cannot have type void in mult expression")

            if not is_numeric_type(left_type) or not is_numeric_type(right_type):
                raise SemanticError(
                    f"Cannot use operands of type {left_type},{right_type} in mult expression"
                )

            # Binary numeric promotion into int
            return PrimitiveType("int")

        case "add_expr":
            left_type, right_type = map(
                lambda c: resolve_expression(c, context, meta, field=field), tree.children
            )

            if any(t.name == "void" for t in [left_type, right_type]):
                raise SemanticError("Operand cannot have type void in add expression")

            if left_type.name == "java.lang.String":
                return left_type
            if right_type.name == "java.lang.String":
                return right_type

            if not is_numeric_type(left_type) or not is_numeric_type(right_type):
                raise SemanticError(f"Cannot use operands of type {left_type},{right_type} in add expression")

            # Binary numeric promotion into int
            return PrimitiveType("int")

        case "sub_expr":
            left_type, right_type = map(
                lambda c: resolve_expression(c, context, meta, field=field), tree.children
            )

            if any(t.name == "void" for t in [left_type, right_type]):
                raise SemanticError("Operand cannot have type void in subtract expression")

            if not is_numeric_type(left_type) or not is_numeric_type(right_type):
                raise SemanticError(
                    f"Cannot use operands of type {left_type},{right_type} in subtract expression"
                )

            # Binary numeric promotion into int
            return PrimitiveType("int")

        case "rel_expr":
            operands = list(map(lambda c: resolve_expression(c, context, meta, field=field), tree.children))
            op = None

            if len(operands) == 3:
                left_type, op, right_type = operands
            else:
                left_type, right_type = operands

            if any(t.name == "void" for t in [left_type, right_type]):
                raise SemanticError("Operand cannot have type void in relational expression")

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
            left_type, _, right_type = map(
                lambda c: resolve_expression(c, context, meta, field=field), tree.children
            )

            if any(t.name == "void" for t in [left_type, right_type]):
                raise SemanticError("Operand cannot have type void in equality expression")

            if not (
                all(map(is_numeric_type, [left_type, right_type]))
                or all(t.name == "boolean" for t in [left_type, right_type])
                or (
                    all(
                        isinstance(t, ClassInterfaceDecl) or isinstance(t, NullReference)
                        for t in [left_type, right_type]
                    )
                )
                and castable(left_type, right_type, get_enclosing_type_decl(context))
            ):
                raise SemanticError(
                    f"Cannot use operands of type {left_type},{right_type} in equality expression"
                )

            return PrimitiveType("boolean")

        case "eager_and_expr" | "eager_or_expr" | "and_expr" | "or_expr":
            left_type, _, right_type = map(
                lambda c: resolve_expression(c, context, meta, field=field), tree.children
            )

            if any(t.name == "void" for t in [left_type, right_type]):
                raise SemanticError("Operand cannot have type void in and/or expression")

            if left_type.name != "boolean" or right_type.name != "boolean":
                raise SemanticError(
                    f"Cannot use operands of type {left_type},{right_type} (must be boolean) in and/or expression"
                )

            return PrimitiveType("boolean")

        case "type_name":
            name = extract_name(tree)
            return resolve_refname2(name, context, meta, get_final_modifier)

        case "expression_name":
            # expression_name actually handles a lot of the field access cases...
            name = extract_name(tree)
            return resolve_refname(name, context, meta, get_final_modifier, field=field)

        case "field_access":
            left, field_name = tree.children
            left_type = resolve_expression(left, context, meta, field=field)
            type_decl = get_enclosing_type_decl(context)
            field = left_type.resolve_field(field_name, type_decl)
            return field.resolved_sym_type

        case "method_invocation":
            type_decl = get_enclosing_type_decl(context)
            arg_types = None
            if isinstance(tree.children[0], Tree) and tree.children[0].data == "method_name":
                # method_name ( ... )
                invocation_name = extract_name(tree.children[0])
                *ref_name, method_name = invocation_name.split(".")

                if ref_name:
                    # assert non primitive type?
                    ref_name = ".".join(ref_name)
                    ref_type = resolve_refname(
                        invocation_name,
                        context,
                        meta,
                        arg_types=get_argument_types(context, tree, meta),
                        field=field,
                    )

                    if isinstance(ref_type.referenced_type, MethodDecl):
                        return ref_type.referenced_type.return_symbol
                    else:
                        ref_type = resolve_refname2(ref_name, context)
                else:
                    # assume no static imports
                    if is_static_context(context):
                        raise SemanticError(
                            f"No implicit this in static context (attempting to invoke {method_name})"
                        )
                    ref_type = type_decl
            else:
                # lhs is expression
                arg_list = None
                if len(tree.children) == 2:
                    # no args in method invocation
                    left, method_name = tree.children
                    arg_types = []
                else:
                    left, method_name, arg_list = tree.children
                    arg_types = get_argument_types(context, arg_list, meta)
                ref_type = resolve_expression(left, context, meta, field=field)

            if is_primitive_type(ref_type):
                raise SemanticError(f"Cannot call method {method_name} on simple type {ref_type}")

            if arg_types is None:
                arg_types = get_argument_types(context, tree, meta)
            method = ref_type.resolve_method(method_name, arg_types, type_decl)

            if method is None:
                raise SemanticError(f"Method {ref_type.name}.{method_name}({arg_types}) not found")

            return method.return_symbol

        case "unary_negative_expr":
            expr_type = resolve_expression(tree.children[0], context, meta, field=field)

            if expr_type.name == "void":
                raise SemanticError("Operand cannot have type void in unary negative expression")

            if not is_numeric_type(expr_type):
                raise SemanticError("Cannot use operand of type {expr_type} in unary negative expression")
            return expr_type

        case "unary_complement_expr":
            expr_type = resolve_expression(tree.children[0], context, meta, field=field)

            if expr_type.name == "void":
                raise SemanticError("Operand cannot have type void in unary complement expression")

            if expr_type != "boolean":
                raise SemanticError("Cannot use operand of type {expr_type} in unary complement expression")
            return expr_type

        case "array_access":
            assert len(tree.children) == 2
            ref_array, index = tree.children

            index_type = resolve_expression(index, context, meta, field=field)
            if not is_numeric_type(index_type):
                raise SemanticError(f"Array index must be an integer type, not {index_type}")

            array_type = resolve_expression(ref_array, context, meta, field=field)
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

            source_type = resolve_expression(cast_target, context, meta, field=field)
            if is_primitive_type(source_type) and isinstance(source_type, str):
                source_type = PrimitiveType(source_type)

            if castable(source_type, cast_type, type_decl):
                return cast_type

            if source_type.name == "void":
                raise SemanticError("Cast target cannot be of type void")

            raise SemanticError(f"Cannot cast type {source_type.name} to {cast_type.name}")

        case "assignment":
            lhs_tree = next(tree.find_data("lhs")).children[0]
            get_final_modifier = True
            lhs = resolve_expression(
                lhs_tree, context, None, get_final_modifier, field=field
            )  # We allow all left-hand operands, even if non-static and forward
            if isinstance(lhs, tuple):
                raise SemanticError("A final field must not be assigned to")
            expr = resolve_expression(tree.children[1], context, meta or tree.meta, field=field)
            if not assignable(expr, lhs, get_enclosing_type_decl(context)):
                raise SemanticError(f"Cannot assign type {expr} to {lhs}")
            return lhs

        case "char_l":
            return PrimitiveType("char")

        case "string_l":
            return context.resolve(f"{ClassInterfaceDecl.node_type}^java.lang.String")

        case x:
            print("assdsd", x)
            logging.warn(f"Unknown tree data {x}")


[
    Tree(
        Token("RULE", "expr"),
        [
            Tree(
                "reference_type",
                [
                    Tree(
                        Token("RULE", "name"),
                        [
                            Token("IDENTIFIER", "java"),
                            Tree(
                                Token("RULE", "name"),
                                [
                                    Token("IDENTIFIER", "util"),
                                    Tree(Token("RULE", "name"), [Token("IDENTIFIER", "List")]),
                                ],
                            ),
                        ],
                    )
                ],
            )
        ],
    ),
    Tree(
        Token("RULE", "class_instance_creation"),
        [
            Token("NEW_KW", "new"),
            Tree(
                Token("RULE", "type_name"),
                [
                    Tree(
                        Token("RULE", "name"),
                        [
                            Token("IDENTIFIER", "java"),
                            Tree(
                                Token("RULE", "name"),
                                [
                                    Token("IDENTIFIER", "util"),
                                    Tree(Token("RULE", "name"), [Token("IDENTIFIER", "LinkedList")]),
                                ],
                            ),
                        ],
                    )
                ],
            ),
        ],
    ),
]
