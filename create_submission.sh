#!/bin/bash

# Ensure the script is run from the root directory of the project
if [ ! -f "Makefile" ]; then
    echo "Error: Makefile not found. Make sure you are in the project root directory."
    exit 1
fi

# Create a temporary directory for the submission
temp_dir="joos_submission_temp"
old_submission="joos_submission.zip"

mkdir -p $temp_dir

# Copy only necessary files to the temp directory
rsync -aP --exclude=$temp_dir --exclude=$old_submission * $temp_dir
rm -rf $temp_dir/.git  # Exclude the .git directory

# Create a .zip archive
zip -r joos_submission.zip $temp_dir

# Clean up the temporary directory
# rm -rf $temp_dir

echo "Submission archive 'joos_submission.zip' created successfully."
