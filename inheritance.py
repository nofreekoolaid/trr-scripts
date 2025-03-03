import sys
import json

# Function to calculate inheritance depth
def calculate_inheritance_depth(data):
    if "results" not in data or "printers" not in data["results"]:
        return {"Max Inheritance Depth": "Error: Invalid JSON format"}

    inheritance_map = data["results"]["printers"][0]["additional_fields"].get("child_to_base", {})

    def get_depth(contract):
        if contract not in inheritance_map or not inheritance_map[contract]["immediate"]:
            return 0
        return 1 + max(get_depth(parent) for parent in inheritance_map[contract]["immediate"])

    depths = {contract: get_depth(contract) for contract in inheritance_map}
    max_depth = max(depths.values(), default=0)

    return {"Max Inheritance Depth": max_depth}

# Run only if executed as a script (not when imported)
if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            with open(sys.argv[1], "r") as f:
                data = json.load(f)
        else:
            data = json.load(sys.stdin)

        result = calculate_inheritance_depth(data)
        print(json.dumps(result))

    except json.JSONDecodeError:
        print(json.dumps({"Max Inheritance Depth": "Error: Invalid or empty JSON"}))
        exit(1)
    except Exception as e:
        print(json.dumps({"Max Inheritance Depth": f"Error: {e}"}))
        exit(1)
