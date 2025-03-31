import sys
import json
from slither.slither import Slither
from pathlib import Path


def get_inheritance_depth_recursive(contract, visited=None):
    if visited is None:
        visited = set()
    if contract in visited or not contract.inheritance:
        return 0
    visited.add(contract)
    return 1 + max((get_inheritance_depth_recursive(base, visited) for base in contract.inheritance), default=0)


def analyze_contracts_via_summary(sol_file_path):
    slither = Slither(sol_file_path)
    result = []
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

            result.append({
                "contract": name,
                "total_tcc": total_tcc,
                "total_tec": total_tec,
                "inheritance_depth": inheritance_depth,
                "source": Path(sol_file_path).name
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
