.PHONY: all clean zip unzip joosc

define JOOSC_FILE_CONTENTS
#!/bin/bash

# Define usage message
usage() {
	echo "Usage: $$0 [-h] [--opt-none] <filename> [<filename> ...]"
	echo "Options:"
	echo "  -h, --help   Show this help message and exit"
	echo "  --opt-none   Disable optimizations including register allocation"
	exit 1
}

# Parse command-line options
while [ $$# -gt 0 ]; do
	case "$$1" in
		-h|--help)
			usage
			;;
		--opt-none)
			opt_none=true
			shift
			;;
		*)
			break
			;;
	esac
done

# Check if filename argument is provided
if [ "$$#" -eq 0 ]; then
	echo "Error: No input files provided."
	usage
fi

# Loop through each filename provided
for filename in "$$@"; do
	# Check if the input file exists
	if [ ! -f "$$filename" ]; then
		echo "Error: File '$$filename' not found."
		exit 1
	fi
done

# Call the Python script with all input filenames
if [ "$$opt_none" = true ]; then
	python src/main.py -o "opt-none" -p "$$@"
else
	python src/main.py -p "$$@"
fi

# Check the exit status of the Python script
case $$? in
	0)
		echo "All input files are lexically and syntactically valid Joos 1W."
		;;
	13)
		echo "Error: An exception occurred during compilation."
		exit 13
		;;
	42)
		echo "Error: One or more input files are not lexically or syntactically valid Joos 1W."
		exit 42
		;;
	43)
		echo "Warning: One or more input files have warnings but are still lexically and syntactically valid Joos 1W."
		exit 43
		;;
	*)
		echo "Error: Your compiler crashed while processing the input files."
		exit 2
		;;
esac

exit 0
endef

export JOOSC_FILE_CONTENTS

TEST_DIR := test
# !!!!!! THIS NEEDS TO BE CHANGED EVERY ASSIGNMENT !!!!!!
CURR_ASSIGNMENT = a5
all: joosc

clean:
	rm -f joosc
	rm -f joos_submission.zip
	rm -rf joos_submission
	rm -rf benchmarks/*/
	pip uninstall -r requirements.txt -y

joosc:
	rm -f joosc
	pip install -r requirements.txt
	echo "$$JOOSC_FILE_CONTENTS" > joosc
	chmod +x joosc

bench:
	rm -f benchmarks/results.csv
	touch benchmarks/results.csv
	find benchmarks -mindepth 2 -type f | while read -r file; do \
		start_unoptimized=$$(date +%s%3N); \
		python src/main.py -q -p "$$file" > /dev/null; \
		end_unoptimized=$$(date +%s%3N); \
		duration_unoptimized=$$(($$end_unoptimized - $$start_unoptimized)); \
		opt=$$(basename "$$(dirname "$$file")"); \
		start_optimized=$$(date +%s%3N); \
		python src/main.py -q -p "$$file" -o "$$opt"> /dev/null; \
		end_optimized=$$(date +%s%3N); \
		duration_optimized=$$(($$end_optimized - $$start_optimized)); \
		speedup=$$(echo "scale=3; $$duration_unoptimized / $$duration_optimized" | bc); \
		benchmark_name=$$(basename "$$file"); \
		echo "$$opt,$$benchmark_name,$$duration_optimized,$$duration_unoptimized,$$speedup" >> benchmarks/results.csv; \
	done

zip:
	rm -rf joos_submission.zip
	git --no-pager log > $(CURR_ASSIGNMENT).log
	find . -type f -name "*.py" -not -path "./env/*" | grep -v "__pycache__" | xargs zip -r joos_submission.zip custom_testcases grammar requirements.txt Makefile $(CURR_ASSIGNMENT).log
	rm -f $(CURR_ASSIGNMENT).log

unzip:
	rm -rf joos_submission
	mkdir joos_submission
	unzip joos_submission.zip -d joos_submission
