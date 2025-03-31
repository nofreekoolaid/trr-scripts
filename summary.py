from pathlib import Path
import argparse
import json


def merge_code_outputs(contract_dirs):
    merged = {
        "contracts": [],
        "files": [],
        "max_inheritance_depth": 0
    }
    seen_hashes = set()

    for dir_name in contract_dirs:
        dir_path = Path(dir_name.lower()).resolve()
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

            merged["contracts"].extend(data.get("contracts", []))

            for fdata in data.get("files", []):
                if fdata["md5"] not in seen_hashes:
                    merged["files"].append(fdata)
                    seen_hashes.add(fdata["md5"])

        except Exception as e:
            print(f"❌ Error reading/parsing {code_path}: {e}")

    return merged


def output_tsv(merged):
    print("contract\tinheritance_depth\ttcc\ttec\tsource_path\tmd5\ttdp\tsloc")
    for contract in merged["contracts"]:
        file_entry = next((f for f in merged["files"] if f["md5"] == contract["md5"]), {})
        row = [
            contract.get("contract", ""),
            contract.get("inheritance_depth", ""),
            contract.get("total_tcc", ""),
            contract.get("total_tec", ""),
            contract.get("source_path", ""),
            contract.get("md5", ""),
            file_entry.get("tdp", ""),
            file_entry.get("sloc", "")
        ]
        print("\t".join(map(str, row)))

    print(f"\n# Max Inheritance Depth: {merged['max_inheritance_depth']}")


def aggregate_by_hash(merged):
    hash_map = {}

    for f in merged["files"]:
        file_hash = f["md5"]
        hash_map[file_hash] = {
            "contracts": [],
            "references": []
        }

    for c in merged["contracts"]:
        file_hash = c["md5"]
        if file_hash not in hash_map:
            continue
        hash_map[file_hash]["contracts"].append({
            "contract": c["contract"],
            "inheritance_depth": c["inheritance_depth"],
            "total_tcc": c["total_tcc"],
            "total_tec": c["total_tec"]
        })
        hash_map[file_hash]["references"].append({
            "contract": c["contract"],
            "source_path": c["source_path"]
        })

    return hash_map


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge and summarize contract code.json files.")
    parser.add_argument("input", help="Text file with list of contract addresses")
    parser.add_argument("--tsv", action="store_true", help="Output summary as TSV as well")
    args = parser.parse_args()

    with open(args.input, "r") as f:
        addresses = [line.strip() for line in f if line.strip()]

    merged_summary = merge_code_outputs(addresses)

    if args.tsv:
        output_tsv(merged_summary)

    aggregated = aggregate_by_hash(merged_summary)
    print(json.dumps(aggregated, indent=2))
