## **🔍 Slither Analysis Scripts**
This repository contains **Python scripts** that extract key **complexity and risk metrics** from Solidity smart contracts using [Slither](https://github.com/crytic/slither).

### **📌 Overview**
These scripts analyze **Ethereum smart contracts** to compute:
1. **Cyclomatic Complexity (TCC)** and **External Calls (TEC)** from the `function-summary` printer.
2. **Maximum Inheritance Depth (ID)** from the `inheritance` printer.
3. **Total Decision Points (TDP)** by scanning the Solidity source code.

---

## **📜  Scripts**
| Script | Description |
|--------|------------|
| [`function-summary.py`](#-function-summarypy) | Extracts **Cyclomatic Complexity (TCC)** and **Total External Calls (TEC)** per function. |
| [`inheritance.py`](#-inheritancepy) | Computes the **maximum inheritance depth** from Slither’s inheritance graph. |
| [`tdp.py`](#-tdppy) | Scans Solidity source code to count **Total Decision Points (TDP)** (e.g., `if`, `require()`, `for`, `while`). |

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

### **3️⃣ Running the Scripts**
Each script requires an input file generated from **Slither**.

### **🔹 Function Complexity & External Calls**
Extracts:
- **Cyclomatic Complexity (TCC)**: Measures function complexity.
- **Total External Calls (TEC)**: Count of external contract interactions.

#### **🔹 Generate Input:**
```sh
slither 0xCONTRACT_ADDRESS --print function-summary &> function-summary.txt
```
#### **🔹 Run Analysis:**
```sh
python function-summary.py
```

**✅ Expected Output Example:**
```
Function: transfer(address,uint256)
  - Cyclomatic Complexity (TCC): 4
  - External Calls (TEC): 1

=====================================
✅ Total Cyclomatic Complexity (TCC): 92
✅ Total External Calls (TEC): 15
=====================================
```

---

### **🔹 Inheritance Depth**
Extracts:
- **Maximum Inheritance Depth (ID)**: Measures contract hierarchy complexity.

#### **🔹 Generate Input:**
```sh
slither 0xCONTRACT_ADDRESS --print inheritance --json - | jq '.' > inheritance.json
```
#### **🔹 Run Analysis:**
```sh
python inheritance.py
```

**✅ Expected Output Example:**
```
Contract: Token, Inheritance Depth: 2
Contract: Governance, Inheritance Depth: 3

=====================================
✅ Maximum Inheritance Depth: 3
=====================================
```

---

### **🔹 Total Decision Points**
Extracts:
- **TDP (Total Decision Points)**: Counts control flow structures (`if`, `while`, `for`, `require()`, `assert()`, `revert()`).

#### **🔹 Generate Input:**
```sh
slither 0xCONTRACT_ADDRESS
cat $(find crytic-export -name "*sol") > flat.sol
```
#### **🔹 Run Analysis:**
```sh
python tdp.py
```

**✅ Expected Output Example:**
```
=====================================
✅ Total Decision Points (TDP): 120
=====================================
```

---

## **🎯 Summary**
| Metric | Script | Slither Printer |
|--------|--------|----------------|
| **Cyclomatic Complexity (TCC)** | `function-summary.py` | `function-summary` |
| **Total External Calls (TEC)** | `function-summary.py` | `function-summary` |
| **Inheritance Depth (ID)** | `inheritance.py` | `inheritance` |
| **Total Decision Points (TDP)** | `tdp.py` | _(Custom Solidity parsing)_ |

---

## **📅 Notes**
- These scripts **do not modify Solidity files**—they only analyze complexity.
- **Slither must be installed inside the virtual environment (`venv`)**.
- **Flattened Solidity code** is required for `tdp.py`.
- Ensure the correct Solidity version is selected using `solc-select`.

🚀 **Use these scripts to quickly assess smart contract complexity risks!** 🚀

---

### **📜 Example Full Command Workflow**
```sh
# Step 1: Set Up venv & Install Dependencies
python3 -m venv venv
source venv/bin/activate  # (Linux/macOS) OR venv\Scripts\activate (Windows)
pip install slither-analyzer jq solc-select

# Step 2: Install & Select solc Version
solc-select install 0.8.20
solc-select use 0.8.20
solc --version  # Verify installation

# Step 3: Run Slither & Extract Data
slither 0xCONTRACT_ADDRESS --print function-summary &> function-summary.txt
slither 0xCONTRACT_ADDRESS --print inheritance --json - | jq '.' > inheritance.json
slither 0xCONTRACT_ADDRESS
cat $(find crytic-export -name "*sol") > flat.sol

# Step 4: Analyze Metrics
python function-summary.py
python inheritance.py
python tdp.py
```

---

## **💡 Future Improvements**
- Automate running all scripts with a single command.
- Improve parsing for **contracts with deep inheritance trees**.
- Extend analysis to detect **loop nesting and inline assembly usage**.
