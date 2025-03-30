import os
import sys
import json
from stats import process_function_summary

def merge_summaries(existing_summary, new_summary):
    for file_hash, new_data in new_summary["inputs"].items():
        if file_hash in existing_summary["inputs"]:
            existing_summary["inputs"][file_hash]["references"].extend(new_data["references"])
        else:
            existing_summary["inputs"][file_hash] = new_data
    return existing_summary

def process_and_merge_summaries(hashes_file, summary_files):
    merged_summary = {"inputs": {}}
    for summary_file in summary_files:
        print(f"Processing: {summary_file}", file=sys.stderr)
        try:
            result = process_function_summary(hashes_file, summary_file)
            merged_summary = merge_summaries(merged_summary, result)
        except Exception as e:
            print(f"Error processing {summary_file}: {e}", file=sys.stderr)
    return merged_summary

def calculate_totals(merged_summary):
    tec = sum(item["ec"] for item in merged_summary["inputs"].values())
    tcc = sum(item["cc"] for item in merged_summary["inputs"].values())
    tloc = sum(item.get("loc", 0) for item in merged_summary["inputs"].values())
    ttdp = sum(item.get("tdp", 0) for item in merged_summary["inputs"].values())
    merged_summary["tec"] = tec
    merged_summary["tcc"] = tcc
    merged_summary["tloc"] = tloc
    merged_summary["ttdp"] = ttdp
    return merged_summary

def output_tsv(merged_summary):
    all_paths = []
    for entry in merged_summary["inputs"].values():
        all_paths.extend([ref["filepath"] for ref in entry.get("references", [])])

    common_prefix = os.path.commonpath(all_paths) if all_paths else ""

    print("contract_names\ttdp\tec\tcc\tloc\thash\tpaths")
    total_tdp = total_ec = total_cc = total_loc = 0

    for file_hash, entry in merged_summary["inputs"].items():
        stats = {
            "tdp": entry.get("tdp", 0),
            "ec": entry.get("ec", 0),
            "cc": entry.get("cc", 0),
            "loc": entry.get("loc", 0),
        }

        contract_names = ",".join(sorted(set(ref["contract_name"] for ref in entry.get("references", []))))
        rel_paths = [
            os.path.relpath(ref["filepath"], common_prefix)
            for ref in entry.get("references", [])
        ]
        path_str = ",".join(rel_paths)

        print(f"{contract_names}\t{stats['tdp']}\t{stats['ec']}\t{stats['cc']}\t{stats['loc']}\t{file_hash}\t{path_str}")

        total_tdp += stats["tdp"]
        total_ec += stats["ec"]
        total_cc += stats["cc"]
        total_loc += stats["loc"]

    print(f"TOTAL\t{total_tdp}\t{total_ec}\t{total_cc}\t{total_loc}\t\t")

# --- CLI entry point ---
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python unique_stats.py <hashes.json> <function-summary1.txt> [...] [--tsv]", file=sys.stderr)
        sys.exit(1)

    # Optional TSV flag
    is_tsv = "--tsv" in sys.argv
    if is_tsv:
        sys.argv.remove("--tsv")

    hashes_file = sys.argv[1]
    summary_files = sys.argv[2:]

    merged_summary = process_and_merge_summaries(hashes_file, summary_files)
    merged_summary = calculate_totals(merged_summary)

    if is_tsv:
        output_tsv(merged_summary)
    else:
        print(json.dumps(merged_summary, indent=2))
