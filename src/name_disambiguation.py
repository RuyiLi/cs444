from lark import ParseTree, Tree
from context import ClassDecl, ClassInterfaceDecl, Context, FieldDecl, InterfaceDecl, LocalVarDecl, SemanticError

from build_environment import get_identifiers

def disambiguate_names(context: Context):
    for child_context in context.children:
        parse_node(child_context.tree, child_context)
        disambiguate_names(child_context)

def get_enclosing_type_decl(context):
     # Go up contexts until we reach a class/interface (do we need this? can we just use parent_node?)
    new_context = context
    while not isinstance(new_context.parent_node, ClassInterfaceDecl):
        new_context = new_context.parent

    enclosing_type_decl = new_context.parent_node
    assert isinstance(enclosing_type_decl, ClassInterfaceDecl)

    return enclosing_type_decl

def parse_node(tree: ParseTree, context: Context):
    match tree.data:
        case "constructor_declaration" | "method_declaration":
            # Nested, ignore
            pass

        case "package_name":
            # I suspect all package names are just valid? 
            pass

        case "type_name":
            print(tree)
            ids = list(get_identifiers(tree))
            type_id = ids[-1]

            enclosing_type_decl = get_enclosing_type_decl(context)

            # Not sure if we need some kind of priority system. Can types clash?
            if len(ids) == 1:
                symbol = enclosing_type_decl.type_names[type_id]

                if symbol is None:
                    raise SemanticError(f"Type name '{type_id}' doesn't exist in scope.")
            else:
                type_name = ".".join(list(ids)[:-1])
                symbol = enclosing_type_decl.type_names[type_name]

                if symbol is None or type_id not in symbol.type_names:
                    raise SemanticError(f"Can't resolve type name '{'.'.join(ids)}'")

        case "expression_name":
            print(tree)
            ids = list(get_identifiers(tree))
            expr_id = ids[-1]

            if len(ids) == 1:
                symbol = context.resolve(f"{LocalVarDecl.node_type}^{expr_id}") or context.resolve(f"{FieldDecl.node_type}^{expr_id}")
                
                if symbol is None:
                    raise SemanticError(f"Can't resolve expression name '{expr_id}'.")
            else:
                name_type = parse_ambiguous_name(context, ids[:-1])

                if name_type == "type_name":
                    type_decl = get_enclosing_type_decl(context).type_names[".".join(ids[:-1])]

                    assert isinstance(type_decl, ClassInterfaceDecl)

                    field_symbol = next(filter(lambda f: f.name == expr_id, type_decl.fields), None)

                    if field_symbol is not None and "static" not in field_symbol.modifiers:
                        raise SemanticError(f"Can't access non-static field {expr_id} from {'.'.join(ids[:-1])}.")
                else:
                    # TODO: Get type of expression. If type isn't a reference type, error
                    symbol = None

        case "method_name":
            print(tree)
            ids = list(get_identifiers(tree))
            method_id = ids[-1]

            if len(ids) == 1:
                symbol = context.parent_node

                if symbol is None:
                    raise SemanticError(f"Method with name '{method_id}' doesn't exist in scope.")
            else:
                name_type = parse_ambiguous_name(context, ids[:-1])

                if name_type == "type_name":
                    enclosing_type_decl = get_enclosing_type_decl(context)

                    type_name = ".".join(list(ids)[:-1])
                    symbol = enclosing_type_decl.type_names[type_name]

                    if symbol is None:
                        raise SemanticError(f"Can't resolve type name '{type_name}'.")
                else:
                    # TODO: Get type of expression
                    symbol = None

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

def parse_ambiguous_name(context, ids):
    last_id = ids[-1]

    if len(ids) == 1:
        if context.resolve(f"{LocalVarDecl.node_type}^{last_id}") or context.resolve(f"{FieldDecl.node_type}^{last_id}"):
            return "expression_name"
        else:
            return "type_name"
    else:
        result = parse_ambiguous_name(context, ids[:-1])

        if result == "type_name":
            enclosing_type_decl = get_enclosing_type_decl(context)
            symbol = enclosing_type_decl.type_names.get(".".join(ids[:-1]))

            # Just try type name?
            if symbol is None:
                return "type_name"

            if any(last_id == method.name for method in symbol.methods) or any(last_id == field.name for field in symbol.fields):
                return "expression_name"
        elif result == "expression_name":
            # Need to somehow resolve type of expression??
            return "expression_name"
