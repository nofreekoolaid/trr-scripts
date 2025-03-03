import subprocess
import argparse
import os
import json

# Set up argument parsing
parser = argparse.ArgumentParser(description="Analyze Solidity contract complexity and structure metrics.")
parser.add_argument("flatfile", type=str, help="Path to the flattened Solidity file (flat.sol)")
args = parser.parse_args()

# Ensure the flat.sol file exists
if not os.path.isfile(args.flatfile):
    print(f"❌ Error: File '{args.flatfile}' not found.")
    exit(1)

# Initialize results dictionary
results = {}

# 1️⃣ Calculate LOC (Lines of Code)
try:
    loc_output = subprocess.check_output(["wc", "-l", args.flatfile], text=True)
    results["LOC"] = int(loc_output.split()[0])
except Exception as e:
    results["LOC"] = f"Error: {e}"

# 2️⃣ Calculate sLOC (Source Lines of Code)
try:
    sloc_output = subprocess.check_output(["cloc", args.flatfile, "--quiet", "--json"], text=True)
    sloc_data = json.loads(sloc_output)
    results["sLOC"] = sloc_data.get("Solidity", {}).get("code", "N/A")
except Exception as e:
    results["sLOC"] = f"Error: {e}"

# 3️⃣ Calculate TDP (Total Decision Points)
try:
    tdp_output = subprocess.check_output(["python", "~/work/src/github.com/nofreekoolaid/trr-scripts/tdp.py", args.flatfile], text=True)
    results["TDP"] = tdp_output.strip()
except Exception as e:
    results["TDP"] = f"Error: {e}"

# 4️⃣ Run Slither Function Summary (for TCC & TEC)
func_summary_file = "function-summary.txt"
try:
    subprocess.run(["slither", args.flatfile, "--print", "function-summary", "--disable-color"], stderr=open(func_summary_file, "w"), check=True)
    func_summary_output = subprocess.check_output(["python", "~/work/src/github.com/nofreekoolaid/trr-scripts/function-summary.py", func_summary_file], text=True)
    results["TCC & TEC"] = func_summary_output.strip()
except Exception as e:
    results["TCC & TEC"] = f"Error: {e}"

# 5️⃣ Run Slither Inheritance Analysis (for ID)
inheritance_file = "inheritance.json"
try:
    subprocess.run(["slither", args.flatfile, "--print", "inheritance", "--json", "-"], stdout=open(inheritance_file, "w"), check=True)
    inheritance_output = subprocess.check_output(["python", "~/work/src/github.com/nofreekoolaid/trr-scripts/inheritance.py", inheritance_file], text=True)
    results["Inheritance Depth (ID)"] = inheritance_output.strip()
except Exception as e:
    results["Inheritance Depth (ID)"] = f"Error: {e}"

# Print final structured output
print("\n=================== Solidity Contract Analysis ===================")
for key, value in results.items():
    print(f"✅ {key}: {value}")
print("==================================================================")
