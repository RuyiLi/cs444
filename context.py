class SemanticError(Exception):
    pass

class Context:
	def __init__(self, parent = None):
		self.parent = parent
		self.children = []
		self.symbol_map = {}

	def declare(self, symbol):
		if self.resolve(symbol.sym_id()) is not None:
			raise SemanticError(f"Overlapping {symbol.node_type} in scope.")

		self.symbol_map[symbol.sym_id()] = symbol

	def resolve(self, id_hash):
		if id_hash in self.symbol_map:
			return self.symbol_map.get(id_hash)

		# Try looking in parent scope
		if self.parent is not None:
			return self.parent.resolve(id_hash)

		return None

class Symbol:
	def __init__(self, context, name):
		self.context = context
		self.name = name
		self.node_type = ""

	def sym_id(self):
		return self.node_type + "^" + self.name

class ClassDecl(Symbol):
	def __init__(self, context, name, modifiers, extends, implements):
		super().__init__(context, name)
		self.node_type = "class_decl"
		self.modifiers = modifiers
		self.extends = extends
		self.implements = implements

	def sym_id(self):
		return "class_interface^" + self.name

class InterfaceDecl(Symbol):
	def __init__(self, context, name, modifiers, extends):
		super().__init__(context, name)
		self.node_type = "interface_decl"
		self.modifiers = modifiers
		self.extends = extends

	def sym_id(self):
		return "class_interface^" + self.name

class FieldDecl(Symbol):
	def __init__(self, context, name, modifiers, field_type):
		super().__init__(context, name)
		self.node_type = "field_decl"
		self.modifiers = modifiers
		self.sym_type = field_type

class MethodDecl(Symbol):
	def __init__(self, context, name, params, modifiers):
		super().__init__(context, name)
		self.node_type = "method_decl"
		self.params = params
		self.modifiers = modifiers

	def sym_id(self):
		return self.name + "^" + ",".join(self.params) if self.params is not None else self.name

class LocalVarDecl(Symbol):
	def __init__(self, context, name, var_type):
		super().__init__(context, name)
		self.node_type = "local_var_decl"
		self.sym_type = var_type

class IfStmt(Symbol):
	def __init__(self, context, name):
		super().__init__(context, name)


class WhileStmt(Symbol):
	def __init__(self, context, name):
		super().__init__(context, name)

node_dict = {
	"class_decl": ClassDecl,
	"if_stmt": IfStmt,
	"while_stmt": WhileStmt
}