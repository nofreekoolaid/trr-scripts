from pathlib import Path
import argparse
import json
import os

def merge_code_outputs(contract_dirs):
    merged = {
        "contracts": [],
        "files": [],
        "max_inheritance_depth": 0
    }
    seen_hashes = {}

    for dir_name in contract_dirs:
        dir_path = Path(dir_name.strip().lower()).resolve()
        code_path = dir_path / "code.json"

        if not code_path.is_file():
            print(f"⚠️ Skipping missing: {code_path}")
            continue

        try:
            with open(code_path, "r") as f:
                data = json.load(f)

            merged["max_inheritance_depth"] = max(
                merged["max_inheritance_depth"], data.get("max_inheritance_depth", 0)
            )

            for contract in data.get("contracts", []):
                merged["contracts"].append({
                    "contract": contract["contract"],
                    "total_tcc": contract["total_tcc"],
                    "total_tec": contract["total_tec"],
                    "inheritance_depth": contract["inheritance_depth"],
                    "md5": contract["md5"]
                })

            for fdata in data.get("files", []):
                if fdata["md5"] not in seen_hashes:
                    rel_path = os.path.relpath(fdata["file"], Path.cwd())
                    merged["files"].append({
                        "md5": fdata["md5"],
                        "tdp": fdata["tdp"],
                        "sloc": fdata["sloc"],
                        "root": dir_path.name,
                        "source_path": rel_path,
                        "contract_address": fdata.get("contract_address", "")
                    })
                    seen_hashes[fdata["md5"]] = dir_path.name

        except Exception as e:
            print(f"❌ Error reading/parsing {code_path}: {e}")

    return merged


def aggregate_by_hash(merged):
    aggregated = {}

    for contract in merged["contracts"]:
        file_hash = contract["md5"]
        if file_hash not in aggregated:
            file_entry = next((f for f in merged["files"] if f["md5"] == file_hash), {})
            aggregated[file_hash] = {
                "contracts": [],
                "references": [],
                "totals": {
                    "total_tcc": 0,
                    "total_tec": 0,
                    "tdp": file_entry.get("tdp", 0),
                    "cloc": file_entry.get("sloc", 0),
                    "max_inheritance_depth": 0
                }
            }

        aggregated[file_hash]["contracts"].append({
            "contract": contract["contract"],
            "total_tcc": contract["total_tcc"],
            "total_tec": contract["total_tec"],
            "inheritance_depth": contract["inheritance_depth"]
        })

        file_entry = next((f for f in merged["files"] if f["md5"] == file_hash), {})
        aggregated[file_hash]["references"].append({
            "contract": contract["contract"],
            "contract_address": file_entry.get("contract_address", ""),
            "source_path": file_entry.get("source_path", "")
        })

        aggregated[file_hash]["totals"]["total_tcc"] += contract["total_tcc"]
        aggregated[file_hash]["totals"]["total_tec"] += contract["total_tec"]
        aggregated[file_hash]["totals"]["max_inheritance_depth"] = max(
            aggregated[file_hash]["totals"]["max_inheritance_depth"],
            contract["inheritance_depth"]
        )

    return aggregated


def output_tsv(merged):
    print("contract\tinheritance_depth\ttcc\ttec\tsource_path\tmd5\ttdp\tsloc")
    for contract in merged["contracts"]:
        file_entry = next((f for f in merged["files"] if f["md5"] == contract["md5"]), {})
        row = [
            contract.get("contract", ""),
            contract.get("inheritance_depth", ""),
            contract.get("total_tcc", ""),
            contract.get("total_tec", ""),
            file_entry.get("source_path", ""),
            contract.get("md5", ""),
            file_entry.get("tdp", ""),
            file_entry.get("sloc", "")
        ]
        print("\t".join(map(str, row)))

    print(f"\n# Max Inheritance Depth: {merged['max_inheritance_depth']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge and summarize contract code.json files.")
    parser.add_argument("input", help="Text file with list of contract addresses")
    parser.add_argument("--tsv", action="store_true", help="Output summary as TSV instead of JSON")
    args = parser.parse_args()

    with open(args.input, "r") as f:
        addresses = [line.strip() for line in f if line.strip()]

    merged_summary = merge_code_outputs(addresses)
    aggregated = aggregate_by_hash(merged_summary)

    if args.tsv:
        output_tsv(merged_summary)
    else:
        print(json.dumps(aggregated, indent=2))
