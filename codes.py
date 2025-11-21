import json
import os
import subprocess
import sys
from code import analyze_contracts_via_summary  # (or code_metrics if renamed)


def run_solc_select(version):
    subprocess.run(["solc-select", "install", version], check=True)
    subprocess.run(["solc-select", "use", version], check=True)
    print(f"✅ solc-select set to version {version}")


def process_contract_directory(address):
    contract_dir = address.lower()
    details_path = os.path.join(contract_dir, "contract_details.json")
    if not os.path.isfile(details_path):
        print(f"⚠️  Missing contract_details.json in {contract_dir}")
        return

    with open(details_path) as f:
        details = json.load(f)

    compiler_version = details.get("compiler_version")
    entry_file = details.get("main_contract_path")

    if not compiler_version or not entry_file:
        print(f"❌ Incomplete contract details in {details_path}")
        return

    full_entry_path = os.path.join(contract_dir, entry_file)
    if not os.path.isfile(full_entry_path):
        print(f"❌ Entry file not found: {full_entry_path}")
        return

    run_solc_select(compiler_version)
    print(f"🔍 Analyzing {entry_file}...")

    try:
        prev_cwd = os.getcwd()
        os.chdir(contract_dir)  # 🔧 CHANGE WORKING DIR
        result = analyze_contracts_via_summary(entry_file)
        os.chdir(prev_cwd)  # 🔄 RESTORE DIR

        output_path = os.path.join(contract_dir, "code.json")
        with open(output_path, "w") as out:
            json.dump(result, out, indent=2)
        print(f"✅ Output saved to {output_path}")
    except Exception as e:
        print(f"❌ Analysis failed for {entry_file}: {e}")
        if os.getcwd() != prev_cwd:
            os.chdir(prev_cwd)


def main(addresses_file):
    with open(addresses_file) as f:
        addresses = [line.strip() for line in f if line.strip()]

    for address in addresses:
        print(f"\n📦 Processing {address}")
        process_contract_directory(address)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python codes.py <addresses.txt>")
        sys.exit(1)

    main(sys.argv[1])
