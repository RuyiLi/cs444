from lark import Visitor, Token, ParseTree, Tree
from typing import List, Union
import os


class WeedError(Exception):
    pass


def get_modifiers(trees_or_tokens: List[Union[Token, Tree[Token]]]):
    return [c for c in trees_or_tokens if isinstance(c, Token) and c.type == "MODIFIER"]


def format_error(msg: str, line=None):
    raise WeedError(f"{msg} (line {line})" if line is not None else msg)


class Weeder(Visitor):
    def __init__(self, file_name: str):
        file_name = os.path.basename(file_name)
        self.file_name = os.path.splitext(file_name)[0]

    def interface_declaration(self, tree: ParseTree):
        modifiers = get_modifiers(tree.children)

        # shouldn't raise stopiteration, grammar should catch anonymous classes
        interface_name = next(filter(lambda c: isinstance(c, Token) and c.type == "IDENTIFIER", tree.children))
        if "public" in modifiers and interface_name != self.file_name:
            raise WeedError(
                f"interface {interface_name} is public, should be declared in a file named {interface_name}.java"
            )

    def class_declaration(self, tree: ParseTree):
        modifiers = get_modifiers(tree.children)

        # shouldn't raise stopiteration, grammar should catch anonymous classes
        class_name = next(
            filter(
                lambda c: isinstance(c, Token) and c.type == "IDENTIFIER", tree.children
            )
        )
        if "public" in modifiers and class_name != self.file_name:
            raise WeedError(
                f"class {class_name} is public, should be declared in a file named {class_name}.java"
            )

        invalid_modifier = next(
            filter(lambda c: c not in ["public", "abstract", "final"], modifiers), None
        )
        if invalid_modifier is not None:
            format_error(
                'Invalid modifier "{invalid_modifier}" used in class declaration.',
                invalid_modifier.line,
            )

        if len(set(modifiers)) < len(modifiers):
            format_error(
                "Class declaration cannot contain more than one of the same modifier.",
                tree.meta.line,
            )

        if "abstract" in modifiers and "final" in modifiers:
            format_error(
                "Class declaration cannot be both abstract and final.", tree.meta.line
            )

        # Non-abstract class
        if "abstract" not in modifiers:
            method_declarations = list(
                tree.find_pred(lambda c: c.data == "method_declaration")
            )

            for md in method_declarations:
                abstract_method = "abstract" in get_modifiers(md.children)

                if abstract_method:
                    format_error(
                        "Non-abstract class cannot contain an abstract method.",
                        md.meta.line,
                    )

    def method_declaration(self, tree: ParseTree):
        modifiers = get_modifiers(tree.children)

        invalid_modifier = next(
            filter(
                lambda c: c
                not in ["public", "protected", "abstract", "static", "final", "native"],
                modifiers,
            ),
            None,
        )
        if invalid_modifier is not None:
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
                    "Illegal combination of modifiers: abstract and final/static",
                    tree.meta.line,
                )

        if "abstract" in modifiers or "native" in modifiers:
            block = next(tree.find_pred(lambda x: x.data == "block"), None)

            if block is not None:
                format_error("An abstract/native method must not have a body.", block.meta.line)

        # Two methods cannot have the same signature (name + param types).
        # Two methods cannot have the same identifier.
        # Final parameters cannot be assigned to.

    def interface_method_declaration(self, tree: ParseTree):
        method_decl = tree.children[0]
        assert isinstance(method_decl, Tree)
        modifiers = get_modifiers(method_decl.children)

        if "final" in modifiers or "static" in modifiers or "native" in modifiers:
            format_error("An interface method cannot be static/final/native.", method_decl.meta.line)

        block = next(tree.find_pred(lambda x: x.data == "block"), None)

        if block is not None:
            format_error("An interface method must not have a body.", block.meta.line)

    def expr(self, tree: ParseTree):
        MAX_INT = 2**31 - 1

        child = tree.children[0]
        if isinstance(child, Token):
            if child.type == "INTEGER_L" and int(child.value) > MAX_INT:
                format_error("Integer number too large", child.line)
        else:
            # Error if a parent has a child with a numeric value that is too large (depends on whether parent is unary_neg)
            int_too_large = next(child.find_pred(lambda p:
                any(isinstance(c, Token) and c.value.isnumeric() and
                     int(c.value) > (MAX_INT + (1 if p.data == "unary_negative_expr" else 0))
                for c in p.children)
            ), None)

            if int_too_large is not None:
                format_error("Integer number too large", int_too_large.meta.line)
    
    def pre_dec_expr(self, tree: ParseTree):
        format_error("Pre-decrement operator not allowed", tree.meta.line)

    def field_declaration(self, tree: ParseTree):
        modifiers = get_modifiers(tree.children)

        if "final" in modifiers:
            format_error("No field can be final.", tree.meta.line)

    # def __default__(self, tree: ParseTree):
    # print(tree.data, tree.children)
