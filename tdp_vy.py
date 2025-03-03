import re
import sys
import json

# Function to remove comments and docstrings from Vyper code
def remove_comments(lines):
    cleaned_lines = []
    block_comment = False

    for line in lines:
        stripped_line = line.strip()

        # Detect the start and end of docstrings (triple quotes)
        if '"""' in stripped_line or "'''" in stripped_line:
            block_comment = not block_comment
            continue  # Skip docstring lines

        if block_comment:
            continue  # Ignore lines inside docstrings

        # Remove single-line comments (#...)
        line = re.sub(r"#.*", "", line).strip()

        if line:  # Avoid adding empty lines
            cleaned_lines.append(line)

    return cleaned_lines

# Function to calculate Total Decision Points (TDP)
def calculate_tdp_vy(lines):
    decision_patterns = [
        r"\bif\b",
        r"\belif\b",
        r"\bwhile\b",
        r"\bfor\b",
        r"\bassert\b",
        r"\braise\b"
    ]
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
        tdp_result = {"TDP": calculate_tdp_vy(cleaned_lines)}
        print(json.dumps(tdp_result))

    except FileNotFoundError:
        print(json.dumps({"Error": "File not found"}))
        exit(1)
