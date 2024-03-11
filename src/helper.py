from typing import List, Type, TypeVar, Union
from lark import ParseTree, Token, Tree
from context import Context, Symbol, ClassInterfaceDecl, MethodDecl, FieldDecl, PrimitiveType

def get_child_tree(tree: ParseTree, name: str) -> Tree:
    return next(filter(lambda c: isinstance(c, Tree) and c.data == name, tree.children), None)


def get_nested_token(tree: ParseTree, name: str) -> str:
    return next(tree.scan_values(lambda v: isinstance(v, Token) and v.type == name)).value


def get_tree_token(tree: ParseTree, tree_name: str, token_name: str):
    return get_nested_token(next(tree.find_data(tree_name)), token_name)


def get_identifiers(tree: ParseTree):
    tokens = tree.scan_values(lambda v: isinstance(v, Token) and v.type == "IDENTIFIER")
    return (token.value for token in tokens)


def get_modifiers(trees_or_tokens: List[Union[Token, Tree[Token]]]):
    return [c for c in trees_or_tokens if isinstance(c, Token) and c.type == "MODIFIER"]


def get_return_type(tree: ParseTree):
    if any(isinstance(x, Token) and x.type == "VOID_KW" for x in tree.children):
        return "void"

    return extract_type(get_child_tree(tree, "type"))


def extract_name(tree: ParseTree):
    return ".".join(get_identifiers(tree))


def extract_type(tree: ParseTree | Token):
    if isinstance(tree, Token):
        # primitive
        return tree.value
    elif tree.data == "array_type":
        return extract_type(tree.children[0]) + "[]"
    elif tree.data == "type_name" or tree.data == "reference_type":
        return extract_name(tree)
    return extract_type(tree.children[0])


def get_formal_params(tree: ParseTree):
    formal_params = next(tree.find_data("formal_param_list"), None)

    formal_param_types = []
    formal_param_names = []

    if formal_params is not None:
        for child in formal_params.children:
            if isinstance(child, Token):
                continue

            formal_param_types.append(extract_type(next(child.find_data("type"))))
            formal_param_names.append(get_tree_token(child, "var_declarator_id", "IDENTIFIER"))

    return (formal_param_types, formal_param_names)


T = TypeVar("T", bound=Symbol)

def get_enclosing_decl(context: Context, decl_type: Type[T]) -> T:
    # Go up contexts until we reach the desired type
    while context and not isinstance(context.parent_node, decl_type):
        context = context.parent
    if context is None:
        return None
    return context.parent_node


def get_enclosing_type_decl(context: Context):
    return get_enclosing_decl(context, ClassInterfaceDecl)


def is_static_context(context: Context):
    if context.is_static:
        return True
    function_decl = get_enclosing_decl(context, MethodDecl)
    if function_decl is not None:
        return "static" in function_decl.modifiers
    field_decl = get_enclosing_decl(context, FieldDecl)
    return field_decl is not None and "static" in field_decl.modifiers
