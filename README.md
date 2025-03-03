## **🔍 Smart Contract Analysis Scripts**
This repository contains **Python scripts** that extract key **complexity and risk metrics** from Solidity and Vyper smart contracts using [Slither](https://github.com/crytic/slither).

### **📌 Overview**
These scripts analyze **Ethereum smart contracts** to compute:
1. **Cyclomatic Complexity (TCC)** and **External Calls (TEC)** from the `function-summary` printer.
2. **Maximum Inheritance Depth (ID)** from the `inheritance` printer.
3. **Total Decision Points (TDP)** by scanning Solidity or Vyper source code.

---

## **📝 Scripts**
| Script | Description |
|--------|------------|
| [`analyze_contract.py`](#-analyze_contractpy) | **Runs all analyses in one command** for Solidity or Vyper contracts. |
| [`function-summary.py`](#-function-summarypy) | Extracts **Cyclomatic Complexity (TCC)** and **Total External Calls (TEC)** per function. |
| [`inheritance.py`](#-inheritancepy) | Computes the **maximum inheritance depth** from Slither’s inheritance graph. |
| [`tdp.py`](#-tdppy) | Scans **Solidity** source code to count **Total Decision Points (TDP)** (e.g., `if`, `require()`, `for`, `while`). |
| [`tdp_vy.py`](#-tdp_vypy) | Scans **Vyper** source code to count **Total Decision Points (TDP)** (e.g., `if`, `assert`, `raise`). |

---

## **📖 Setup Guide**
### **1️⃣ Install Dependencies**
First, set up a **Python virtual environment (`venv`)** to isolate dependencies:
```sh
# Create a virtual environment
python3 -m venv venv

# Activate venv (Linux/macOS)
source venv/bin/activate
```

Now, install **Slither**, Solidity compiler (`solc`), and required dependencies inside the virtual environment:
```sh
pip install slither-analyzer jq
```

### **2️⃣ Install & Select `solc` Version**
To ensure compatibility with different Solidity versions, install `solc-select`:
```sh
pip install solc-select
solc-select install 0.8.20  # Install the required version
solc-select use 0.8.20      # Use the selected version
```
To verify the installed version:
```sh
solc --version
```

---

## **🚀 Running the Analysis**
### **💡 One-Command Analysis**
The **`analyze_contract.py`** script automates all analysis steps for both Solidity and Vyper contracts.

```sh
python analyze_contract.py flat.sol  # Solidity
python analyze_contract.py flat.vy   # Vyper
```
**✅ Expected Output Example:**
```json
{
  "LOC": "2285",
  "sLOC": 1092,
  "TDP": 218,
  "TCC": 10,
  "TEC": 5,
  "Max Inheritance Depth": 3
}
```

---

### **💡 Function Complexity & External Calls**
Extracts:
- **Cyclomatic Complexity (TCC)**: Measures function complexity.
- **Total External Calls (TEC)**: Count of external contract interactions.

#### **💡 Generate Input:**
```sh
slither 0xCONTRACT_ADDRESS --print function-summary --disable-color > function-summary.txt
```
#### **💡 Run Analysis:**
```sh
python function-summary.py function-summary.txt
```

---

### **💡 Inheritance Depth**
Extracts:
- **Maximum Inheritance Depth (ID)**: Measures contract hierarchy complexity.

#### **💡 Generate Input:**
```sh
slither 0xCONTRACT_ADDRESS --print inheritance --json - | jq '.' > inheritance.json
```
#### **💡 Run Analysis:**
```sh
python inheritance.py inheritance.json
```

---

### **💡 Total Decision Points (Solidity)**
Extracts:
- **TDP (Total Decision Points)**: Counts control flow structures (`if`, `while`, `for`, `require()`, `assert()`, `revert()`).

#### **💡 Generate Input:**
```sh
slither 0xCONTRACT_ADDRESS
cat $(find crytic-export -name "*sol") > flat.sol
```
#### **💡 Run Analysis:**
```sh
python tdp.py flat.sol
```

---

### **💡 Total Decision Points (Vyper)**
Extracts:
- **TDP (Total Decision Points)**: Counts control flow structures (`if`, `while`, `for`, `assert`, `raise`).

#### **💡 Generate Input:**
```sh
vyper -f combined_json contract.vy > flat.vy
```
#### **💡 Run Analysis:**
```sh
python tdp_vy.py flat.vy
```

---

## **🎯 Summary**
| Metric | Script | Slither Printer |
|--------|--------|----------------|
| **Cyclomatic Complexity (TCC)** | `function-summary.py` | `function-summary` |
| **Total External Calls (TEC)** | `function-summary.py` | `function-summary` |
| **Inheritance Depth (ID)** | `inheritance.py` | `inheritance` |
| **Total Decision Points (TDP) - Solidity** | `tdp.py` | _(Custom Solidity parsing)_ |
| **Total Decision Points (TDP) - Vyper** | `tdp_vy.py` | _(Custom Vyper parsing)_ |

---

## **🗓 Notes**
- These scripts **do not modify source files**—they only analyze complexity.
- **Slither must be installed inside the virtual environment (`venv`)**.
- **Flattened source code** is required for `tdp.py` and `tdp_vy.py`.
- Ensure the correct compiler version is selected using `solc-select` or `vyper`.

🚀 **Use these scripts to quickly assess smart contract complexity risks!** 🚀

