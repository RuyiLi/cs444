import glob
import logging
import os
import subprocess
import traceback
import warnings
from copy import deepcopy
from typing import List

from asm_tiling import tile_comp_unit
from build_environment import build_environment
from context import GlobalContext
from hierarchy_check import hierarchy_check
from lark import Lark, Tree, logger
from name_disambiguation import disambiguate_names
from optimizations import no_optimization, register_allocation
from reachability import analyze_reachability
from tir import IRExp, IRSeq
from tir_canonical import canonicalize_expression, canonicalize_statement
from tir_translation import lower_comp_unit
from tir_visitor import CanonicalVisitor
from type_check import type_check
from type_link import type_link
from weeder import Weeder

log = logging.getLogger(__name__)

grammar = ""
grammar_files = glob.glob(r"./grammar/**/*.lark", recursive=True)
for file in grammar_files:
    log.info(f"Loaded grammar {file[2:]}")
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
    format="\033[2m[%(levelname)s] %(filename)s:%(lineno)d in %(funcName)s\033[0m\n%(message)s\n",
    level=logging.ERROR,
)
# !!!!!! THIS NEEDS TO BE CHANGED EVERY ASSIGNMENT !!!!!!
STDLIB_VERSION = 6.1
ASSIGNMENT_NUMBER = int(str(STDLIB_VERSION).split(".")[0])

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
            log.error("Failed type_link")
        raise e

    try:
        hierarchy_check(context)
    except Exception as e:
        if not quiet:
            log.error("Failed hierarchy_check")
        raise e

    try:
        disambiguate_names(context)
    except Exception as e:
        if not quiet:
            log.error("Failed name disambiguation")
        raise e

    try:
        type_check(context)
    except Exception as e:
        if not quiet:
            log.error("Failed type check")
        raise e

    try:
        analyze_reachability(context)
    except Exception as e:
        if not quiet:
            log.error("Failed reachability analysis")
        raise e


OPTIMIZATIONS_MAP = {"opt-reg-only": register_allocation, "opt-none": no_optimization}


def parse_instructions(assembly_lines):
    instructions = []
    for line in assembly_lines:
        line = line.strip().split("#")[0]
        if not line:
            continue
        parts = line.split(None, 1)
        instruction = parts[0].strip()
        operands = parts[1].strip() if len(parts) > 1 else ""
        instructions.append((instruction, operands))
    return instructions


def perform_register_allocation(instructions):
    active_intervals = []
    register_map = {}
    register_pool = ["eax", "ebx", "ecx", "edx"]

    for index, (instruction, operands) in enumerate(instructions):
        for operand in operands.split(","):
            operand = operand.strip()
            if operand in register_map:
                active_intervals[register_map[operand]][2] = index
            else:
                active_intervals.append((operand, index, index))

    active_intervals.sort(key=lambda x: x[1])

    for interval in active_intervals:
        variable = interval[0]
        start_index = interval[1]
        end_index = interval[2]

        if variable not in register_map:
            if register_pool:
                register_map[variable] = register_pool.pop(0)
            else:
                register_map[variable] = "memory_location"  # How do I map to a memory location????

    return register_map


def write_optimized_file(file_path, instructions, register_map):
    with open(file_path, "w") as file:
        for instruction, operands in instructions:
            if operands and any(operand.strip() in register_map for operand in operands.split(",")):
                new_operands = ", ".join(
                    register_map.get(operand.strip(), operand.strip()) for operand in operands.split(",")
                )
                file.write(f"{instruction} {new_operands}\n")
            else:
                file.write(f"{instruction} {operands}\n")


def read_file_and_perform_allocation(file_path):
    with open(file_path, "r") as file:
        assembly_lines = file.readlines()

    instructions = parse_instructions(assembly_lines)
    allocated_registers = perform_register_allocation(instructions)
    write_optimized_file(file_path, instructions, allocated_registers)

    return allocated_registers


def assemble(context: GlobalContext, optimizations_set: set[str]):
    for i, child_context in enumerate(context.children):
        comp_unit = lower_comp_unit(child_context, context)

        # Lower functions into canonical form
        for k, v in comp_unit.functions.items():
            log.debug(f"old {v.body}")
            canonical = canonicalize_statement(v.body)

            visitor = CanonicalVisitor()
            result = visitor.visit(None, canonical)
            if not result:
                raise Exception(f"IR was not canonical!")

            v.body = canonical
            log.debug(f"{canonical}")

        # Lower fields into canonical form
        for k, v in comp_unit.fields.items():
            log.debug(f"old {v}")
            print(k)
            canonical = canonicalize_expression(v.expr)
            v.canonical = canonical

            visitor = CanonicalVisitor()
            result = visitor.visit(None, v)
            if not result:
                raise Exception(f"IR was not canonical!")

            log.debug(f"{canonical}")

        for optimization in optimizations_set:
            if optimization in OPTIMIZATIONS_MAP:
                optimization_function = OPTIMIZATIONS_MAP[optimization]
                comp_unit = optimization_function(comp_unit)
            else:
                print(f"Could not find optimization {optimization} in the OPTIMIZATIONS_MAP")
        asm = tile_comp_unit(comp_unit, context)
        f = open(f"output/test{i}.s", "w")
        f.write("\n".join(asm))
        f.write("\n")


ERROR = 42
EXCEPTION = 13
WARNING = 43
SUCCESS = 0

CORRECTLY_ASSEMBLED_OUTPUT = 123


def get_result_string(result: int):
    if result == ERROR:
        return "error"
    elif result == EXCEPTION:
        return "exception"
    elif result == WARNING:
        return "warning"
    elif result == SUCCESS:
        return "success"
    else:
        return result


def get_expected_result(path_name: str):
    possible_results = {"Je": ERROR, "J1e": EXCEPTION, "Jw": WARNING}
    for key, val in possible_results.items():
        if path_name.startswith(key):
            return val
    return SUCCESS


ASSEMBLE_SCRIPT_PATH = "assemble"


def get_assembled_output():
    try:
        os.chdir("output")
        result = subprocess.run(["bash", ASSEMBLE_SCRIPT_PATH], capture_output=True, check=True, text=True)
        return int(result.stdout)
    except subprocess.CalledProcessError:
        raise Exception("Failed to assemble the code")
    finally:
        os.chdir("..")


def load_assignment_testcases(
    assignment: int, quiet: bool, custom_test_names: List[str], optimizations: List[str]
):
    test_directory = os.path.join(os.getcwd(), f"assignment_testcases/a{assignment}")
    test_files_lists = []
    custom_test_names_set = set(custom_test_names) if custom_test_names else set()
    optimizations_set = set(optimizations) if optimizations else set()
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
        error_traceback = None
        expected_result = get_expected_result(test_files_list[0])
        try:
            assembled_output = CORRECTLY_ASSEMBLED_OUTPUT
            with warnings.catch_warnings(record=True) as warning_list:
                global_context = deepcopy(global_context_with_stdlib)
                for test_file in test_files_list:
                    if not quiet:
                        log.info(f"Testing {test_file}")
                    with open(os.path.join(test_directory, test_file), "r") as f:
                        test_file_contents = f.read()
                        res = lark.parse(test_file_contents)
                        Weeder(f.name).visit(res)
                        build_environment(res, global_context)
                        if not quiet:
                            log.info(f"{res.pretty()}")
                static_check(global_context, quiet)
                assemble(global_context, optimizations_set)
                assembled_output = get_assembled_output()
            if assembled_output == EXCEPTION:
                actual_result = EXCEPTION
            elif assembled_output != CORRECTLY_ASSEMBLED_OUTPUT:
                actual_result = assembled_output
            elif warning_list:
                actual_result = WARNING
            else:
                actual_result = SUCCESS
        except Exception as e:
            actual_result = ERROR
            error = e
            error_traceback = traceback.format_exc()

        if assignment != 4:
            if actual_result == WARNING:
                actual_result = SUCCESS

        if assignment != 5 and assignment != 6:
            if actual_result == EXCEPTION:
                actual_result = SUCCESS

        if actual_result == expected_result:
            log.info(f"Passed: {test_files_list} (correctly returned {get_result_string(expected_result)})")
            if warning_list:
                log.info(f"Warned: {[warning.message for warning in warning_list]}")
            passed += 1
        else:
            log.info(
                f"Failed: {test_files_list} (returned {get_result_string(actual_result)} instead of {get_result_string(expected_result)})"
            )
            if error:
                log.info(f"Threw: {error}")
                log.info(f"Traceback: {error_traceback}")
            if warning_list:
                log.info(f"Warned: {[warning.message for warning in warning_list]}")
            failed_tests.append(str(test_files_list))
            # raise error
    print("")
    print("=" * 50)
    print(f"Total passed: {passed}/{len(test_files_lists)}")
    if len(failed_tests) > 0:
        print(f"Failed tests: {', '.join(failed_tests)}")


def load_custom_testcases(test_names: List[str], optimizations: List[str]):
    global_context = deepcopy(global_context_with_stdlib)
    warning_list = []
    optimizations_set = set(optimizations) if optimizations else set()
    for test_name in test_names:
        log.info(f"Testing {test_name}")
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
                        log.debug(res.pretty())
                        Weeder(f.name).visit(res)
                        log.info(f"{res.pretty()}")
                        build_environment(res, global_context)
                    except Exception as e:
                        print(f"Failed {test_name}:", e)
                        log.info(f"Traceback: {traceback.format_exc()}")
                        raise e
            warning_list.extend(w)

    assembled_output = CORRECTLY_ASSEMBLED_OUTPUT

    with warnings.catch_warnings(record=True) as w:
        try:
            static_check(global_context)
            assemble(global_context, optimizations_set)
            assembled_output = get_assembled_output()
        except Exception as e:
            print(f"Failed {test_name}:", e)
            log.info(f"Traceback: {traceback.format_exc()}")
            raise e
    warning_list.extend(w)

    if assembled_output == EXCEPTION:
        print(f"Exceptioned {test_name}")
    elif warning_list:
        print(f"Warned {test_name}: ", [warning.message for warning in warning_list])
    else:
        print(f"Passed {test_name} (exit code {assembled_output})")


def load_path_testcases(paths: List[str], optimizations: List[str]):
    global_context = deepcopy(global_context_with_stdlib)
    optimizations_set = set(optimizations) if optimizations else set()
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
                        log.debug(res.pretty())
                        Weeder(f.name).visit(res)
                        build_environment(res, global_context)
                    except Exception as e:
                        log.exception(e)
                        log.exception(f"Traceback: {traceback.format_exc()}")
                        exit(42)
            warning_list.extend(w)

    with warnings.catch_warnings(record=True) as w:
        try:
            static_check(global_context)
            assemble(global_context, optimizations_set)
        except Exception as e:
            log.exception(e)
            log.exception(f"Traceback: {traceback.format_exc()}")
            exit(42)

    warning_list.extend(w)
    for warning in warning_list:
        log.warning(warning)

    if warning_list and ASSIGNMENT_NUMBER == 4:
        exit(43)
    else:
        exit(0)


def load_parse_trees(paths: List[str]):
    for path in paths:
        try:
            f = open(path, "r")
        except FileNotFoundError:
            print(f"Could not find test with name {path}, skipping...")
        else:
            with f:
                test_file_contents = f.read()
                try:
                    log.info(f"Parsing {f.name}")
                    res = lark.parse(test_file_contents)
                    Weeder(f.name).visit(res)
                    log.info(f"{res.pretty()}")
                except Exception as e:
                    log.error(e)
                    log.error(f"Traceback: {traceback.format_exc()}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Joos test suite utilities.")
    parser.add_argument("-a", type=int, help="Load assignment testcases")
    parser.add_argument("-t", type=str, nargs="+", help="Load custom testcases")
    parser.add_argument("-p", type=str, nargs="+", help="Load testcases from path")
    parser.add_argument("-q", action="store_true", default=False, help="Only log errors")
    parser.add_argument("-v", action="store_true", default=False, help="Log everything")
    parser.add_argument("-g", type=str, nargs="+", help="View parse tree of files")
    parser.add_argument("-o", type=str, nargs="+", help="Specify optimizations (e.g., opt-reg-only)")

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
        load_assignment_testcases(args.a, quiet=args.q, custom_test_names=args.t, optimizations=args.o)

    elif args.t is not None:
        load_custom_testcases(args.t, optimizations=args.o)

    elif args.p is not None:
        load_path_testcases(args.p, optimizations=args.o)

    elif args.g is not None:
        load_parse_trees(args.g)

    # i = 9
    # file_path = f"output/test{i}.s"
    # read_file_and_perform_allocation(file_path)
