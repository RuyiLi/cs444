from context import ClassInterfaceDecl, Context, SemanticError


def hierarchy_check(context: Context):
    for sym_id, symbol in context.symbol_map.items():
        # Check that every symbol meets its hierarchy criteria
        symbol.hierarchy_check()

    for subcontext in context.children:
        hierarchy_check(subcontext)
