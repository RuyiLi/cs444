from context import ClassInterfaceDecl, Context, SemanticError

"""
Terminology:
- A "canonical name", "qualified name", or just "name" is the full type_name of the import (e.g. foo.bar.Baz)
- A "simple name" is just the single identifier being imported (e.g. Baz)
"""


class ImportDeclaration:
    def type_link(self, context: Context, type_decl: ClassInterfaceDecl):
        raise NotImplementedError


class SingleTypeImport(ImportDeclaration):
    def __init__(self, name: str):
        self.name = name
        self.simple_name = name.split(".")[-1]

    def __repr__(self):
        return f"SingleTypeImport({self.simple_name}, {self.name})"

    def type_link(self, context: Context, type_decl: ClassInterfaceDecl):
        # No single-type-import declaration clashes with the class or interface declared in the same file.
        if self.simple_name == type_decl.name:
            raise SemanticError(f"Type {type_decl.name} clashes with import declaration {self.name}")

        # No two single-type-import declarations clash with each other.
        for import_decl in type_decl.imports:
            if (
                isinstance(import_decl, SingleTypeImport)
                and self.simple_name == import_decl.simple_name
                and self.name != import_decl.name
            ):
                raise SemanticError(f"Import {self.name} clashes with {import_decl.name}")

        # All type names must resolve to some class or interface declared in some file listed on the Joos command line.
        linked_type = context.resolve(f"class_interface^{self.name}")
        if linked_type is None:
            raise SemanticError(f"Imported type {self.name} does not resolve to any specified type")


class OnDemandImport(ImportDeclaration):
    def __init__(self, package: str):
        self.package = package

    def __repr__(self):
        return f"SingleTypeImport({self.package}.*)"

    def type_link(self, context: Context, type_decl: ClassInterfaceDecl):
        pass


def check_type_decl(context: Context, type_decl: ClassInterfaceDecl):
    for import_decl in type_decl.imports:
        import_decl.type_link(context, type_decl)
