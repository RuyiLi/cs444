from lark import Visitor, Token, ParseTree

class WeedError(Exception):
    pass

class Weeder(Visitor):
    def class_declaration(self, tree: ParseTree):
        modifiers = list(filter(lambda c: isinstance(c, Token) and c.type == "MODIFIER", tree.children))

        if any(x not in ["public", "abstract", "final"] for x in modifiers):
            raise WeedError("Invalid modifier used in class declaration.")

        if len(set(modifiers)) < len(modifiers):
            raise WeedError("Class declaration cannot contain more than one of the same modifier.")

        if any(x == "abstract" for x in modifiers) and any(x == "final" for x in modifiers):
            raise WeedError("Class declaration cannot be both abstract and final.")

    def field_declaration(self, tree: ParseTree):
        modifiers = list(filter(lambda c: isinstance(c, Token) and c.type == "MODIFIER", tree.children))

        if any(x == "final" for x in modifiers):
            raise WeedError("No field can be final.")


    # def __default__(self, tree: ParseTree):
        # print(tree.data, tree.children)
