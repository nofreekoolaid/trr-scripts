import sys
import json
import subprocess
import hashlib
from slither.slither import Slither
from pathlib import Path
from tdp import compute_tdp_from_file  # Import from tdp.py


def get_inheritance_depth_recursive(contract, visited=None):
    if visited is None:
        visited = set()
    if contract in visited or not contract.inheritance:
        return 0
    visited.add(contract)
    return 1 + max((get_inheritance_depth_recursive(base, visited) for base in contract.inheritance), default=0)


def get_cloc_sloc(filepath):
    try:
        result = subprocess.run([
            "cloc", filepath, "--json"
        ], capture_output=True, text=True, check=True)
        cloc_data = json.loads(result.stdout)
        return cloc_data.get("Solidity", {}).get("code", 0)
    except Exception as e:
        print(f"⚠️ Error running cloc on {filepath}: {e}")
        return 0


def compute_md5(filepath):
    try:
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception as e:
        print(f"⚠️ Error computing MD5 for {filepath}: {e}")
        return None


def find_contract_file(contract_name):
    matches = []
    for path in Path.cwd().rglob("*.sol"):
        try:
            with open(path, 'r') as f:
                if f"contract {contract_name} " in f.read():
                    matches.append(str(path))
        except Exception as e:
            print(f"⚠️ Error reading file {path}: {e}")

    if len(matches) > 1:
        raise RuntimeError(f"❌ Multiple files found for contract '{contract_name}': {matches}")
    elif not matches:
        return None
    return matches[0]


def analyze_contracts_via_summary(sol_file_path):
    slither = Slither(sol_file_path)
    result = []
    max_inheritance_depth = 0
    seen_files = set()

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
            if contract_file:
                if contract_file in seen_files:
                    raise RuntimeError(f"❌ Duplicate file reference in output: {contract_file}")
                seen_files.add(contract_file)

                tdp = compute_tdp_from_file(contract_file)
                sloc = get_cloc_sloc(contract_file)
                file_hash = compute_md5(contract_file)
            else:
                tdp = 0
                sloc = 0
                file_hash = None

            result.append({
                "contract": name,
                "total_tcc": total_tcc,
                "total_tec": total_tec,
                "inheritance_depth": inheritance_depth,
                "sloc": sloc,
                "tdp": tdp,
                "md5": file_hash,
                "source_path": contract_file
            })

        except Exception as e:
            print(f"⚠️ Error processing contract {contract.name}: {e}")

    return {
        "max_inheritance_depth": max_inheritance_depth,
        "contracts": result
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python main.py <contract.sol>")
    else:
        analysis = analyze_contracts_via_summary(sys.argv[1])
        print(json.dumps(analysis, indent=2))
