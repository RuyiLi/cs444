from lark.visitors import Interpreter


class JoosInterpreter(Interpreter):
    def interface_method_declaration(self, tree):
        method_decl = tree.children[0]
        setattr(method_decl, "_joos__is_interface_method", True)
