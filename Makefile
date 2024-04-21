.PHONY: all clean zip unzip

define JOOSC_FILE_CONTENTS
#!/bin/bash

# Check if filename argument is provided
if [ "$$#" -eq 0 ]; then
    echo "Usage: $$0 <filename> [<filename> ...]"
    exit 1
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
python src/main.py -p "$$@"

# Check the exit status of the Python script
case $$? in
    0)
        echo "All input files are lexically and syntactically valid Joos 1W."
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
CURR_ASSIGNMENT = a6
all: joosc

clean:
	rm -f joosc
	rm -f joos_submission.zip
	rm -rf joos_submission
	rm -rf benchmarks/*/
	pip uninstall -r requirements.txt -y

joosc:
	pip install -r requirements.txt
	echo "$$JOOSC_FILE_CONTENTS" > joosc
	chmod +x joosc

zip:
	rm -rf joos_submission.zip
	git --no-pager log > $(CURR_ASSIGNMENT).log
	find . -type f -name "*.py" -not -path "./env/*" | grep -v "__pycache__" | xargs zip -r joos_submission.zip custom_testcases grammar requirements.txt Makefile $(CURR_ASSIGNMENT).log
	rm -f $(CURR_ASSIGNMENT).log

unzip:
	rm -rf joos_submission
	mkdir joos_submission
	unzip joos_submission.zip -d joos_submission
