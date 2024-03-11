import os

from helper import get_formal_params, get_modifiers, get_return_type
from interpreter import JoosInterpreter
from lark import ParseTree, Token, Tree, Visitor


class WeedError(Exception):
    pass


def format_error(msg: str, line=None):
    raise WeedError(f"{msg} (line {line})" if line is not None else msg)


class Weeder(Visitor):
    def __init__(self, file_name: str):
        file_name = os.path.basename(file_name)
        self.file_name = os.path.splitext(file_name)[0]

    def visit(self, tree: ParseTree):
        JoosInterpreter().visit(tree)
        super().visit(tree)

    def interface_declaration(self, tree: ParseTree):
        modifiers = get_modifiers(tree.children)

        # shouldn't raise stopiteration, grammar should catch anonymous classes
        interface_name = next(c for c in tree.children if isinstance(c, Token) and c.type == "IDENTIFIER")
        if "public" in modifiers and interface_name != self.file_name:
            raise WeedError(
                f"interface {interface_name} is public, should be declared in a file named {interface_name}.java"
            )

    def class_declaration(self, tree: ParseTree):
        modifiers = get_modifiers(tree.children)

        # shouldn't raise stopiteration, grammar should catch anonymous classes
        class_name = next(c for c in tree.children if isinstance(c, Token) and c.type == "IDENTIFIER")
        if "public" in modifiers and class_name != self.file_name:
            raise WeedError(
                f"class {class_name} is public, should be declared in a file named {class_name}.java"
            )

        invalid_modifier = next(filter(lambda c: c not in ["public", "abstract", "final"], modifiers), None)
        if invalid_modifier is not None:
            format_error(
                f'Invalid modifier "{invalid_modifier}" used in class declaration.',
                invalid_modifier.line,
            )

        if len(set(modifiers)) < len(modifiers):
            format_error(
                "Class declaration cannot contain more than one of the same modifier.",
                tree.meta.line,
            )

        if "abstract" in modifiers and "final" in modifiers:
            format_error("Class declaration cannot be both abstract and final.", tree.meta.line)

        method_declarations = list(tree.find_pred(lambda c: c.data == "method_declaration"))
        abstract_method = next(
            filter(lambda md: "abstract" in get_modifiers(md.children), method_declarations), None
        )

        if "abstract" not in modifiers and abstract_method is not None:
            format_error(
                "Non-abstract class cannot contain an abstract method.",
                abstract_method.meta.line,
            )

    def method_declaration(self, tree: ParseTree):
        modifiers = get_modifiers(tree.children)
        return_type = get_return_type(tree)

        valid_modifiers = ["public", "protected", "abstract", "static", "final", "native"]

        if invalid_modifier := next((c for c in modifiers if c not in valid_modifiers), None):
            format_error(
                f'Invalid modifier "{invalid_modifier}" used in method declaration.',
                invalid_modifier.line,
            )

        if len(set(modifiers)) < len(modifiers):
            format_error(
                "Method declaration cannot contain more than one of the same modifier.",
                tree.meta.line,
            )

        if "public" in modifiers and "protected" in modifiers:
            format_error("Method cannot be both public and protected.", tree.meta.line)

        if "final" in modifiers and "static" in modifiers:
            format_error("A static method cannot be final.", tree.meta.line)

        if "native" in modifiers and "static" not in modifiers:
            format_error("A native method must be static.", tree.meta.line)

        if "abstract" in modifiers:
            if "static" in modifiers or "final" in modifiers:
                format_error(
                    "Illegal combination of modifiers: abstract and final/static.",
                    tree.meta.line,
                )

        block = next(tree.find_pred(lambda x: x.data == "block"), None)
        if "abstract" in modifiers or "native" in modifiers:
            if block is not None:
                format_error("An abstract/native method must not have a body.", block.meta.line)
        else:
            if block is None and not getattr(tree, "_joos__is_interface_method", False):
                format_error("A non-abstract/native method must have a body.", tree.meta.line)

        if "native" in modifiers:
            if return_type != "int":
                format_error(
                    f"Native methods are restricted to int return type, found '{return_type}'", tree.meta.line
                )

            formal_param_types, _ = get_formal_params(tree)

            if len(formal_param_types) == 0 or len(formal_param_types) > 1 or formal_param_types[0] != "int":
                format_error("Native methods must have exactly one int parameter.", tree.meta.line)

        if "public" not in modifiers and "protected" not in modifiers:
            format_error("Method must be declared public or protected.", tree.meta.line)

        child_fields = filter(lambda c: isinstance(c, Tree) and c.data == "field_declaration", tree.children)
        for field in child_fields:
            if "public" not in get_modifiers(field.children):
                format_error("Package field must be declared public.", field.meta.line)

        return_exprs = list(tree.find_pred(lambda c: c.data == "return_st"))
        if return_type == "void":
            expr_return = next(
                filter(
                    lambda r: next(r.find_pred(lambda d: d.data == "expr"), None) is not None, return_exprs
                ),
                None,
            )
            if expr_return is not None:
                format_error(
                    "Void function cannot contain an expression in a return statement.", expr_return.meta.line
                )
        else:
            noexpr_return = next(
                filter(lambda r: next(r.find_pred(lambda d: d.data == "expr"), None) is None, return_exprs),
                None,
            )
            if noexpr_return is not None:
                format_error(
                    "Non-void function must contain an expression in a return statement.",
                    noexpr_return.meta.line,
                )

        # Final parameters cannot be assigned to.

    def octal(self, tree: ParseTree):
        octal_seq = tree.children[0][1:]
        tree.children[0] = chr(int(octal_seq, 8))

    def formal_param_list(self, tree: ParseTree):
        identifiers = list(
            map(lambda v: v.children[0], tree.find_pred(lambda c: c.data == "var_declarator_id"))
        )

        if len(set(identifiers)) < len(identifiers):
            format_error("Formal parameters must have unique identifiers.", tree.meta.line)

    def interface_method_declaration(self, tree: ParseTree):
        method_decl = tree.children[0]
        assert isinstance(method_decl, Tree)
        modifiers = get_modifiers(method_decl.children)

        if "final" in modifiers or "static" in modifiers or "native" in modifiers:
            format_error("An interface method cannot be static/final/native.", method_decl.meta.line)

        block = next(tree.find_pred(lambda x: x.data == "block"), None)

        if block is not None:
            format_error("An interface method must not have a body.", block.meta.line)

        if "public" not in modifiers:
            format_error("Method must be declared public.", tree.meta.line)

    def constructor_declaration(self, tree: ParseTree):
        modifiers = get_modifiers(tree.children)

        if invalid_modifier := next((m for m in modifiers if m not in ["public", "protected"]), None):
            format_error(
                f'Invalid modifier "{invalid_modifier}" used in constructor declaration.',
                invalid_modifier.line,
            )

        if len(set(modifiers)) < len(modifiers):
            format_error(
                "Constructor declaration cannot contain more than one of the same modifier.",
                tree.meta.line,
            )

        if "public" in modifiers and "protected" in modifiers:
            format_error("Constructor cannot be both public and protected.", tree.meta.line)

        if "public" not in modifiers and "protected" not in modifiers:
            format_error("Package private constructors are not allowed.", tree.meta.line)

    def expr(self, tree: ParseTree):
        MAX_INT = 2**31 - 1

        child = tree.children[0]
        if isinstance(child, Token):
            if child.type == "INTEGER_L" and int(child.value) > MAX_INT:
                format_error("Integer number too large", child.line)
        else:
            # Error if a parent has a child with a numeric value that is too large (depends on whether parent is unary_neg)
            int_too_large = next(
                child.find_pred(
                    lambda p: any(
                        isinstance(c, Token)
                        and c.value.isnumeric()
                        and int(c.value) > (MAX_INT + (1 if p.data == "unary_negative_expr" else 0))
                        for c in p.children
                    )
                ),
                None,
            )

            if int_too_large is not None:
                format_error("Integer number too large.", int_too_large.meta.line)

    def pre_dec_expr(self, tree: ParseTree):
        format_error("Pre-decrement operator not allowed.", tree.meta.line)

    def field_declaration(self, tree: ParseTree):
        modifiers = get_modifiers(tree.children)

        if invalid_modifier := next(
            (m for m in modifiers if m not in ["public", "protected", "static"]), None
        ):
            format_error(
                f'Invalid modifier "{invalid_modifier}" used in field declaration.', invalid_modifier.line
            )

        if "public" in modifiers and "protected" in modifiers:
            format_error("Field cannot be both public and protected.", tree.meta.line)

        if len(set(modifiers)) < len(modifiers):
            format_error(
                "Field declaration cannot contain more than one of the same modifier.",
                tree.meta.line,
            )

    def class_body(self, tree: ParseTree):
        constructor = next(tree.find_pred(lambda x: x.data == "constructor_declaration"), None)
        if constructor is None:
            format_error("Class must contain an explicit constructor.", tree.meta.line)

        nested_class = next(tree.find_pred(lambda x: x.data == "class_declaration"), None)
        if nested_class is not None:
            format_error("Nested classes are not allowed.", nested_class.meta.line)

    def cast_expr(self, tree: ParseTree):
        cast = tree.children[0]
        # if it's not a primitive type (i.e. int or int[]), enforce that it is an object or object array cast
        if cast not in ["int", "char", "byte", "short", "boolean"]:
            expr = cast.children[0]

            # enforce that it is casting an object (if it is array_type, we skip since that is enforced in grammer)
            if expr.data != "expression_name" and cast.data == "expr":
                format_error("Expression casting invalid.", tree.meta.line)
            else:
                expr.data = "reference_type"
                pass
