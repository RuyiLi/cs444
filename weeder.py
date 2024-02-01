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

        if "abstract" in modifiers and ("static" in modifiers or "final" in modifiers):
            raise WeedError(
                "Illegal combination of modifiers: abstract and final/static"
            )

    def field_declaration(self, tree: ParseTree):
        modifiers = get_modifiers(tree.children)

        if "final" in modifiers:
            raise WeedError("No field can be final.")

    # def __default__(self, tree: ParseTree):
    # print(tree.data, tree.children)
