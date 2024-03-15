import glob
import logging
import os
import warnings
from copy import deepcopy
from typing import List

from build_environment import build_environment
from context import GlobalContext
from hierarchy_check import hierarchy_check
from lark import Lark, Tree, logger
from name_disambiguation import disambiguate_names
from type_check import type_check
from type_link import type_link
from reachability import analyze_reachability
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


# monkey patch lark.Tree to add context field
def __deepcopy__(self, memo):
    cls = self.__class__
    result = cls.__new__(cls)
    memo[id(self)] = result
    for k, v in self.__dict__.items():
        setattr(result, k, deepcopy(v, memo))
    return result


Tree.__deepcopy__ = __deepcopy__


logging.basicConfig(
    format="\033[2m[%(levelname)s] %(filename)s:%(funcName)s:%(lineno)d\033[0m\n%(message)s\n",
    level=logging.ERROR,
)
# !!!!!! THIS NEEDS TO BE CHANGED EVERY ASSIGNMENT !!!!!!
STDLIB_VERSION = 4.0
stdlib_files = glob.glob(f"stdlib/{STDLIB_VERSION}/java/**/*.java")
global_context_with_stdlib = GlobalContext()
for file in stdlib_files:
    with open(file) as f:
        res = lark.parse(f.read())
        Weeder(f.name).visit(res)
        build_environment(res, global_context_with_stdlib)


def static_check(context: GlobalContext, quiet=False):
    try:
        type_link(context)
    except Exception as e:
        if not quiet:
            logging.error("Failed type_link")
        raise e

    try:
        hierarchy_check(context)
    except Exception as e:
        if not quiet:
            logging.error("Failed hierarchy_check")
        raise e

    try:
        disambiguate_names(context)
    except Exception as e:
        if not quiet:
            logging.error("Failed name disambiguation")
        raise e

    try:
        type_check(context)
    except Exception as e:
        if not quiet:
            logging.error("Failed type check")
        raise e

    try:
        analyze_reachability(context)
    except Exception as e:
        if not quiet:
            logging.error("Failed reachability analysis")
        raise e


ERROR = 42
WARNING = 43
SUCCESS = 0


def get_result_string(result: int):
    if result == ERROR:
        return "error"
    elif result == WARNING:
        return "warning"
    elif result == SUCCESS:
        return "success"
    else:
        return "unrecognized result"


def get_expected_result(path_name: str):
    match path_name[:2]:
        case "Je":
            return ERROR
        case "Jw":
            return WARNING
        case _:
            return SUCCESS


def load_assignment_testcases(assignment: int, quiet: bool, custom_test_names: List[str]):
    test_directory = os.path.join(os.getcwd(), f"assignment_testcases/a{assignment}")
    test_files_lists = []
    custom_test_names_set = set(custom_test_names) if custom_test_names else None
    seen_custom_test_names_set = set()

    for entry in sorted(os.listdir(test_directory)):
        entry_path = os.path.join(test_directory, entry)
        if os.path.isfile(entry_path):
            if custom_test_names_set:
                if entry in custom_test_names_set:
                    test_files_lists.append([entry])
                    seen_custom_test_names_set.add(entry)
            else:
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
                if custom_test_names_set:
                    if entry in custom_test_names_set:
                        test_files_lists.append(test_files_list)
                        seen_custom_test_names_set.add(entry)
                else:
                    test_files_lists.append(test_files_list)

    if custom_test_names_set:
        missed_tests = custom_test_names_set.difference(seen_custom_test_names_set)
        for test_name in missed_tests:
            print(
                f"Could not find test file or folder in assignment {assignment} with name {test_name}, skipping..."
            )

    passed = 0
    failed_tests = []
    actual_result = SUCCESS
    for test_files_list in test_files_lists:
        error = None
        expected_result = get_expected_result(test_files_list[0])
        try:
            with warnings.catch_warnings(record=True) as warning_list:
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
                static_check(global_context, quiet)
            if warning_list:
                actual_result = WARNING
            else:
                actual_result = SUCCESS
        except Exception as e:
            actual_result = ERROR
            error = e

        if actual_result == expected_result:
            if not quiet:
                print(f"Passed: {test_files_list} (correctly returned {get_result_string(expected_result)})")
                if warning_list:
                    print(f"Warned: {[warning.message for warning in warning_list]}")
            passed += 1
        else:
            # print(
            #     actual_result,
            #     expected_result,
            #     get_result_string(actual_result),
            #     get_result_string(expected_result),
            # )
            print(
                f"Failed: {test_files_list} (returned {get_result_string(actual_result)} instead of {get_result_string(expected_result)})"
            )
            if error:
                print(f"Threw: {error}")
            failed_tests.append(str(test_files_list))
            # raise error
    print()
    print("=" * 50)
    print(f"Total passed: {passed}/{len(test_files_lists)}")
    if len(failed_tests) > 0:
        print(f"Failed tests: {', '.join(failed_tests)}")


def load_custom_testcases(test_names: List[str]):
    global_context = deepcopy(global_context_with_stdlib)
    warning_list = []

    for test_name in test_names:
        logging.info(f"Testing {test_name}")
        try:
            f = open(f"./custom_testcases/{test_name}.java", "r")
        except FileNotFoundError:
            print(f"Could not find test with name {test_name}.java, skipping...")
        else:
            with warnings.catch_warnings(record=True) as w:
                with f:
                    test_file_contents = f.read()
                    try:
                        res = lark.parse(test_file_contents)
                        logging.debug(res.pretty())
                        Weeder(f.name).visit(res)
                        print(res.pretty())
                        build_environment(res, global_context)
                    except Exception as e:
                        print(f"Failed {test_name}:", e)
                        raise e
            warning_list.extend(w)

    with warnings.catch_warnings(record=True) as w:
        try:
            static_check(global_context)
        except Exception as e:
            print(f"Failed {test_name}:", e)
            raise e
    warning_list.extend(w)

    if warning_list:
        print(f"Warned {test_name}")
    else:
        print(f"Passed {test_name}")


def load_path_testcases(paths: List[str]):
    global_context = deepcopy(global_context_with_stdlib)
    warning_list = []

    for path in paths:
        try:
            f = open(path, "r")
        except FileNotFoundError:
            print(f"Could not find test with name {path}, skipping...")
        else:
            with warnings.catch_warnings(record=True) as w:
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
            warning_list.extend(w)

    with warnings.catch_warnings(record=True) as w:
        try:
            static_check(global_context)
        except Exception as e:
            logging.exception(e)
            exit(42)

    warning_list.extend(w)
    for warning in warning_list:
        logging.warning(warning)

    if warning_list:
        exit(43)
    else:
        exit(0)


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
        load_assignment_testcases(args.a, quiet=args.q, custom_test_names=args.t)

    elif args.t is not None:
        load_custom_testcases(args.t)

    elif args.p is not None:
        load_path_testcases(args.p)

    elif args.g is not None:
        load_parse_trees(args.g)
