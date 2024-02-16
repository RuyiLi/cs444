from typing import List
import logging

from context import ClassInterfaceDecl, ClassDecl, InterfaceDecl, Context, SemanticError


"""
Terminology:
- A "canonical name", "qualified name", or just "name" is the full type_name of the import (e.g. foo.bar.Baz)
- A "simple name" is just the single identifier being imported (e.g. Baz)
"""


def resolve_simple_name(qualified_name: str) -> str:
    return qualified_name.split(".")[-1]


def resolve_package_name(qualified_name: str) -> str:
    return ".".join(qualified_name.split(".")[:-1])


class ImportDeclaration:
    def link_type(self, context: Context, type_decl: ClassInterfaceDecl):
        raise NotImplementedError


class SingleTypeImport(ImportDeclaration):
    def __init__(self, name: str):
        self.name = name

    @property
    def simple_name(self):
        return resolve_simple_name(self.name)

    def __repr__(self):
        return f"SingleTypeImport({self.simple_name}, {self.name})"

    def link_type(self, context: Context, type_decl: ClassInterfaceDecl):
        logging.info(f"Single Type Link: {self.name}, {type_decl.name}")

        # No single-type-import declaration clashes with the class or interface declared in the same file.
        if self.simple_name == type_decl.name:
            raise SemanticError(f"Type {type_decl.name} clashes with import declaration {self.name}")

        # No two single-type-import declarations clash with each other.
        for import_decl in type_decl.imports:
            # But allow duplicates
            if (
                isinstance(import_decl, SingleTypeImport)
                and self.simple_name == import_decl.simple_name
                and self.name != import_decl.name
            ):
                raise SemanticError(f"Import {self.name} clashes with {import_decl.name}")

        # All type names must resolve to some class or interface declared in some file listed on the Joos command line.
        imported_type = context.resolve(f"{ClassInterfaceDecl.node_type}^{self.name}")
        if imported_type is None:
            raise SemanticError(f"Import {self.name} does not resolve to any provided type")

        type_decl.type_names[self.simple_name] = imported_type


class OnDemandImport(ImportDeclaration):
    def __init__(self, package: str):
        self.package = package

    def __repr__(self):
        return f"SingleTypeImport({self.package}.*)"

    def link_type(self, context: Context, type_decl: ClassInterfaceDecl):
        logging.info(f"On Demand Type Link: {self}, {type_decl.name}")

        # Every import-on-demand declaration must refer to a package declared in some file listed on the
        # Joos command line. That is, the import-on-demand declaration must refer to a package whose name
        # appears as the package declaration in some source file, or whose name is a prefix of the name
        # appearing in some package declaration.
        prefix = self.package + "."
        for package in context.packages.keys():
            if package == self.package or package.startswith(prefix):
                return

        raise SemanticError(
            f"Imported package {self.package} does not exist as either a package declaration or a prefix of a package declaration."
        )


def resolve_type(context: Context, type_name: str, type_decl: ClassInterfaceDecl):
    logging.debug(f"Resolving {type_name}")

    is_qualified = "." in type_name
    if is_qualified:
        # resolve fully qualified type name
        symbol = context.resolve(f"{ClassInterfaceDecl.node_type}^{type_name}")
        if symbol is None:
            raise SemanticError(f"Full qualified type {type_name} does not resolve to any provided type")
        else:
            type_decl.type_names[type_name] = symbol
    else:
        # resolve simple type name

        # all single imports are already resolved, so look at on demand imports
        for import_decl in type_decl.imports:
            if isinstance(import_decl, OnDemandImport):
                symbol = context.resolve(f"{ClassInterfaceDecl.node_type}^{import_decl.package}.{type_name}")
                if symbol is not None:
                    type_decl.type_names[type_name] = symbol
                    return

        raise SemanticError(f"Simple type {type_name} does not resolve to any provided type")


def type_link(context: Context):
    """
    Should only be run once on the global context.
    """

    type_decls: List[ClassInterfaceDecl] = list(
        filter(
            lambda symbol: symbol.node_type in [ClassDecl.node_type, InterfaceDecl.node_type],
            context.symbol_map.values(),
        )
    )

    for type_decl in type_decls:
        logging.debug(f"Linking type {type_decl.name}")

        # resolve class/interface name to itself
        type_name = resolve_simple_name(type_decl.name)
        type_decl.type_names[type_name] = type_decl

        # auto import types from the same package
        package_name = resolve_package_name(type_decl.name)
        for same_package_type_decl in context.packages[package_name]:
            same_package_type_name = resolve_simple_name(same_package_type_decl.name)
            type_decl.type_names[same_package_type_name] = same_package_type_decl

        # verify and resolve imports
        for import_decl in type_decl.imports:
            import_decl.link_type(context, type_decl)

        # resolve type names to symbols, skip if already resolved (SingleTypeImports)
        for type_name, symbol in type_decl.type_names.items():
            if symbol is None:
                resolve_type(context, type_name, type_decl)
