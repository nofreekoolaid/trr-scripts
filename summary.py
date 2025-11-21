import argparse
import json
import os
from pathlib import Path


def merge_code_outputs(contract_dirs):
    merged = {"contracts": [], "files": [], "max_inheritance_depth": 0}
    seen_contracts = set()
    seen_files = set()

    for dir_name in contract_dirs:
        dir_path = Path(dir_name.strip().lower()).resolve()
        code_path = dir_path / "code.json"

        if not code_path.is_file():
            print(f"⚠️ Skipping missing: {code_path}")
            continue

        try:
            with open(code_path) as f:
                data = json.load(f)

            merged["max_inheritance_depth"] = max(
                merged["max_inheritance_depth"], data.get("max_inheritance_depth", 0)
            )

            for contract in data.get("contracts", []):
                contract_id = (contract["contract"], contract["md5"])
                if contract_id not in seen_contracts:
                    merged["contracts"].append(
                        {
                            "contract": contract["contract"],
                            "total_tcc": contract["total_tcc"],
                            "total_tec": contract["total_tec"],
                            "inheritance_depth": contract["inheritance_depth"],
                            "md5": contract["md5"],
                        }
                    )
                    seen_contracts.add(contract_id)

            for fdata in data.get("files", []):
                key = (fdata["md5"], dir_path.name)
                rel_path = os.path.relpath(fdata["file"], Path.cwd())
                if key not in seen_files:
                    merged["files"].append(
                        {
                            "md5": fdata["md5"],
                            "tdp": fdata["tdp"],
                            "sloc": fdata["sloc"],
                            "source_path": rel_path,
                            "contract_address": dir_path.name,
                        }
                    )
                    seen_files.add(key)

        except Exception as e:
            print(f"❌ Error reading/parsing {code_path}: {e}")

    return merged


def aggregate_by_hash(merged, contract_dirs=None):
    aggregated = {}

    # If contract_dirs not provided, extract from merged files
    if contract_dirs is None:
        contract_dirs = list({f.get("contract_address", "") for f in merged.get("files", [])})

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
                    "max_inheritance_depth": 0,
                },
            }

        aggregated[file_hash]["contracts"].append(
            {
                "contract": contract["contract"],
                "total_tcc": contract["total_tcc"],
                "total_tec": contract["total_tec"],
                "inheritance_depth": contract["inheritance_depth"],
            }
        )

        matching_files = [
            f
            for f in merged["files"]
            if f["md5"] == file_hash
            and f["contract_address"].lower() in [d.lower() for d in contract_dirs]
        ]

        for file_entry in matching_files:
            ref = {
                "contract": contract["contract"],
                "contract_address": file_entry.get("contract_address", ""),
                "source_path": file_entry.get("source_path", ""),
            }
            if ref not in aggregated[file_hash]["references"]:
                aggregated[file_hash]["references"].append(ref)

        aggregated[file_hash]["totals"]["total_tcc"] += contract["total_tcc"]
        aggregated[file_hash]["totals"]["total_tec"] += contract["total_tec"]
        aggregated[file_hash]["totals"]["max_inheritance_depth"] = max(
            aggregated[file_hash]["totals"]["max_inheritance_depth"], contract["inheritance_depth"]
        )

    return aggregated


def output_tsv_from_aggregated(aggregated):
    print("Contract Names\tTCC\tTEC\tTDP\tCLOC\tMax ID\tFile Hash\tContract Addresses")
    for file_hash, entry in aggregated.items():
        contract_names = ",".join(sorted({c["contract"] for c in entry["contracts"]}))
        contract_addresses = ",".join(sorted({r["contract_address"] for r in entry["references"]}))
        totals = entry["totals"]
        row = [
            contract_names,
            totals["total_tcc"],
            totals["total_tec"],
            totals["tdp"],
            totals["cloc"],
            totals["max_inheritance_depth"],
            file_hash,
            contract_addresses,
        ]
        print("\t".join(map(str, row)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge and summarize contract code.json files.")
    parser.add_argument("input", help="Text file with list of contract addresses")
    parser.add_argument("--tsv", action="store_true", help="Output summary as TSV instead of JSON")
    args = parser.parse_args()

    with open(args.input) as f:
        contract_dirs = [line.strip() for line in f if line.strip()]

    merged_summary = merge_code_outputs(contract_dirs)
    aggregated = aggregate_by_hash(merged_summary, contract_dirs)

    if args.tsv:
        output_tsv_from_aggregated(aggregated)
    else:
        print(json.dumps(aggregated, indent=2))
