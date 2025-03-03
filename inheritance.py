import json
import argparse

# Set up argument parsing
parser = argparse.ArgumentParser(description="Parse Slither inheritance JSON output and compute inheritance depth.")
parser.add_argument("filename", type=str, help="Path to the inheritance.json file")
args = parser.parse_args()

# Load JSON output
try:
    with open(args.filename, "r") as f:
        data = json.load(f)
except FileNotFoundError:
    print(f"❌ Error: File '{args.filename}' not found.")
    exit(1)
except json.JSONDecodeError:
    print(f"❌ Error: File '{args.filename}' is not a valid JSON file.")
    exit(1)

# Extract inheritance data
try:
    inheritance_map = data["results"]["printers"][0]["additional_fields"]["child_to_base"]
except KeyError:
    print(f"❌ Error: The file '{args.filename}' does not contain valid inheritance data.")
    exit(1)

def get_depth(contract, depth_map):
    """Recursively calculates inheritance depth."""
    if contract not in inheritance_map or not inheritance_map[contract]["immediate"]:
        return 0
    return 1 + max(get_depth(parent, depth_map) for parent in inheritance_map[contract]["immediate"])

# Compute depth for each contract
depths = {contract: get_depth(contract, {}) for contract in inheritance_map}
max_depth = max(depths.values(), default=0)

# Print per-contract depth and overall max
for contract, depth in depths.items():
    print(f"Contract: {contract}, Inheritance Depth: {depth}")

print("\n=====================================")
print(f"✅ Maximum Inheritance Depth: {max_depth}")
print("=====================================")
