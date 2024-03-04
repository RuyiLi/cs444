from lark import ParseTree, Token, Tree
from context import ClassInterfaceDecl, Context, FieldDecl, LocalVarDecl, SemanticError

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
        case _:
            raise SemanticError("how did you get here?")

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
        case "mult_expr": # | "eq_expr" | "eager_and_expr" | "eager_or_expr" | "and_expr" | "or_expr":
            [left_type, right_type] = map(lambda c: resolve_expression(c, context), tree.children)
            # print('expr', tree)
            # print('ls', left_type)
            # print('rs', right_type)
            if any(t not in ["byte", "short", "int", "char"] for t in [left_type, right_type]):
                raise SemanticError(f"Cannot use operands of type {left_type},{right_type} in mult expression")

            # Binary numeric promotion into int
            return "int"
        case "add_expr":
            [left_type, right_type] = map(lambda c: resolve_expression(c, context), tree.children)

            if "String" in [left_type, right_type]:
                return "String"
            elif any(t not in ["byte", "short", "int", "char"] for t in [left_type, right_type]):
                raise SemanticError(f"Cannot use operands of type {left_type},{right_type} in add expression")

            # Binary numeric promotion into int
            return "int"
        case "rel_expr":
            [left_type, right_type] = map(lambda c: resolve_expression(c, context), tree.children)
            # print('expr', tree)
            # print('ls', left_type)
            # print('rs', right_type)
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
