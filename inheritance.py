# Steps to make input `inheritance.json`:
# slither 0x0C9a3dd6b8F28529d72d7f9cE918D493519EE383 --print inheritance --json - | jq '.' > inheritance.json
import json

# Load JSON output
with open("inheritance.json", "r") as f:
    data = json.load(f)

inheritance_map = data["results"]["printers"][0]["additional_fields"]["child_to_base"]

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
