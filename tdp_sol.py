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
    decision_patterns = [
        r"\bif\b",
        r"\belse\b",
        r"\bwhile\s*\(",
        r"\bfor\s*\(",
        r"\brequire\s*\(",
        r"\bassert\s*\(",
        r"\brevert\b"
    ]
    total_tdp = sum(1 for line in lines if any(re.search(pattern, line) for pattern in decision_patterns))
    return total_tdp

# Main script execution
if __name__ == "__main__":
    try:
        file_results = {}
        total_tdp = 0

        if len(sys.argv) > 1:
            for file_path in sys.argv[1:]:
                try:
                    with open(file_path, "r") as f:
                        lines = f.readlines()
                    cleaned_lines = remove_comments(lines)
                    tdp = calculate_tdp(cleaned_lines)
                    file_results[file_path] = tdp
                    total_tdp += tdp
                except FileNotFoundError:
                    file_results[file_path] = "Error: File not found"

        else:
            print(json.dumps({"Error": "No input files provided"}))
            exit(1)

        file_results["Total"] = total_tdp
        print(json.dumps(file_results, indent=4))
    
    except Exception as e:
        print(json.dumps({"Error": str(e)}))
        exit(1)
