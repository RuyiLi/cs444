import os
import glob
import logging
from typing import List
from copy import deepcopy

from lark import Lark, logger

from build_environment import build_environment
from context import Context, GlobalContext
from hierarchy_check import hierarchy_check
from type_check import type_check
from type_link import type_link
from name_disambiguation import disambiguate_names
from weeder import Weeder

grammar = ""
grammar_files = glob.glob(r"./grammar/**/*.lark", recursive=True)
for file in grammar_files:
    print(f"Loaded grammar {file[2:]}")
    with open(file) as f:
        grammar += "\n" + f.read()

lark = Lark(
    grammar,
    start="compilation_unit",
    parser="lalr",
    propagate_positions=True,
)

logging.basicConfig(
    format="\033[2m[%(levelname)s] %(filename)s:%(funcName)s:%(lineno)d\033[0m\n%(message)s\n",
    level=logging.ERROR,
)
# !!!!!! THIS NEEDS TO BE CHANGED EVERY ASSIGNMENT !!!!!!
STDLIB_VERSION = 3.0
stdlib_files = glob.glob(f"stdlib/{STDLIB_VERSION}/java/**/*.java")
global_context_with_stdlib = GlobalContext()
for file in stdlib_files:
    with open(file) as f:
        res = lark.parse(f.read())
        Weeder(f.name).visit(res)
        build_environment(res, global_context_with_stdlib)


def static_check(context: GlobalContext):
    try:
        type_link(context)
    except Exception as e:
        logging.error("Failed type_link")
        raise e

    try:
        hierarchy_check(context)
    except Exception as e:
        logging.error("Failed hierarchy_check")
        raise e

    try:
        disambiguate_names(context)
    except Exception as e:
        logging.error("Failed name disambiguation")
        raise e

    try:
        type_check(context)
    except Exception as e:
        logging.error("Failed type check")
        raise e


def should_error(path_name: str):
    return path_name[:2] == "Je"


def load_assignment_testcases(assignment: int, quiet: bool):
    test_directory = os.path.join(os.getcwd(), f"assignment_testcases/a{assignment}")
    test_files_lists = []

    for entry in sorted(os.listdir(test_directory)):
        entry_path = os.path.join(test_directory, entry)
        if os.path.isfile(entry_path):
            test_files_lists.append([entry])

    for entry in sorted(os.listdir(test_directory)):
        entry_path = os.path.join(test_directory, entry)
        if os.path.isdir(entry_path):
            test_files_list = []
            for root, _, files in os.walk(entry_path):
                for file in sorted(files):
                    test_file = os.path.relpath(os.path.join(root, file), test_directory)
                    test_files_list.append(test_file)
            if test_files_list:
                test_files_lists.append(test_files_list)

    passed = 0
    failed_tests = []
    for test_files_list in test_files_lists:
        try:
            global_context = deepcopy(global_context_with_stdlib)

            for test_file in test_files_list:
                if not quiet:
                    print(f"Testing {test_file}")
                with open(os.path.join(test_directory, test_file), "r") as f:
                    test_file_contents = f.read()
                    res = lark.parse(test_file_contents)
                    Weeder(f.name).visit(res)
                    build_environment(res, global_context)

                    if not quiet:
                        print(res.pretty())

            static_check(global_context)

            if should_error(test_files_list[0]):
                print(f"Failed {test_files_list} (should have thrown an error):")
                failed_tests.append(str(test_files_list))
            else:
                if not quiet:
                    print(f"Passed {test_files_list} (correctly did not throw an error):")
                passed += 1

        except Exception as e:
            if should_error(test_files_list[0]):
                if not quiet:
                    print(f"Passed {test_files_list} (correctly threw an error):")
                passed += 1
            else:
                print(f"Failed {test_files_list} (should not have thrown an error):", e)
                failed_tests.append(str(test_files_list))

    print()
    print("=" * 50)
    print(f"Total passed: {passed}/{len(test_files_lists)}")
    if len(failed_tests) > 0:
        print(f"Failed tests: {', '.join(failed_tests)}")


def load_custom_testcases(test_names: List[str]):
    global_context = deepcopy(global_context_with_stdlib)

    for test_name in test_names:
        logging.info(f"Testing {test_name}")
        try:
            f = open(f"./custom_testcases/{test_name}.java", "r")
        except FileNotFoundError:
            print(f"Could not find test with name {test_name}.java, skipping...")
        else:
            with f:
                test_file_contents = f.read()
                try:
                    res = lark.parse(test_file_contents)
                    logging.debug(res.pretty())
                    Weeder(f.name).visit(res)

                    build_environment(res, global_context)

                    print(f"Passed {test_name}")
                except Exception as e:
                    print(f"Failed {test_name}:", e)
                    raise e

    static_check(global_context)


def load_path_testcases(paths: List[str]):
    global_context = GlobalContext()

    for path in paths:
        try:
            f = open(path, "r")
        except FileNotFoundError:
            print(f"Could not find test with name {path}, skipping...")
        else:
            with f:
                test_file_contents = f.read()
                try:
                    res = lark.parse(test_file_contents)
                    logging.debug(res.pretty())
                    Weeder(f.name).visit(res)
                    build_environment(res, global_context)
                except Exception as e:
                    logging.exception(e)
                    exit(42)

    try:
        static_check(global_context)
    except Exception as e:
        logging.exception(e)
        exit(42)


def load_parse_trees(paths: List[str]):
    for path in paths:
        try:
            f = open(path, "r")
        except FileNotFoundError:
            logging.info(f"Could not find test with name {path}, skipping...")
        else:
            with f:
                test_file_contents = f.read()
                try:
                    logging.info(f"Parsing {f.name}")
                    res = lark.parse(test_file_contents)
                    Weeder(f.name).visit(res)
                    logging.info(res.pretty())
                except Exception as e:
                    logging.error(e)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Joos test suite utilities.")
    parser.add_argument("-a", type=int, help="Load assignment testcases")
    parser.add_argument("-t", type=str, nargs="+", help="Load custom testcases")
    parser.add_argument("-p", type=str, nargs="+", help="Load testcases from path")
    parser.add_argument("-q", action="store_true", default=False, help="Only log errors")
    parser.add_argument("-v", action="store_true", default=False, help="Log everything")
    parser.add_argument("-g", type=str, nargs="+", help="View parse tree of files")

    args = parser.parse_args()

    # default to INFO
    log_level = logging.INFO
    if args.q:
        log_level = logging.ERROR
    if args.v:
        log_level = logging.DEBUG

    logger.setLevel(log_level)
    logging.root.setLevel(log_level)

    if args.a is not None:
        load_assignment_testcases(args.a, quiet=args.q)

    if args.t is not None:
        load_custom_testcases(args.t)

    if args.p is not None:
        load_path_testcases(args.p)

    if args.g is not None:
        load_parse_trees(args.g)
