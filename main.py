from typing import List
import logging
import glob
import os
import sys

from lark import Lark, logger

logger.setLevel(logging.DEBUG)

grammar = ""
files = glob.glob(r"./grammar/**/*.lark", recursive=True)
for file in files:
    print(f"Loaded grammar {file[2:]}")
    with open(file) as f:
        grammar += "\n" + f.read()

l = Lark(grammar, start="compilation_unit", parser="lalr", debug=True)


def should_error(file_name: str):
    return file_name[:2] == "Je"


def load_assignment_testcases(assignment: int):
    test_directory = os.path.join(os.getcwd(), f"assignment_testcases/a{assignment}")
    test_files = os.listdir(test_directory)
    passed = 0
    for test_file in test_files:
        print(f"Testing {test_file}")
        with open(os.path.join(test_directory, test_file), "r") as f:
            test_file_contents = f.read()
            try:
                print(l.parse(test_file_contents).pretty())
                if should_error(test_file):
                    print(f"Failed {test_file} (should have thrown an error):")
                else:
                    print(f"Passed {test_file} (correctly did not throw an error):")
                    passed += 1

            except Exception as e:
                if should_error(test_file):
                    print(f"Passed {test_file} (correctly threw an error):", e)
                    passed += 1
                else:
                    print(f"Failed {test_file} (should not have thrown an error):", e)
    print(f"Total passed: {passed}/{len(test_files)}")


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


def load_path_testcase(path: str):
    print(f"Testing {path}")
    try:
        f = open(f"./{path}", "r")
    except FileNotFoundError:
        print(f"Could not find test with name {path}, skipping...")
    else:
        with f:
            test_file_contents = f.read()
            try:
                print(l.parse(test_file_contents).pretty())
            except Exception as e:
                print(f"Failed {path}:", e)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Joos test suite utilities.")
    parser.add_argument("-a", type=int, help="Load assignment testcases")
    parser.add_argument("-t", type=str, nargs="+", help="Load custom testcases")
    parser.add_argument("-p", type=str, help="Load testcases from path")

    args = parser.parse_args()

    if args.a is not None:
        load_assignment_testcases(args.a)

    if args.t is not None:
        load_custom_testcases(args.t)

    if args.p is not None:
        load_path_testcase(args.p)
