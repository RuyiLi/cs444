.PHONY: all clean install joosc zip

define JOOSC_FILE_CONTENTS
#!/bin/bash

# Check if filename argument is provided
if [ $$# -ne 1 ]; then
    echo "Usage: $$0 <filename>"
    exit 1
fi

# Assign the filename argument to a variable
filename=$$1

# Check if the input file exists
if [ ! -f "$$filename" ]; then
    echo "Error: File '$$filename' not found."
    exit 1
fi

# Call the Python script with the input filename
python main.py -p $$filename

# Check the exit status of the Python script
case $$? in
    0)
        echo "The input file is lexically and syntactically valid Joos 1W."
        exit 0
        ;;
    42)
        echo "Error: The input file is not lexically or syntactically valid Joos 1W."
        exit 42
        ;;
    *)
        echo "Error: Your compiler crashed."
        exit 1
        ;;
esac
endef

export JOOSC_FILE_CONTENTS

TEST_DIR := test
CURR_ASSIGNMENT = a1
all: joosc

clean:
	rm -f joosc
	rm -f joos_submission.zip
	rm -rf joos_submission
	pip uninstall -r requirements.txt -y

joosc:
	pip install -r requirements.txt
	echo "$$JOOSC_FILE_CONTENTS" > joosc
	chmod +x joosc

zip:
	git --no-pager log > $(CURR_ASSIGNMENT).log
	zip -r joos_submission.zip custom_testcases grammar main.py weeder.py requirements.txt Makefile $(CURR_ASSIGNMENT).log
	rm -f $(CURR_ASSIGNMENT).log

unzip:
	rm -rf joos_submission
	mkdir joos_submission
	unzip joos_submission.zip -d joos_submission