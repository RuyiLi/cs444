class SemanticError(Exception):
    pass

class Context:
    def __init__(self, parent, parent_node):
        self.parent = parent
        self.parent_node = parent_node
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

    def hierarchy_check(self):
        pass

def inherit_methods(symbol: Symbol, methods):
    inherited_methods = []
    for method in methods:
        # in Replace()?
        if (replacing := next(filter(lambda m: m.signature() == method.signature(), methods), None)) is not None:
            if replacing.return_type != method.return_type:
                raise SemanticError(f"Class/interface {symbol.name} cannot replace method with signature {method.signature()} with differing return types.")

            if "static" in replacing.modifiers != "static" in method.modifiers:
                raise SemanticError(f"Class/interface {symbol.name} cannot replace method with signature {method.signature()} with differing static-ness.")

            if "protected" in replacing.modifiers and "public" in method.modifiers:
                raise SemanticError(f"Class/interface {symbol.name} cannot replace public method with signature {method.signature()} with a protected method.")

            if "final" in method.modifiers:
                raise SemanticError(f"Class/interface {symbol.name} cannot replace final method with signature {method.signature()}.")
        else:
            if symbol.node_type == "class_decl" and "abstract" in method.modifiers and "abstract" not in symbol.modifiers:
                raise SemanticError(f"Non-abstract class {symbol.name} cannot inherit abstract method with signature {method.signature} without implementing it.")

            inherited_methods.append(method)

def check_overlapping_methods(symbol: Symbol, methods):
    for i in range(len(methods)):
        for j in range(i+1, len(methods)):
            if (methods[i].signature() == methods[j].signature() and
                methods[i].return_type != methods[j].return_type):
                raise SemanticError(f"Class/interface {symbol.name} cannot contain two methods with signature {methods[i].signature} but different return types.")

class ClassDecl(Symbol):
    def __init__(self, context, name, modifiers, extends, implements):
        super().__init__(context, name)
        self.node_type = "class_decl"
        self.modifiers = modifiers
        self.extends = extends
        self.implements = implements

        self.fields = []
        self.methods = []
        self.constructors = []

    def sym_id(self):
        return "class_interface^" + self.name

    def hierarchy_check(self):
        contained_methods = self.methods

        for extend in self.extends:
            exist_sym = self.context.resolve(f"class_interface^{extend}")

            if exist_sym is None:
                raise SemanticError(f"Class {self.name} cannot extend class {extend} that does not exist.")

            if exist_sym.node_type == "interface_decl":
                raise SemanticError(f"Class {self.name} cannot extend an interface ({extend}).")

            if "final" in exist_sym.modifiers:
                raise SemanticError(f"Class {self.name} cannot extend a final class ({extend}).")

            contained_methods = contained_methods + inherit_methods(self, extend.methods)

        if len(set(self.extends)) < len(self.extends):
            raise SemanticError(f"Duplicate class/interface in extends for class {self.name}")

        for implement in self.implements:
            exist_sym = self.context.resolve(f"class_interface^{implement}")

            if exist_sym is None:
                raise SemanticError(f"Class {self.name} cannot extend class {implement} that does not exist.")

            if exist_sym.node_type == "class_decl":
                raise SemanticError(f"Class {self.name} cannot implement a class ({implement}).")

            contained_methods = contained_methods + inherit_methods(self, implement.methods)

        if len(set(self.extends)) < len(self.extends):
            raise SemanticError(f"Duplicate class/interface in implements for class {self.name}")

        check_overlapping_methods(self, contained_methods)
        print(list(map(lambda m: m.name, self.methods)))

class InterfaceDecl(Symbol):
    def __init__(self, context, name, modifiers, extends):
        super().__init__(context, name)
        self.node_type = "interface_decl"
        self.modifiers = modifiers
        self.extends = extends

        self.fields = []
        self.methods = []

    def sym_id(self):
        return "class_interface^" + self.name

    def hierarchy_check(self):
        contained_methods = self.methods

        for extend in self.extends:
            exist_sym = self.context.resolve(f"class_interface^{extend}")

            if exist_sym is None:
                raise SemanticError(f"Interface {self.name} cannot extend interface {extend} that does not exist.")

            if exist_sym.node_type == "class_decl":
                raise SemanticError(f"Interface {self.name} cannot extend a class ({extend}).")

            contained_methods = contained_methods + inherit_methods(self, extend.methods)

        if len(set(self.extends)) < len(self.extends):
            raise SemanticError(f"Duplicate class/interface in extends for interface {self.name}")

        check_overlapping_methods(self, contained_methods)

class ConstructorDecl(Symbol):
    def __init__(self, context, param_types, modifiers):
        super().__init__(context, "constructor")
        self.node_type = "constructor"
        self.param_types = param_types
        self.modifiers = modifiers

        self.context.parent_node.constructors.append(self)

    def sym_id(self):
        return "constructor^" + ",".join(self.param_types) if self.param_types is not None else "constructor"

class FieldDecl(Symbol):
    def __init__(self, context, name, modifiers, field_type):
        super().__init__(context, name)
        self.node_type = "field_decl"
        self.modifiers = modifiers
        self.sym_type = field_type

        self.context.parent_node.fields.append(self)

class MethodDecl(Symbol):
    def __init__(self, context, name, param_types, modifiers, return_type):
        super().__init__(context, name)
        self.node_type = "method_decl"
        self.param_types = param_types
        self.modifiers = modifiers
        self.return_type = return_type

        self.context.parent_node.methods.append(self)

    def signature(self):
        return self.name + "^" + ",".join(self.param_types) if self.param_types is not None else self.name

    def sym_id(self):
        return self.signature()

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