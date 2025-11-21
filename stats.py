import ast
import json
import os
import re
import subprocess
import sys

from tdp import compute_tdp_from_file  # Import from tdp.py


def parse_external_calls(external_calls):
    try:
        if isinstance(external_calls, list):
            return len(external_calls)  # Already a list, return its length

        elif isinstance(external_calls, str):
            # Normalize multi-line strings by joining and stripping spaces
            external_calls = " ".join(external_calls.splitlines()).strip()

            # Safely evaluate as a Python literal (list)
            parsed_ec = ast.literal_eval(external_calls)

            # Return length only if the result is a list
            return len(parsed_ec) if isinstance(parsed_ec, list) else 0

    except (SyntaxError, ValueError):
        return 0

    return 0


# Function to parse Slither function summary output
def parse_function_summary(data):
    headers = []
    contract_summaries = {}
    current_contract = None
    row_pattern = re.compile(r"^\|(.+)\|$")
    contract_name_pattern = re.compile(r"Contract\s+(\w+)")

    # Split sections by INFO:Printers, each representing a contract
    sections = data.split("INFO:Printers:")

    for section in sections:
        lines = section.split("\n")
        contract_match = contract_name_pattern.search(section)

        if contract_match:
            current_contract = contract_match.group(1)
            contract_summaries[current_contract] = {"ec": 0, "cc": 0}
        else:
            continue  # Skip if contract name is not found

        for line in lines:
            if "Function" in line and "Cyclomatic Complexity" in line:
                headers = [h.strip() for h in line.split("|")[1:-1]]
                continue

            match = row_pattern.match(line)
            if match and current_contract:
                row_values = [v.strip() for v in match.group(1).split("|")]
                if len(row_values) == len(headers):
                    func_data = dict(zip(headers, row_values))

                    try:
                        cc_key = next(
                            (key for key in func_data.keys() if key.startswith("Cycl")), None
                        )
                        raw_cc = func_data.get(cc_key, "0")
                        cc = int(raw_cc) if raw_cc.isdigit() else 0
                    except ValueError:
                        cc = 0

                    external_calls = func_data.get("External Calls", "[]")
                    ec = parse_external_calls(external_calls)

                    contract_summaries[current_contract]["cc"] += cc
                    contract_summaries[current_contract]["ec"] += ec

    return contract_summaries


# Function to map contract names to file hashes and paths using hashes.json
def map_contracts_to_hashes(hashes_file, base_dir):
    with open(hashes_file, encoding="utf-8") as f:
        hashes_data = json.load(f)

    base_dir = os.path.abspath(base_dir)  # Normalize base directory path
    file_map = {}

    for file_hash, file_entries in hashes_data.items():
        for entry in file_entries:
            filepath = os.path.abspath(os.path.normpath(entry["filepath"]))  # Normalize file path
            if filepath.startswith(base_dir):
                contract_name = os.path.basename(filepath).replace(".sol", "")
                if file_hash not in file_map:
                    file_map[file_hash] = []
                file_map[file_hash].append({"contract_name": contract_name, "filepath": filepath})

    return file_map


# Run cloc and return number of Solidity lines
def get_solidity_loc(filepath):
    try:
        result = subprocess.run(
            ["cloc", "--json", filepath], capture_output=True, text=True, check=True
        )
        data = json.loads(result.stdout)
        return data.get("Solidity", {}).get("code", 0)
    except Exception:
        return 0


# Function to process function summary and map contracts to hashes
def process_function_summary(hashes_file, function_summary_file):
    base_dir = os.path.dirname(function_summary_file)  # Get base directory
    contract_hash_map = map_contracts_to_hashes(hashes_file, base_dir)
    contract_data = {}

    try:
        with open(function_summary_file, encoding="utf-8") as f:
            data = f.read()

        # Parse function summary
        summaries = parse_function_summary(data)

        # Store parsed summaries in contract_data
        for contract, stats in summaries.items():
            for file_hash, references in contract_hash_map.items():
                if any(ref["contract_name"] == contract for ref in references):
                    loc = get_solidity_loc(references[0]["filepath"])  # Assume first match for LOC
                    tdp = compute_tdp_from_file(references[0]["filepath"])  # TDP per file
                    contract_data[file_hash] = {
                        "ec": stats["ec"],
                        "cc": stats["cc"],
                        "loc": loc,
                        "tdp": tdp,
                        "references": references,
                    }
    except Exception as e:
        print(f"Error processing {function_summary_file}: {e}", file=sys.stderr)

    return {"inputs": contract_data}


# Main execution block
if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python stats.py <hashes.json> <function-summary.txt>", file=sys.stderr)
        sys.exit(1)

    hashes_file = sys.argv[1]  # First argument is the hashes.json file
    function_summary_file = sys.argv[2]  # Second argument is the function-summary.txt file

    # Process and output JSON
    contract_data = process_function_summary(hashes_file, function_summary_file)
    print(json.dumps(contract_data, indent=2))
