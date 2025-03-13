import sys
import json
import hashlib
import re

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

# Function to extract contract, library, interface, or struct name
def extract_name(lines):
    names = {"contract": [], "library": [], "interface": [], "struct": []}
    for line in lines:
        line = line.strip()  # Normalize line
        match = re.match(r"^(abstract\s+)?(contract|library|interface|struct)\s+(\w+)", line)
        if match:
            names[match.group(2)].append(match.group(3))
    return names

# Function to determine the primary name priority-wise
def determine_primary_name(names):
    for key in ["contract", "library", "interface", "struct"]:
        if names[key]:
            return names[key][0]  # Take the first occurrence
    return "Unknown"

# Dictionary to store hash mappings
hash_map = {}

# Process each Solidity file passed via command-line arguments
for filepath in sys.argv[1:]:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        cleaned_lines = remove_comments(lines)
        cleaned_content = "\n".join(cleaned_lines)
        
        # Compute MD5 hash
        file_hash = hashlib.md5(cleaned_content.encode("utf-8")).hexdigest()
        
        # Extract contract, library, interface, or struct names
        names = extract_name(cleaned_lines)
        primary_name = determine_primary_name(names)
        
        # Store in hash map
        if file_hash not in hash_map:
            hash_map[file_hash] = []
        
        hash_map[file_hash].append({"filepath": filepath, "names": names, "name": primary_name})
    except Exception as e:
        print(f"Error processing {filepath}: {e}", file=sys.stderr)

# Output JSON to stdout
print(json.dumps(hash_map, indent=2))
