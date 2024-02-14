from context import Context, SemanticError

def hierarchy_check(context: Context):
	for sym_id, symbol in context.symbol_map.items():
		# Check that the types of all symbols exist
		symbol.hierarchy_check()
		pass

	for subcontext in context.children:
		hierarchy_check(subcontext)
