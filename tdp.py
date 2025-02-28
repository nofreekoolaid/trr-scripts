# Steps to make input `flat.sol`:
# slither 0x0C9a3dd6b8F28529d72d7f9cE918D493519EE383
# cat $(find crytic-export -name "*sol") > flat.sol
import re

# Load flattened Solidity contract
with open("flat.sol", "r") as f:
    lines = f.readlines()

# Function to remove comments
def remove_comments(lines):
    cleaned_lines = []
    block_comment = False

    for line in lines:
        # Detect the start and end of block comments
        if "/*" in line:
            block_comment = True
        if "*/" in line:
            block_comment = False
            continue  # Skip this line as it closes a comment

        if block_comment:
            continue  # Ignore lines inside block comments

        # Remove single-line comments (//...)
        line = re.sub(r"//.*", "", line).strip()

        if line:  # Avoid adding empty lines
            cleaned_lines.append(line)

    return cleaned_lines
    
# Clean comments and save the new file
cleaned_lines = remove_comments(lines)
    
# Keywords indicating decision points
decision_patterns = [r"\bif\b", r"\belse\b", r"\bwhile\s*\(", r"\bfor\s*\(",r"\brequire\s*\(", r"\bassert\s*\(", r"\brevert\b"]
total_tdp = 0

# Count occurrences of decision-making statements
for line in cleaned_lines:
    if any(re.search(pattern, line) for pattern in decision_patterns):
        total_tdp += 1

print("=====================================")
print(f"✅ Total Decision Points (TDP): {total_tdp}")
print("=====================================")
