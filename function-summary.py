# Steps to make input `function-summary.txt`
# slither 0x0C9a3dd6b8F28529d72d7f9cE918D493519EE383 --print function-summary &> function-summary.txt
import re

# Read Slither output file
with open("function-summary.txt", "r") as f:
    lines = f.readlines()

headers = []
functions = []
total_tcc = 0  # Total Cyclomatic Complexity
total_tec = 0  # Total External Calls

# Regex to match table rows
row_pattern = re.compile(r"^\|(.+)\|$")

# Extract header row
for line in lines:
    if "Function" in line and "Cyclomatic Complexity" in line:
        headers = [h.strip() for h in line.split("|")[1:-1]]
        continue

    # Extract table data
    match = row_pattern.match(line)
    if match:
        row_values = [v.strip() for v in match.group(1).split("|")]

        if len(row_values) == len(headers):  # Ensure row matches header count
            func_data = dict(zip(headers, row_values))

            # Extract Cyclomatic Complexity (TCC)
            try:
                tcc = int(func_data.get("Cyclomatic Complexity", "0"))
            except ValueError:
                tcc = 0

            # Extract Total External Calls (TEC)
            try:
                external_calls = func_data.get("External Calls", "[]")
                if external_calls and external_calls != "[]":
                    tec = len(eval(external_calls))  # Convert string list to actual list and count
                else:
                    tec = 0
            except:
                tec = 0  # Fallback if parsing fails

            # Print function-level details
            print(f"Function: {func_data['Function']}")
            print(f"  - Cyclomatic Complexity (TCC): {tcc}")
            print(f"  - External Calls (TEC): {tec}\n")

            # Sum totals
            total_tcc += tcc
            total_tec += tec

# Print total results
print("=====================================")
print(f"✅ Total Cyclomatic Complexity (TCC): {total_tcc}")
print(f"✅ Total External Calls (TEC): {total_tec}")
print("=====================================")
