import os
import sys
import json
import requests
import subprocess

# Check for contract address argument
if len(sys.argv) < 2:
    print("❌ Error: Please provide a contract address.")
    print("👉 Usage: python rebuild_project.py <contract_address>")
    exit(1)

# Contract address from command line argument
CONTRACT_ADDRESS = sys.argv[1].lower()
NETWORK = "arbiscan.io"

# Set your Arbiscan API key
ARBISCAN_API_KEY = os.getenv("ARBISCAN_API_KEY")
if not ARBISCAN_API_KEY:
    print("❌ Error: Please set ARBISCAN_API_KEY as an environment variable.")
    exit(1)

# API URL for fetching verified source code
API_URL = f"https://api.{NETWORK}/api?module=contract&action=getsourcecode&address={CONTRACT_ADDRESS}&apikey={ARBISCAN_API_KEY}"

# Fetch contract source
response = requests.get(API_URL)

# Save raw response for debugging
with open("raw_response.json", "w", encoding="utf-8") as f:
    f.write(response.text)

print("✅ Raw API response saved to raw_response.json.")

# Extract `SourceCode` field using jq
try:
    jq_command = ["jq", "-r", ".result[0].SourceCode", "raw_response.json"]
    source_code = subprocess.check_output(jq_command, universal_newlines=True).strip()
except subprocess.CalledProcessError as e:
    print(f"❌ Error running jq: {e}")
    exit(1)

# Extract and clean up compiler version
try:
    jq_command = ["jq", "-r", ".result[0].CompilerVersion", "raw_response.json"]
    raw_compiler_version = subprocess.check_output(jq_command, universal_newlines=True).strip()

    # Strip everything after `+` to remove commit hash
    compiler_version = raw_compiler_version.split("+")[0].replace("v", "")

    print(f"✅ Detected Solidity compiler version: {compiler_version} (Original: {raw_compiler_version})")

except subprocess.CalledProcessError as e:
    print(f"❌ Error fetching compiler version: {e}")
    compiler_version = None

# Extract main contract name
try:
    jq_command = ["jq", "-r", ".result[0].ContractName", "raw_response.json"]
    contract_name = subprocess.check_output(jq_command, universal_newlines=True).strip()
except subprocess.CalledProcessError as e:
    print(f"❌ Error fetching contract name: {e}")
    contract_name = None

# Save raw extracted Solidity source for debugging
with open("raw_source_code.txt", "w", encoding="utf-8") as f:
    f.write(source_code)

print("✅ Raw Solidity source saved to raw_source_code.txt.")


# 🔥 Step 1: Detect and Remove Extra `{}` Wrapping
if source_code.startswith("{{") and source_code.endswith("}}"):
    print("⚠️ Warning: Extra `{}` detected. Removing them.")
    source_code = source_code[1:-1]  # Remove first and last `{}`

# 🔥 Step 2: Determine if `source_code` is JSON or raw Solidity
try:
    source_json = json.loads(source_code)
    if isinstance(source_json, dict) and "sources" in source_json:
        source_files = source_json["sources"]
    else:
        raise ValueError("JSON doesn't contain 'sources' key.")
except json.JSONDecodeError:
    # ❗ If JSON parsing fails, assume it's a **single Solidity file**
    print("⚠️ Warning: Single-source contract detected. Treating as raw Solidity.")
    
    # Extract contract name from metadata
    try:
        jq_command = ["jq", "-r", ".result[0].ContractName", "raw_response.json"]
        contract_name = subprocess.check_output(jq_command, universal_newlines=True).strip()
    except subprocess.CalledProcessError:
        print("❌ Error: Failed to extract contract name. Using 'UnknownContract.sol' instead.")
        contract_name = "UnknownContract"

    # Name the file dynamically based on the contract name
    sol_filename = f"{contract_name}.sol"
    source_files = {sol_filename: {"content": source_code}}

# Ensure JSON is correctly parsed
if not isinstance(source_files, dict):
    print("❌ Error: Unexpected format for source files.")
    exit(1)

# Ensure JSON is correctly parsed
if not isinstance(source_files, dict):
    print("❌ Error: Unexpected format for source files.")
    exit(1)

# 🔍 Debug: Print extracted file paths
print(f"🔍 Extracted {len(source_files)} Solidity files:")
for key in list(source_files.keys())[:5]:  # Show first 5 files
    print(f"   - {key}")

# ✅ Create project directory using the contract address
project_dir = CONTRACT_ADDRESS
os.makedirs(project_dir, exist_ok=True)

# ✅ Save each Solidity file in its **correct directory structure**
default_contract_path = None
exact_match = None
partial_match = None
flat_sol_path = os.path.join(project_dir, "flat.sol")

with open(flat_sol_path, "w", encoding="utf-8") as flat_file:
    flat_file.write("// Flattened Solidity Contract\n\n")

    for file_path, content_dict in source_files.items():
        if isinstance(content_dict, dict) and "content" in content_dict:
            content = content_dict["content"]
        else:
            content = content_dict

        if not file_path.endswith(".sol"):
            continue

        file_path = file_path.lstrip("/")
        full_path = os.path.join(project_dir, file_path)

        filename = os.path.basename(file_path).replace(".sol", "")

        if contract_name:
            if filename.lower() == contract_name.lower():
                exact_match = file_path
            elif contract_name.lower() in filename.lower():
                partial_match = file_path

        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        flat_file.write(f"\n// File: {file_path}\n\n")
        flat_file.write(content)
        flat_file.write("\n\n")

# Prefer exact match; otherwise, fall back to partial match
default_contract_path = exact_match if exact_match else partial_match

if default_contract_path:
    print(f"✅ Selected contract for analysis: {default_contract_path} (Default contract: {contract_name})")
else:
    print("❌ No exact match found. Using flat.sol instead.")
    default_contract_path = "flat.sol"  # Fallback to flattened file

# ✅ Generate `run_slither.sh` script
script_path = os.path.join(project_dir, "run_slither.sh")
script_content = f"""#!/bin/bash

# Ensure solc-select is installed
if ! command -v solc-select &> /dev/null
then
    echo "❌ solc-select is not installed. Please install it first."
    exit 1
fi

# Install and use the correct Solidity compiler version
solc-select install {compiler_version}
solc-select use {compiler_version}

# Run function summary analysis
slither ./{default_contract_path} --print function-summary --disable-color 2> function-summary.txt

# Run inheritance analysis and save as JSON
slither ./{default_contract_path} --print inheritance --json - | jq '.' > inheritance.json
"""

with open(script_path, "w", encoding="utf-8") as f:
    f.write(script_content)

os.chmod(script_path, 0o755)

print(f"✅ Created `run_slither.sh` to analyze `{default_contract_path}` (Default contract: {contract_name})")
print(f"👉 Run: `cd {project_dir} && bash run_slither.sh`")
