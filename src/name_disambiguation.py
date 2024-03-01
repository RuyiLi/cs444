from lark import ParseTree, Tree
from context import ClassDecl, ClassInterfaceDecl, Context, InterfaceDecl, SemanticError

from build_environment import get_identifiers

def disambiguate_names(context: Context):
    for child_context in context.children:
        parse_node(child_context.tree, child_context)
        disambiguate_names(child_context)

def parse_node(tree: ParseTree, context: Context):
    # print(tree)
    match tree.data:
        case "constructor_declaration" | "method_declaration":
            # Nested, ignore
            pass

        case "package_name":
            print(tree)

        case "type_name":
            print(tree)

        case "expression_name":
            print(tree)

        case "method_name":
            print(tree)
            ids = list(get_identifiers(tree))
            method_id = ids[-1]

            if len(ids) == 1:
                symbol = context.parent_node

                if symbol is None:
                    raise SemanticError(f"Method with name '{method_id}' doesn't exist in scope.")
            else:
                enclosing_type_decl = context.parent.parent_node
                assert isinstance(enclosing_type_decl, ClassInterfaceDecl)

                type_name = ".".join(list(ids)[:-1])
                symbol = enclosing_type_decl.type_names[type_name]

                if symbol is None:
                    raise SemanticError(f"Can't resolve type name '{type_name}'.")

            if isinstance(symbol, InterfaceDecl):
                raise SemanticError(f"Can't call method {method_id} as static from interface {symbol.name}")

            assert isinstance(symbol, ClassDecl)

            if not any(method.name == method_id for method in symbol.methods):
                raise SemanticError(f"Method {method_id} doesn't exist in class {symbol.name}")

        case "statement":
            child = tree.children[0]
            scope_stmts = ["block", "if_st", "if_else_st", "for_st", "while_st"]

            if isinstance(child, Tree) and child.data not in scope_stmts:
                parse_node(child, context)

        case _:
            for child in tree.children:
                if isinstance(child, Tree):
                    parse_node(child, context)
