import glob
from lark import Lark

grammar = ""

files = glob.glob(r"./grammar/*.lark")
for file in files:
    with open(file) as f:
        grammar += "\n" + f.read()

l = Lark(grammar, start="expr", parser="lalr")

print(l.parse("'f' + 3 - '\\b' / '\\0177' + \"foo\\b\" + null").pretty())
