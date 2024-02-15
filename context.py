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

            for method in extend.methods:
                # in Replace()?
                if (replacing := next(filter(lambda m: m.signature() == method.signature(), self.methods), None)) is not None:
                    if replacing.return_type != method.return_type:
                        raise SemanticError(f"Class {self.name} cannot replace method with signature {method.signature()} with differing return types.")
                else:
                    if "abstract" in method.modifiers and "abstract" not in self.modifiers:
                        raise SemanticError(f"Non-abstract class {self.name} cannot inherit abstract method with signature {method.signature} without implementing it.")

                    contained_methods.append(method)

        if len(set(self.extends)) < len(self.extends):
            raise SemanticError(f"Duplicate class/interface in extends for class {self.name}")

        for implement in self.implements:
            exist_sym = self.context.resolve(f"class_interface^{implement}")

            if exist_sym is None:
                raise SemanticError(f"Class {self.name} cannot extend class {implement} that does not exist.")

            if exist_sym.node_type == "class_decl":
                raise SemanticError(f"Class {self.name} cannot implement a class ({implement}).")

            for method in implement.methods:
                # in Replace()?
                if (replacing := next(filter(lambda m: m.signature() == method.signature(), self.methods), None)) is not None:
                    if replacing.return_type != method.return_type:
                        raise SemanticError(f"Class {self.name} cannot replace method with signature {replacing.signature()} with differing return types.")
                else:
                    if "abstract" in method.modifiers and "abstract" not in self.modifiers:
                        raise SemanticError(f"Non-abstract class {self.name} cannot inherit abstract method with signature {method.signature} without implementing it.")

                    contained_methods.append(method)

        if len(set(self.extends)) < len(self.extends):
            raise SemanticError(f"Duplicate class/interface in implements for class {self.name}")

        for i in range(len(contained_methods)):
            for j in range(i+1, len(contained_methods)):
                if (contained_methods[i].signature() == contained_methods[j].signature() and
                    contained_methods[i].return_type != contained_methods[j].return_type):
                    raise SemanticError(f"Class {self.name} cannot contain two methods with signature {contained_methods[i].signature} but different return types.")

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

        if len(set(self.extends)) < len(self.extends):
            raise SemanticError(f"Duplicate class/interface in extends for interface {self.name}")

        for method in extend.methods:
            # in Replace()?
            if (replacing := next(filter(lambda m: m.signature() == method.signature(), self.methods), None)) is not None:
                if replacing.return_type != method.return_type:
                    raise SemanticError(f"Interface {self.name} cannot replace method with signature {method.signature()} with differing return types.")
            else:
                if "abstract" in method.modifiers and "abstract" not in self.modifiers:
                    raise SemanticError(f"Non-abstract interface {self.name} cannot inherit abstract method with signature {method.signature} without implementing it.")

                contained_methods.append(method)

        for i in range(len(contained_methods)):
            for j in range(i+1, len(contained_methods)):
                if (contained_methods[i].signature() == contained_methods[j].signature() and
                    contained_methods[i].return_type != contained_methods[j].return_type):
                    raise SemanticError(f"Interface {self.name} cannot contain two methods with signature {contained_methods[i].signature} but different return types.")

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