import os
import sys
import json
import subprocess
import hashlib
import re
from slither.slither import Slither
from pathlib import Path
from tdp import compute_tdp_from_file, remove_comments  # Import from tdp.py


def get_inheritance_depth_recursive(contract, visited=None):
    if visited is None:
        visited = set()
    if contract in visited or not contract.inheritance:
        return 0
    visited.add(contract)
    return 1 + max((get_inheritance_depth_recursive(base, visited) for base in contract.inheritance), default=0)


def get_cloc_sloc(filepath):
    try:
        result = subprocess.run(["cloc", filepath, "--json"],
                                capture_output=True, text=True, check=True)
        cloc_data = json.loads(result.stdout)
        return cloc_data.get("Solidity", {}).get("code", 0)
    except Exception as e:
        print(f"⚠️ Error running cloc on {filepath}: {e}")
        return 0


def compute_md5(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        cleaned_lines = remove_comments(lines, "sol")
        cleaned_content = "\n".join(cleaned_lines)
        return hashlib.md5(cleaned_content.encode("utf-8")).hexdigest()
    except Exception as e:
        print(f"⚠️ Error computing MD5 for {filepath}: {e}")
        return None


def extract_contract_names(lines):
    names = {"contract": [], "library": [], "interface": [], "struct": []}
    for line in lines:
        line = line.strip()
        match = re.match(r"^(abstract\s+)?(contract|library|interface|struct)\s+(\w+)", line)
        if match:
            kind = match.group(2)
            name = match.group(3)
            names[kind].append(name)
    return names


def find_contract_file(contract_name):
    matches = []
    for path in Path.cwd().rglob("*.sol"):
        try:
            with open(path, 'r') as f:
                lines = f.readlines()
                names = extract_contract_names(lines)
                if contract_name in sum(names.values(), []):
                    matches.append(str(path))
        except Exception as e:
            print(f"⚠️ Error reading file {path}: {e}")

    if len(matches) > 1:
        print(f"⚠️ Multiple files matched for contract '{contract_name}': {matches}, picking first.")
    elif not matches:
        return None
    return matches[0] if matches else None


def analyze_contracts_via_summary(sol_file_path):
    slither = Slither(sol_file_path)
    contracts = []
    files_info = {}
    max_inheritance_depth = 0

    for contract in slither.contracts:
        try:
            (
                name,
                _inheritance,
                _vars,
                func_summaries,
                modif_summaries,
            ) = contract.get_summary()

            total_tcc = 0
            total_tec = 0

            for (
                _c_name,
                _f_name,
                _visi,
                _modifiers,
                _read,
                _write,
                _internal_calls,
                external_calls,
                cyclomatic_complexity,
            ) in func_summaries + modif_summaries:
                total_tcc += cyclomatic_complexity
                total_tec += len(external_calls)

            inheritance_depth = get_inheritance_depth_recursive(contract)
            max_inheritance_depth = max(max_inheritance_depth, inheritance_depth)

            contract_file = find_contract_file(name)
            rel_path = str(Path(contract_file).relative_to(Path.cwd())) if contract_file else None
            file_hash = compute_md5(contract_file) if contract_file else None

            # If file not already added, collect sloc/tdp stats for it
            if contract_file and rel_path not in files_info:
                tdp = compute_tdp_from_file(contract_file)
                sloc = get_cloc_sloc(contract_file)
                files_info[rel_path] = {
                    "file": rel_path,
                    "md5": file_hash,
                    "sloc": sloc,
                    "tdp": tdp
                }

            contracts.append({
                "contract": name,
                "total_tcc": total_tcc,
                "total_tec": total_tec,
                "inheritance_depth": inheritance_depth,
                "source_path": rel_path,
                "md5": file_hash
            })

        except Exception as e:
            print(f"⚠️ Error processing contract {contract.name}: {e}")

    return {
        "max_inheritance_depth": max_inheritance_depth,
        "contracts": contracts,
        "files": list(files_info.values())
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python code.py <contract.sol>")
    else:
        analysis = analyze_contracts_via_summary(sys.argv[1])
        print(json.dumps(analysis, indent=2))
