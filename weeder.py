from lark import Visitor, Token, ParseTree, Tree
from typing import List, Union
import os


class WeedError(Exception):
    pass


def get_modifiers(trees_or_tokens: List[Union[Token, Tree[Token]]]):
    return [c for c in trees_or_tokens if isinstance(c, Token) and c.type == "MODIFIER"]


class Weeder(Visitor):
    def __init__(self, file_name: str):
        file_name = os.path.basename(file_name)
        self.file_name = os.path.splitext(file_name)[0]

    def interface_declaration(self, tree: ParseTree):
        modifiers = get_modifiers(tree.children)

        # shouldn't raise stopiteration, grammar should catch anonymous classes
        interface_name = next(filter(lambda c: c.type == "IDENTIFIER", tree.children))
        if "public" in modifiers and interface_name != self.file_name:
            raise WeedError(
                f"interface {interface_name} is public, should be declared in a file named {interface_name}.java"
            )

    def class_declaration(self, tree: ParseTree):
        modifiers = get_modifiers(tree.children)

        # shouldn't raise stopiteration, grammar should catch anonymous classes
        class_name = next(filter(lambda c: c.type == "IDENTIFIER", tree.children))
        if "public" in modifiers and class_name != self.file_name:
            raise WeedError(
                f"class {class_name} is public, should be declared in a file named {class_name}.java"
            )

        if any(x not in ["public", "abstract", "final"] for x in modifiers):
            raise WeedError("Invalid modifier used in class declaration.")

        if len(set(modifiers)) < len(modifiers):
            raise WeedError(
                "Class declaration cannot contain more than one of the same modifier."
            )

        if "abstract" in modifiers and "final" in modifiers:
            raise WeedError("Class declaration cannot be both abstract and final.")

    def method_declaration(self, tree: ParseTree):
        modifiers = get_modifiers(tree.children)

        if "final" in modifiers and "static" in modifiers:
            raise WeedError("A static method cannot be final.")

        if "native" in modifiers and "static" not in modifiers:
            raise WeedError("A native method must be static.")

        if "abstract" in modifiers:
            if "static" in modifiers or "final" in modifiers:
                raise WeedError(
                    "Illegal combination of modifiers: abstract and final/static."
                )
            if tree.scan_values(lambda x: x.value == "method_body"):
                raise WeedError("An abstract method must not have a body.")

    def interface_method_declaration(self, tree: ParseTree):
        method_decl = tree.children[0]
        modifers = get_modifiers(method_decl.children)

        if "final" in modifers or "static" in modifers:
            raise WeedError("An interface method cannot be static or final.")

    def integer_l(self, tree: ParseTree):
        MAX_INT = 2**31 - 1
        MIN_INT = -(2**31)

        # doesnt work for -/*comment*/MAX_INT
        val = int(tree.children[0].value)
        if val > MAX_INT:
            raise WeedError("Integer number too large")
        if val < MIN_INT:
            raise WeedError("Integer number too large")

    def field_declaration(self, tree: ParseTree):
        modifiers = get_modifiers(tree.children)

        if "final" in modifiers:
            raise WeedError("No field can be final.")

    # def __default__(self, tree: ParseTree):
    # print(tree.data, tree.children)
