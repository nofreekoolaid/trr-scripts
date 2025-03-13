#!/usr/bin/env python3
import os
import json
import requests
import subprocess
import sys
import argparse

# Supported networks
NETWORKS = {
    "eth": "etherscan.io",
    "arb": "arbiscan.io"
}

def download_contract(contract_address, network="eth"):
    """
    Download and process the source code of a contract given its address and network.
    
    Parameters:
      contract_address (str): The contract address to fetch.
      network (str): The network identifier ("eth" or "arb").
      
    This function will:
      - Query the appropriate API (Etherscan/Arbiscan) for the contract's source code.
      - Save the raw API response to a file.
      - Use jq via subprocess to extract the source code, compiler version, and contract name.
      - Save the Solidity source(s) to file(s).
      - Generate a run_slither.sh script for further analysis if the compiler version is detected.
    """
    contract_address = contract_address.lower()
    if network not in NETWORKS:
        raise ValueError(f"Invalid network: {network}. Supported networks: {', '.join(NETWORKS.keys())}.")
    
    domain = NETWORKS[network]
    API_KEYS = {
        "eth": os.getenv("ETHERSCAN_API_KEY"),
        "arb": os.getenv("ARBISCAN_API_KEY")
    }
    API_KEY = API_KEYS[network]
    
    if not API_KEY:
        raise RuntimeError(f"Error: Please set the API_KEY environment variable (ETHERSCAN_API_KEY or ARBISCAN_API_KEY).")
    
    API_URL = f"https://api.{domain}/api?module=contract&action=getsourcecode&address={contract_address}&apikey={API_KEY}"
    response = requests.get(API_URL)
    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch contract from API (HTTP {response.status_code}).")
    
    os.makedirs(contract_address, exist_ok=True)
    raw_response_path = os.path.join(contract_address, "raw_response.json")
    with open(raw_response_path, "w", encoding="utf-8") as f:
        f.write(response.text)
    print(f"✅ Raw API response saved to {raw_response_path}.")

    try:
        jq_command = ["jq", "-r", ".result[0].SourceCode", raw_response_path]
        source_code = subprocess.check_output(jq_command, universal_newlines=True).strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Error running jq for source code: {e}")

    try:
        jq_command = ["jq", "-r", ".result[0].CompilerVersion", raw_response_path]
        raw_compiler_version = subprocess.check_output(jq_command, universal_newlines=True).strip()
        compiler_version = raw_compiler_version.split("+")[0].replace("v", "")
        print(f"✅ Detected Solidity compiler version: {compiler_version} (Original: {raw_compiler_version})")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Error fetching compiler version: {e}")
        compiler_version = None

    try:
        jq_command = ["jq", "-r", ".result[0].ContractName", raw_response_path]
        contract_name = subprocess.check_output(jq_command, universal_newlines=True).strip()
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Error fetching contract name: {e}")
        contract_name = None

    raw_source_path = os.path.join(contract_address, "raw_source_code.txt")
    with open(raw_source_path, "w", encoding="utf-8") as f:
        f.write(source_code)
    print(f"✅ Raw Solidity source saved to {raw_source_path}.")

    if source_code.startswith("{{") and source_code.endswith("}}"):
        source_code = source_code[1:-1]

    try:
        source_json = json.loads(source_code)
        source_files = source_json.get("sources", {}) if isinstance(source_json, dict) else {}
    except json.JSONDecodeError:
        sol_filename = f"{contract_name if contract_name else 'UnknownContract'}.sol"
        source_files = {sol_filename: {"content": source_code}}

    if not source_files:
        raise RuntimeError("❌ Error: No Solidity files found.")

    print(f"🔍 Extracted {len(source_files)} Solidity file(s) for contract {contract_address}.")

    last_file_path = None
    for file_path, content_dict in source_files.items():
        content = content_dict["content"] if isinstance(content_dict, dict) and "content" in content_dict else content_dict
        file_path = file_path.lstrip("/")
        full_path = os.path.join(contract_address, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        last_file_path = file_path  # Save for later use in slither script

    if compiler_version:
        script_path = os.path.join(contract_address, "run_slither.sh")
        script_content = f"""#!/bin/bash

if ! command -v solc-select &> /dev/null
then
    echo "❌ solc-select is not installed. Please install it first."
    exit 1
fi

solc-select install {compiler_version}
solc-select use {compiler_version}

slither ./{last_file_path} --print function-summary --disable-color 2> function-summary.txt
slither ./{last_file_path} --print inheritance --json - | jq '.' > inheritance.json
"""
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_content)
        os.chmod(script_path, 0o755)
        print(f"✅ Created `run_slither.sh` in directory {contract_address} for analysis.")
    else:
        print("⚠️ Skipping generation of run_slither.sh due to missing compiler version.")

def main():
    parser = argparse.ArgumentParser(description="Download and analyze Ethereum/Arbitrum contracts.")
    parser.add_argument("contract_address", help="Contract address to fetch source code for.")
    parser.add_argument("--network", choices=["eth", "arb"], default="eth", help="Network (eth=Ethereum, arb=Arbitrum)")
    args = parser.parse_args()
    
    try:
        download_contract(args.contract_address, args.network)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
