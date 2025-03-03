import re
import sys
import json

# Function to remove comments
def remove_comments(lines):
    cleaned_lines = []
    block_comment = False

    for line in lines:
        if "/*" in line:
            block_comment = True
        if "*/" in line:
            block_comment = False
            continue  # Skip closing block comment

        if block_comment:
            continue  # Ignore lines inside block comments

        # Remove single-line comments
        line = re.sub(r"//.*", "", line).strip()

        if line:
            cleaned_lines.append(line)

    return cleaned_lines

# Function to calculate Total Decision Points (TDP)
def calculate_tdp(lines):
    decision_patterns = [r"\bif\b", r"\belse\b", r"\bwhile\s*\(", r"\bfor\s*\(", r"\brequire\s*\(", r"\bassert\s*\(", r"\brevert\b"]
    total_tdp = sum(1 for line in lines if any(re.search(pattern, line) for pattern in decision_patterns))
    return total_tdp

# Run only if executed as a script (not when imported)
if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            with open(sys.argv[1], "r") as f:
                lines = f.readlines()
        else:
            lines = sys.stdin.readlines()

        cleaned_lines = remove_comments(lines)
        tdp_result = {"TDP": calculate_tdp(cleaned_lines)}
        print(json.dumps(tdp_result))

    except FileNotFoundError:
        print(json.dumps({"Error": "File not found"}))
        exit(1)
