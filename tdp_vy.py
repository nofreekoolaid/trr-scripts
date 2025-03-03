import re

# Load flattened Vyper contract
with open("flat.vy", "r") as f:
    lines = f.readlines()

# Function to remove comments and docstrings
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
    
# Clean comments and save the new file
cleaned_lines = remove_comments(lines)
    
# Keywords indicating decision points
decision_patterns = [
    r"\bif\b", 
    r"\belif\b", 
    r"\bwhile\b", 
    r"\bfor\b", 
    r"\bassert\b", 
    r"\braise\b"
]
total_tdp = 0

# Count occurrences of decision-making statements
for line in cleaned_lines:
    if any(re.search(pattern, line) for pattern in decision_patterns):
        total_tdp += 1

print("=====================================")
print(f"✅ Total Decision Points (TDP): {total_tdp}")
print("=====================================")
