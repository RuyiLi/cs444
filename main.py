from typing import List
import glob
import os

from lark import Lark

grammar = ""
files = glob.glob(r"./grammar/**/*.lark", recursive=True)
for file in files:
    print(f"Loaded grammar {file[2:]}")
    with open(file) as f:
        grammar += "\n" + f.read()

l = Lark(grammar, start="expr", parser="lalr")


def load_assignment_testcases(assignment: int):
    test_directory = os.path.join(os.getcwd(), f"assignment_testcases/a{assignment}")
    test_files = os.listdir(test_directory)
    for test_file in test_files:
        print(f"Testing {test_file}")
        with open(os.path.join(test_directory, test_file), "r") as f:
            test_file_contents = f.read()
            try:
                print(l.parse(test_file_contents).pretty())
            except Exception as e:
                print(f"Failed {test_file}:", e)


def load_custom_testcases(test_names: List[str]):
    for test_name in test_names:
        print(f"Testing {test_name}")
        try:
            f = open(f"./custom_testcases/{test_name}.java", "r")
        except FileNotFoundError:
            print(f"Could not find test with name {test_name}, skipping...")
        else:
            with f:
                test_file_contents = f.read()
                try:
                    print(l.parse(test_file_contents).pretty())
                except Exception as e:
                    print(f"Failed {test_name}:", e)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Joos test suite utilities.")
    parser.add_argument("-a", type=int, help="Load assignment testcases")
    parser.add_argument("-t", type=str, nargs="+", help="Load custom testcases")

    args = parser.parse_args()

    if args.a is not None:
        load_assignment_testcases(args.a)

    if args.t is not None:
        load_custom_testcases(args.t)
