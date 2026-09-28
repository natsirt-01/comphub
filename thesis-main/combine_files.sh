#!/bin/bash
# combine_files.sh
# Combines all files in the current directory AND its subdirectories
# into one text file, each preceded by its relative path/filename.
#
# Usage:
#    chmod +x combine_files.sh
#   ./combine_files.sh                 -> outputs to combined_output.txt
#   ./combine_files.sh output.txt      -> outputs to output.txt
#   ./combine_files.sh                 -> outputs to combined_output.txt
#   ./combine_files.sh output.txt      -> outputs to output.txt

OUTPUT_FILE="${1:-combined_output.txt}"
SCRIPT_NAME="$(basename "$0")"

# Remove old output file if it exists (so it doesn't include itself)
rm -f "$OUTPUT_FILE"

# Recursively find all regular files, sorted, null-delimited (safe for spaces/newlines)
while IFS= read -r -d '' file; do
    # Strip leading "./" so output shows "dir/main.py" instead of "./dir/main.py"
    rel_path="${file#./}"

    # Skip the script itself and the output file
    [ "$rel_path" == "$SCRIPT_NAME" ] && continue
    [ "$rel_path" == "$OUTPUT_FILE" ] && continue

    {
        echo "$rel_path"
        cat "$rel_path"
        echo ""   # blank line for spacing between files
    } >> "$OUTPUT_FILE"
done < <(find . -type f -print0 | sort -z)

echo "Done! Combined files into $OUTPUT_FILE"