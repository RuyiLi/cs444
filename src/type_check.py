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
    MethodDecl,
    SemanticError,
    PrimitiveType,
    Symbol,
)

from build_environment import extract_name, get_tree_token
from name_disambiguation import get_enclosing_type_decl
from type_link import is_primitive_type


NUMERIC_TYPES = {"byte", "short", "int", "char"}


def is_numeric_type(type_name: Symbol | str):
    # we prolly need to clean up these random helper functions
    if isinstance(type_name, PrimitiveType):
        type_name = type_name.name
    return type_name in NUMERIC_TYPES


def type_check(context: Context):
    for child_context in context.children:
        parse_node(child_context.tree, child_context)
        type_check(child_context)


def parse_node(tree: ParseTree, context: Context):
    match tree.data:
        case "constructor_declaration" | "method_declaration":
            # Nested, ignore
            pass

        case "local_var_declaration":
            # print(tree)
            var_name = get_tree_token(tree, "var_declarator_id", "IDENTIFIER")
            symbol = context.resolve(f"{LocalVarDecl.node_type}^{var_name}")
            expr = next(tree.find_data("var_initializer"), None).children[0]

            assert isinstance(symbol, LocalVarDecl)
            assert isinstance(expr, Tree)

            initialized_expr_type = resolve_expression(expr, context)

            if initialized_expr_type is None:
                print(symbol.sym_type)
                print()

        case "statement":
            child = tree.children[0]
            scope_stmts = ["block", "if_st", "if_else_st", "for_st", "while_st"]

            if isinstance(child, Tree) and child.data not in scope_stmts:
                parse_node(child, context)

        case "assignment":
            lhs = next(tree.find_data("lhs"))
            lhs = resolve_expression(lhs.children[0], context)
            expr = resolve_expression(tree.children[1], context)

            if lhs != expr:
                if is_numeric_type(lhs):
                    if not (
                        (lhs == "int" and expr in ["char", "byte", "short"])
                        or (lhs == "short" and expr == "byte")
                    ):
                        raise SemanticError(f"Can't convert type {expr} to {lhs} in assignment.")
                else:
                    if is_primitive_type(expr):
                        raise SemanticError(f"Can't convert type {expr} to {lhs} in assignment.")

                    if isinstance(expr, ArrayType):
                        # allow a widening conversion for reference types
                        if lhs not in ["java.lang.Object", "java.lang.Cloneable", "java.io.Serializable"]:
                            pass

            return expr

        case "method_invocation":
            pass

        case "field_access":
            pass

        case "array_access":
            pass

        case _:
            for child in tree.children:
                if isinstance(child, Tree):
                    parse_node(child, context)


def resolve_token(token: Token, context: Context):
    match token.type:
        case "INTEGER_L":
            return "int"
        case "BOOLEAN_L":
            return "boolean"
        case "char_l":
            return "char"
        case "string_l":
            return "String"
        case "NULL":
            return "null"
        case "THIS_KW":
            symbol = get_enclosing_type_decl(context)
            if symbol is None:
                raise SemanticError("Keyword 'this' found without an enclosing class.")
            return symbol
        case "INSTANCEOF_KW":
            return "instanceof"
        case "LT_EQ":
            return "<="
        case "GT_EQ":
            return ">="
        case x:
            raise SemanticError(f"Unknown token {x}")


def resolve_bare_refname(name: str, context: Context) -> Symbol:
    # resolves a refname with no dots
    if name == "this":
        return get_enclosing_type_decl(context)

    symbol = (
        context.resolve(f"{LocalVarDecl.node_type}^{name}")
        or context.resolve(f"{FieldDecl.node_type}^{name}")
        or get_enclosing_type_decl(context).type_names.get(name)
    )

    if symbol is None:
        raise SemanticError(f"Name '{name}' could not be resolved in expression.")

    # default to symbol itself (not localvar/field)
    return getattr(symbol, "resolved_sym_type", symbol)


def resolve_refname(name: str, context: Context):
    print(name)
    # assert non primitive type?
    symbol = context.resolve(f"{ClassDecl.node_type}^{name}")
    if symbol is not None:
        # fully qualified name
        return symbol

    # foo.bar.baz, this.asdf, x
    refs = name.split(".")
    ref_type = resolve_bare_refname(refs[0], context)
    for i in range(1, len(refs)):
        ref_type = ref_type.resolve_field(refs[i]).resolved_sym_type

    return ref_type


def resolve_expression(tree: ParseTree | Token, context: Context):
    if isinstance(tree, Token):
        return resolve_token(tree, context)

    match tree.data:
        case "expr":
            assert len(tree.children) == 1
            return resolve_expression(tree.children[0], context)

        case "class_instance_creation":
            return get_enclosing_type_decl(context)

        case "array_creation_expr":
            array_type = tree.children[1]
            if is_primitive_type(array_type):
                return f"{array_type}[]"
            else:
                type_name = extract_name(tree.children[1])
                symbol = get_enclosing_type_decl(context).type_names.get(type_name)

                if symbol is None:
                    raise SemanticError(f"Type name '{type_name}' could not be resolved.")
                return f"{symbol.name}[]"

        case "mult_expr":
            left_type, right_type = map(lambda c: resolve_expression(c, context), tree.children)
            if not is_numeric_type(left_type) or not is_numeric_type(right_type):
                raise SemanticError(
                    f"Cannot use operands of type {left_type},{right_type} in mult expression"
                )

            # Binary numeric promotion into int
            return "int"

        case "add_expr":
            left_type, right_type = map(lambda c: resolve_expression(c, context), tree.children)

            if "String" in [left_type, right_type]:
                return "String"

            if not is_numeric_type(left_type) or not is_numeric_type(right_type):
                raise SemanticError(f"Cannot use operands of type {left_type},{right_type} in add expression")

            # Binary numeric promotion into int
            return "int"

        case "sub_expr":
            left_type, right_type = map(lambda c: resolve_expression(c, context), tree.children)

            if not is_numeric_type(left_type) or not is_numeric_type(right_type):
                raise SemanticError(f"Cannot use operands of type {left_type},{right_type} in add expression")

            # Binary numeric promotion into int
            return "int"

        case "rel_expr":
            operands = list(map(lambda c: resolve_expression(c, context), tree.children))
            op = None

            if len(operands) == 3:
                left_type, op, right_type = operands
            else:
                left_type, right_type = operands

            if op == "instanceof":
                if not (left_type == "null" or isinstance(left_type, ClassDecl)):
                    raise SemanticError("Left side of instanceof must be a reference type or the null type")
            else:
                if not is_numeric_type(left_type) or not is_numeric_type(right_type):
                    raise SemanticError(
                        f"Cannot use operands of type {left_type},{right_type} in relational expression"
                    )

            return "boolean"

        case "eq_expr":
            left_type, right_type = map(lambda c: resolve_expression(c, context), tree.children)

            if left_type != right_type and not all(map(is_numeric_type, [left_type, right_type])):
                raise SemanticError(
                    f"Cannot use operands of type {left_type},{right_type} in equality expression"
                )

            return "boolean"

        case "eager_and_expr" | "eager_or_expr" | "and_expr" | "or_expr":
            left_type, right_type = map(lambda c: resolve_expression(c, context), tree.children)

            if left_type != "boolean" or right_type != "boolean":
                raise SemanticError(
                    f"Cannot use operands of type {left_type},{right_type} (must be boolean) in and/or expression"
                )

            return "boolean"

        case "expression_name":
            name = extract_name(tree)
            return resolve_refname(name, context)

        case "field_access":
            expr_name = extract_name(tree)
            if tree.children[0].type == "THIS_KW":
                expr_name = "this." + expr_name
            return resolve_refname(expr_name, context)

        case "method_invocation":
            invocation_name = extract_name(next(tree.find_data("method_name")))
            *ref_name, method_name = invocation_name.split(".")

            type_decl = get_enclosing_type_decl(context)
            if ref_name:
                # assert non primitive type?
                ref_name = ".".join(ref_name)
                ref_type = resolve_refname(ref_name, context)
            else:
                ref_type = type_decl

            arg_list = next(tree.find_data("argument_list"), None)
            if arg_list is None:
                arg_types = []
            else:
                arg_types = map(
                    lambda c: resolve_expression(c, context),
                    arg_list.children,
                )

                # resolve arg list to fully qualified typenames
                # arg_types = map(type_decl.resolve_name, arg_types)
                arg_types = [getattr(arg_type, "name", arg_type) for arg_type in arg_types]
            method = ref_type.resolve_method(method_name, arg_types)

            # if is_static and "static" not in method.modifiers:
            #     raise SemanticError(f"Cannot call non-static method {method_name} from static context")

            return method.return_symbol

        case "unary_negative_expr":
            expr_type = resolve_expression(tree.children[0], context)
            if not is_numeric_type(expr_type):
                raise SemanticError(f"Cannot use operand of type {expr_type} in unary negative expression")
            return expr_type

        case "array_access":
            assert len(tree.children) == 2
            ref_array, index = tree.children

            index_type = resolve_expression(index, context)
            if index_type != "int":
                raise SemanticError(f"Array index must be of type int, not {index_type}")

            # TODO this should probably be a symbol, not a string ending in []?
            array_type = resolve_expression(ref_array, context)
            if not isinstance(array_type, ArrayType):
                raise SemanticError(f"Cannot index non-array type {array_type}")

            return array_type.name[:-2]

        case "char_l":
            return "char"

        case "string_l":
            return "String"

        case x:
            logging.warn(f"Unknown tree data {x}")
