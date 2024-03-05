from lark import ParseTree, Token, Tree
from context import ArrayType, ClassDecl, ClassInterfaceDecl, Context, FieldDecl, InterfaceDecl, LocalVarDecl, SemanticError

from build_environment import extract_name, get_tree_token
from name_disambiguation import get_enclosing_type_decl
from type_link import PRIMITIVE_TYPES

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
            if tree.children[0].children[0].data == "expression_name":
                lhs = resolve_expression(tree.children[0].children[0], context)
            else:
                lhs = parse_node(tree.children[0], context)

            expr = resolve_expression(tree.children[1], context)

            if lhs != expr:
                if lhs in NUMERIC_TYPES:
                    if not ((lhs == "int" and expr in ["char", "byte", "short"]) or
                        (lhs == "short" and expr == "byte")):
                        raise SemanticError(f"Can't convert type {expr} to {lhs} in assignment.")
                else:
                    if expr in PRIMITIVE_TYPES:
                        raise SemanticError(f"Can't convert type {expr} to {lhs} in assignment.")

                    if isinstance(expr, ArrayType):
                        # allow a windening conversion for reference types
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
        case "INSTANCEOF_KW":
            return "instanceof"
        case "LT_EQ":
            return "<="
        case "GT_EQ":
            return ">="
        case x:
            raise SemanticError(f"Unknown token {x}")

NUMERIC_TYPES = ["byte", "short", "int", "char"]

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
            if array_type in PRIMITIVE_TYPES:
                return f"{array_type}[]"
            else:
                type_name = extract_name(tree.children[1])
                symbol = get_enclosing_type_decl(context).type_names.get(type_name)

                if symbol is None:
                    raise SemanticError(f"Type name '{type_name}' could not be resolved.")
                return f"{symbol.name}[]"

        case "mult_expr":
            [left_type, right_type] = map(lambda c: resolve_expression(c, context), tree.children)
            if any(t not in NUMERIC_TYPES for t in [left_type, right_type]):
                raise SemanticError(f"Cannot use operands of type {left_type},{right_type} in mult expression")

            # Binary numeric promotion into int
            return "int"

        case "add_expr":
            [left_type, right_type] = map(lambda c: resolve_expression(c, context), tree.children)

            if "String" in [left_type, right_type]:
                return "String"
            elif any(t not in NUMERIC_TYPES for t in [left_type, right_type]):
                raise SemanticError(f"Cannot use operands of type {left_type},{right_type} in add expression")

            # Binary numeric promotion into int
            return "int"

        case "rel_expr":
            operands = list(map(lambda c: resolve_expression(c, context), tree.children))
            op = None

            if len(operands) == 3:
                [left_type, op, right_type] = operands
            else:
                [left_type, right_type] = operands

            if op == "instanceof":
                if not (left_type == "null" or isinstance(left_type, ClassDecl)):
                    raise SemanticError(f"Left side of instanceof must be a reference type or the null type")
            else:
                if any(t not in NUMERIC_TYPES for t in [left_type, right_type]):
                    raise SemanticError(f"Cannot use operands of type {left_type},{right_type} in relational expression")

            return "boolean"

        case "eq_expr":
            [left_type, right_type] = map(lambda c: resolve_expression(c, context), tree.children)

            if left_type != right_type and not all(t in NUMERIC_TYPES for t in [left_type, right_type]):
                raise SemanticError(f"Cannot use operands of type {left_type},{right_type} in equality expression")

            return "boolean"

        case "eager_and_expr" | "eager_or_expr" | "and_expr" | "or_expr":
            [left_type, right_type] = map(lambda c: resolve_expression(c, context), tree.children)

            if left_type != "boolean" or right_type != "boolean":
                raise SemanticError(f"Cannot use operands of type {left_type},{right_type} (must be boolean) in and/or expression")

            return "boolean"

        case "expression_name":
            name = extract_name(tree)
            symbol = context.resolve(f"{LocalVarDecl.node_type}^{name}") or \
                context.resolve(f"{FieldDecl.node_type}^{name}") or \
                get_enclosing_type_decl(context).type_names.get(name)

            if symbol is None:
                raise SemanticError(f"Name '{name}' could not be resolved in expression.")

            return symbol.sym_type or symbol

        case x:
            print("unknown tree data", x)
