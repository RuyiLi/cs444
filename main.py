import glob
import os

from lark import Lark

grammar = ""

files = glob.glob(r"./grammar/*.lark")
for file in files:
    with open(file) as f:
        grammar += "\n" + f.read()

l = Lark(grammar, start="expr", parser="lalr")

print(l.parse("'f' + 3 - '\\b' / '\\0177' + \"foo\\b\" + null").pretty())

test_directory = os.path.join(os.getcwd(), "assignment_testcases/a1")
test_files = os.listdir(test_directory)
for test_file in test_files:
    with open(os.path.join(test_directory, test_file), "r") as f:
        test_file_contents = f.read()
        try:
            # print(l.parse(test_file_contents).pretty())
            pass
        except:
            # print(f"Failed {test_file}")
            pass
