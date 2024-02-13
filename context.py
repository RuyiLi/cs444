class SemanticError(Exception):
    pass

class Context:
	def __init__(self, parent = None):
		self.parent = parent
		self.symbol_map = {}

	def declare(self, symbol):
		if (existing_symbol := self.resolve(symbol.id())) is not None:
			symbol.check_clash(existing_symbol)
		else:
			self.symbol_map[symbol.id()] = symbol

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

	def id(self):
		return id_hash(self.name)

	def check_clash(self, existing_symbol):
		pass


class SymbolWithParams(Symbol):
	def __init__(self, context, name, params):
		super().__init__(context, name)
		self.params = params

	def id(self):
		return id_hash(self.name, self.params)


class ClassDecl(Symbol):
	def __init__(self, context, name, modifiers, extends, implements):
		super().__init__(context, name)
		self.modifiers = modifiers
		self.extends = extends;
		self.implements = implements;

	def check_clash(self, existing_symbol):
		if existing_symbol.name == self.name:
			raise SemanticError(f"Cannot redeclare class named {self.name} in scope.")


class InterfaceDecl(Symbol):
	def __init__(self, context, name, modifiers, extends, implements):
		super().__init__(context, name)
		self.modifiers = modifiers
		self.extends = extends;
		self.implements = implements;

	def check_clash(self, existing_symbol):
		if existing_symbol.name == self.name:
			raise SemanticError(f"Cannot redeclare interface named {self.name} in scope.")


class MethodDecl(SymbolWithParams):
	def __init__(self, context, name, params, modifiers):
		super().__init__(context, name, params)
		self.modifiers = modifiers

	def check_clash(self, existing_symbol):
		if existing_symbol.name == self.name:
			raise SemanticError(f"Cannot redeclare method named {self.name} in scope.")


class LocalVarDecl(Symbol):
	def __init__(self, context, name, var_type):
		super().__init__(context, name)
		self.type = var_type;

	def check_clash(self, existing_symbol):
		if existing_symbol.name == self.name:
			raise SemanticError(f"Cannot redeclare local variable named {self.name} in scope.")


class IfStmt(Symbol):
	def __init__(self, context, name):
		super().__init__(context, name)


class WhileStmt(Symbol):
	def __init__(self, context, name):
		super().__init__(context, name)


def id_hash(name, params = None):
	return name + "^" + ",".join(params) if params is not None else name


node_dict = {
	"class_decl": ClassDecl,
	"if_stmt": IfStmt,
	"while_stmt": WhileStmt
}