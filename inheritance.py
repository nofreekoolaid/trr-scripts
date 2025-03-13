import sys
import json

# python3 inheritance.py $(find . -name "inheritance.json")  > inhiertance.json

def calculate_inheritance_depth(data):
    """Calculates the maximum inheritance depth from the Slither inheritance.json output."""
    if "results" not in data or "printers" not in data["results"]:
        return None  # Indicate an invalid JSON format
    
    inheritance_map = data["results"]["printers"][0]["additional_fields"].get("child_to_base", {})

    def get_depth(contract):
        if contract not in inheritance_map or not inheritance_map[contract]["immediate"]:
            return 0
        return 1 + max(get_depth(parent) for parent in inheritance_map[contract]["immediate"])

    depths = {contract: get_depth(contract) for contract in inheritance_map}
    return max(depths.values(), default=0)


def process_files(file_paths):
    """Processes multiple inheritance.json files and computes max inheritance depth for each and overall."""
    results = []
    overall_max = 0
    overall_max_file = None

    for file_path in file_paths:
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
            
            max_depth = calculate_inheritance_depth(data)
            if max_depth is not None:
                results.append({"file": file_path, "Max Inheritance Depth": max_depth})
                if max_depth > overall_max:
                    overall_max = max_depth
                    overall_max_file = file_path
            else:
                results.append({"file": file_path, "Max Inheritance Depth": "Error: Invalid JSON format"})

        except json.JSONDecodeError:
            results.append({"file": file_path, "Max Inheritance Depth": "Error: Invalid or empty JSON"})
        except Exception as e:
            results.append({"file": file_path, "Max Inheritance Depth": f"Error: {e}"})

    return results, overall_max, overall_max_file


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"Error": "Usage: script.py <inheritance1.json> <inheritance2.json> ..."}))
        sys.exit(1)
    
    file_paths = sys.argv[1:]
    results, overall_max, overall_max_file = process_files(file_paths)
    
    # Output individual file results
    print(json.dumps(results, indent=2))
    
    # Output overall max depth
    print(json.dumps({"Overall Max Inheritance Depth": overall_max, "File": overall_max_file}, indent=2))
