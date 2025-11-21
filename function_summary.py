import json
import re
import sys


# Function to parse Slither function summary output
def parse_function_summary(data):
    headers = []
    total_tcc = 0  # Total Cyclomatic Complexity
    total_tec = 0  # Total External Calls
    row_pattern = re.compile(r"^\|(.+)\|$")

    for line in data.split("\n"):
        if "Function" in line and "Cyclomatic Complexity" in line:
            headers = [h.strip() for h in line.split("|")[1:-1]]
            continue

        match = row_pattern.match(line)
        if match:
            row_values = [v.strip() for v in match.group(1).split("|")]
            if len(row_values) == len(headers):
                func_data = dict(zip(headers, row_values))

                try:
                    tcc = int(func_data.get("Cyclomatic Complexity", "0"))
                except ValueError:
                    tcc = 0

                try:
                    external_calls = func_data.get("External Calls", "[]")
                    tec = (
                        len(eval(external_calls))
                        if external_calls and external_calls != "[]"
                        else 0
                    )
                except Exception:
                    tec = 0

                total_tcc += tcc
                total_tec += tec

    return {"TCC": total_tcc, "TEC": total_tec}


# Run only if executed as a script (not when imported)
if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            with open(sys.argv[1]) as f:
                data = f.read()
        else:
            data = sys.stdin.read()

        result = parse_function_summary(data)
        print(json.dumps(result))

    except Exception as e:
        print(json.dumps({"Error": str(e)}))
        exit(1)
