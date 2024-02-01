from lark import Visitor, Token, ParseTree
import os


class WeedError(Exception):
    pass


class Weeder(Visitor):
    def __init__(self, file_name: str):
        file_name = os.path.basename(file_name)
        self.file_name = os.path.splitext(file_name)[0]

    def class_declaration(self, tree: ParseTree):
        modifiers = [
            c for c in tree.children if isinstance(c, Token) and c.type == "MODIFIER"
        ]

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

        if any(x == "abstract" for x in modifiers) and any(
            x == "final" for x in modifiers
        ):
            raise WeedError("Class declaration cannot be both abstract and final.")

    # def __default__(self, tree: ParseTree):
    # print(tree.data, tree.children)
