import os
import json
import argparse
import subprocess
from tdp import calculate_tdp
from function_summary import parse_function_summary
from inheritance import calculate_inheritance_depth

# Helper function to run subprocess commands with optional debugging
def run_command(command, allow_empty=False):
    """Runs a shell command and returns its output. Optionally prints the command for debugging."""
    if args.debug:
        print(f"[DEBUG] Running: {' '.join(command)}")

    try:
        output = subprocess.check_output(
            command, text=True, stderr=subprocess.STDOUT  # Merge stderr into stdout
        ).strip()

        if not output and not allow_empty:
            raise ValueError(f"Command returned empty output: {' '.join(command)}")

        return output
    except subprocess.CalledProcessError as e:
        return f"Error: {e}"
    except ValueError as e:
        return f"Error: {e}"

def analyze_contract(flatfile, debug=False):
    """Runs all Solidity contract analysis steps and returns a structured JSON result."""
    global args
    args = argparse.Namespace(debug=debug)

    if not os.path.isfile(flatfile):
        return {"Error": f"File '{flatfile}' not found."}

    results = {}

    # 1. Calculate LOC (Lines of Code)
    results["LOC"] = run_command(["wc", "-l", flatfile]).split()[0]

    # 2. Calculate sLOC (Source Lines of Code)
    sloc_output = run_command(["cloc", flatfile, "--quiet", "--json"])
    try:
        sloc_data = json.loads(sloc_output)
        results["sLOC"] = sloc_data.get("Solidity", {}).get("code", "N/A")
    except json.JSONDecodeError:
        results["sLOC"] = "Error: Invalid JSON from cloc"

    # 3. Calculate TDP (Total Decision Points)
    try:
        with open(flatfile, "r") as f:
            solidity_code = f.readlines()
        results["TDP"] = calculate_tdp(solidity_code)
    except Exception as e:
        results["TDP"] = f"Error: {e}"

    # 4. Run Slither Function Summary (for TCC and TEC)
    slither_output = run_command(["slither", flatfile, "--print", "function-summary", "--disable-color"], allow_empty=True)
    try:
        results.update(parse_function_summary(slither_output))
    except Exception as e:
        results["TCC & TEC"] = f"Error: {e}"

    # 5. Run Slither Inheritance Analysis (for ID)
    slither_json_output = run_command(["slither", flatfile, "--print", "inheritance", "--json", "-"], allow_empty=True)
    try:
        slither_json = json.loads(slither_json_output)
        results.update(calculate_inheritance_depth(slither_json))
    except json.JSONDecodeError:
        results["Inheritance Depth (ID)"] = "Error: Invalid or empty JSON"

    return results

# Run only if executed as a script (not when imported)
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze Solidity contract complexity and structure metrics.")
    parser.add_argument("flatfile", type=str, help="Path to the flattened Solidity file (flat.sol)")
    parser.add_argument("--debug", action="store_true", help="Print debug information before running commands")
    args = parser.parse_args()

    # Run the analysis
    analysis_result = analyze_contract(args.flatfile, debug=args.debug)
    
    # Print JSON output
    print(json.dumps(analysis_result, indent=2))
