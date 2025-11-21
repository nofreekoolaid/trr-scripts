import hashlib
import json
import re
import sys


# Function to remove comments based on file type
def remove_comments(lines, file_type):
    cleaned_lines = []
    block_comment = False

    for line in lines:
        if file_type == "sol":
            if "/*" in line:
                block_comment = True
            if "*/" in line:
                block_comment = False
                continue  # Skip closing block comment

            if block_comment:
                continue

            line = re.sub(r"//.*", "", line).strip()

        elif file_type == "vy":
            stripped_line = line.strip()
            if '"""' in stripped_line or "'''" in stripped_line:
                block_comment = not block_comment
                continue

            if block_comment:
                continue

            line = re.sub(r"#.*", "", line).strip()

        if line:
            cleaned_lines.append(line)

    return cleaned_lines


# Function to calculate Total Decision Points (TDP) based on file type
def calculate_tdp(lines, file_type):
    if file_type == "sol":
        decision_patterns = [
            r"\bif\b",
            r"\belse\b",
            r"\bwhile\s*\(",
            r"\bfor\s*\(",
            r"\brequire\s*\(",
            r"\bassert\s*\(",
            r"\brevert\b",
        ]
    else:  # Vyper
        decision_patterns = [
            r"\bif\b",
            r"\belif\b",
            r"\bwhile\b",
            r"\bfor\b",
            r"\bassert\b",
            r"\braise\b",
        ]

    total_tdp = sum(
        1 for line in lines if any(re.search(pattern, line) for pattern in decision_patterns)
    )
    return total_tdp


# Exposed function to compute TDP from a file path
def compute_tdp_from_file(filepath):
    try:
        with open(filepath) as f:
            lines = f.read().splitlines()

        file_type = (
            "sol" if filepath.endswith(".sol") else "vy" if filepath.endswith(".vy") else None
        )
        if not file_type:
            raise ValueError(f"Unsupported file type for {filepath}")

        cleaned_lines = remove_comments(lines, file_type)
        return calculate_tdp(cleaned_lines, file_type)

    except Exception as e:
        print(f"⚠️ Error computing TDP for {filepath}: {e}", file=sys.stderr)
        return 0


# Main script execution (for CLI use)
if __name__ == "__main__":
    try:
        file_results = {}
        total_tdp_unique = 0
        total_tdp_all = 0
        seen_hashes = {}

        if len(sys.argv) > 1:
            for file_path in sys.argv[1:]:
                try:
                    with open(file_path) as f:
                        lines = f.read().splitlines()

                    file_type = (
                        "sol"
                        if file_path.endswith(".sol")
                        else "vy"
                        if file_path.endswith(".vy")
                        else None
                    )
                    if not file_type:
                        file_results[file_path] = "Error: Unsupported file type"
                        continue

                    cleaned_lines = remove_comments(lines, file_type)
                    file_hash = hashlib.md5("\n".join(cleaned_lines).encode()).hexdigest()
                    tdp = calculate_tdp(cleaned_lines, file_type)
                    file_results[file_path] = tdp
                    total_tdp_all += tdp

                    if file_hash not in seen_hashes:
                        seen_hashes[file_hash] = tdp
                        total_tdp_unique += tdp
                except FileNotFoundError:
                    file_results[file_path] = "Error: File not found"

        else:
            print(json.dumps({"Error": "No input files provided"}))
            exit(1)

        file_results["Total (Unique)"] = total_tdp_unique
        file_results["Total (All)"] = total_tdp_all
        print(json.dumps(file_results, indent=4))

    except Exception as e:
        print(json.dumps({"Error": str(e)}))
        exit(1)
