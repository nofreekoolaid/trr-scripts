# Steps to make input `flat.sol`:
# slither 0x0C9a3dd6b8F28529d72d7f9cE918D493519EE383
# cat $(find crytic-export -name "*sol") > flat.sol
import re

# Load flattened Solidity contract
with open("flat.sol", "r") as f:
    lines = f.readlines()

# Keywords indicating decision points
decision_keywords = ["if", "else", "while", "for", "require", "assert", "revert"]
total_tdp = 0

# Count occurrences of decision-making statements
for line in lines:
    if any(keyword in line for keyword in decision_keywords):
        total_tdp += 1

print("=====================================")
print(f"✅ Total Decision Points (TDP): {total_tdp}")
print("=====================================")
