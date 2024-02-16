from typing import List, Type

"""
Terminology:
- A "canonical name" is the full type_name of the import (e.g. foo.bar.Baz)
- A "simple name" is just the name of the object being imported (e.g. Baz)
"""


class SingleTypeImport:
    def __init__(self, canonical: str):
        self.canonical = canonical

    @property
    def simple(self):
        return self.canonical.split(".")[-1]

    def __repr__(self):
        return f"SingleTypeImport({self.simple}, {self.canonical})"


class OnDemandImport:
    def __init__(self, package: str):
        self.package = package

    def __repr__(self):
        return f"SingleTypeImport({self.package})"


ImportDeclaration = SingleTypeImport | OnDemandImport
