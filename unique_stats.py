import sys
import json
from stats import process_function_summary

# python hash_mapper.py $(find 0x* -name "*.sol") > hashes.json
# python unique_stats.py hashes.json $(find . -name function-summary.txt) > merged_stats.json
# cat merged_stats.json | jq '{tec: ([.inputs[].ec] | add), tcc: ([.inputs[].cc] | add)}'

# Function to merge multiple function summaries into one
def merge_summaries(existing_summary, new_summary):
    for file_hash, new_data in new_summary["inputs"].items():
        if file_hash in existing_summary["inputs"]:
            # Merge references list
            existing_summary["inputs"][file_hash]["references"].extend(new_data["references"])
        else:
            # Add new entry
            existing_summary["inputs"][file_hash] = new_data

    return existing_summary

# Function to process multiple function-summary.txt files and merge results
def process_and_merge_summaries(hashes_file, summary_files):
    merged_summary = {"inputs": {}}

    for summary_file in summary_files:
        print(f"Processing: {summary_file}", file=sys.stderr)
        try:
            result = process_function_summary(hashes_file, summary_file)  # Returns a dict
            merged_summary = merge_summaries(merged_summary, result)
        except Exception as e:
            print(f"Error processing {summary_file}: {e}", file=sys.stderr)
    
    return merged_summary

# Main execution block
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python unique_stats.py <hashes.json> <function-summary1.txt> [<function-summary2.txt> ...]", file=sys.stderr)
        sys.exit(1)

    hashes_file = sys.argv[1]  # First argument is the hashes.json file
    summary_files = sys.argv[2:]  # Remaining arguments are function-summary.txt files

    # Process and merge summaries
    merged_summary = process_and_merge_summaries(hashes_file, summary_files)
    print(json.dumps(merged_summary, indent=2))
