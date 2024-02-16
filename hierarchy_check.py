from typing import List
from type_link import check_type_decl

from context import ClassInterfaceDecl, Context, SemanticError


def type_link(context: Context):
    # should only be run once on the global context
    type_decls: List[ClassInterfaceDecl] = list(
        filter(
            lambda symbol: symbol.node_type == ClassInterfaceDecl.node_type,
            context.symbol_map.items(),
        )
    )

    for type_decl in type_decls:
        check_type_decl(type_decl)


def hierarchy_check(context: Context):
    for sym_id, symbol in context.symbol_map.items():
        # Check that the types of all symbols exist

        # Check that every symbol meets its hierarchy criteria
        symbol.hierarchy_check()

    for subcontext in context.children:
        hierarchy_check(subcontext)


# BFS upwards through all superclasses/superinterfaces, maintaining path traveled so far for every possible path.
# If a superclass/superinterface is already on the path, there is a cyclic dependency.
def check_cyclic(symbol: ClassInterfaceDecl):
    to_visit = list(map(lambda x: list(x), symbol.extends + (symbol.implements or [])))
    next_visit = []
    global_context = symbol.context

    while len(to_visit) != 0:
        for path in to_visit:
            curr_sym = global_context.resolve(path[-1])

            for next_sym_name in curr_sym.extends + (curr_sym.implements or []):
                if next_sym_name in path:
                    raise SemanticError(f"Cyclic dependency found, path {'->'.join(path + [next_sym_name])}")
                next_visit.append(path.copy().append(next_sym_name))

        to_visit = next_visit
        next_visit = []
