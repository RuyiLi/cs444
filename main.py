import glob
from lark import Lark

grammar = ""

files = glob.glob(r"./grammar/*.lark")
for file in files:
    with open(file) as f:
        grammar += "\n" + f.read()

lark = Lark(grammar, start="expr", parser="lalr")

print(lark.parse("import foo;").pretty())
