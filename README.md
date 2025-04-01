## **🔍 Smart Contract Analysis Scripts**

This repository contains **Python and Bash scripts** for analyzing the **complexity, risk metrics, and metadata** of verified Ethereum/Arbitrum smart contracts. These tools use [Slither](https://github.com/crytic/slither), `solc-select`, and DeFiLlama APIs to extract and aggregate relevant data.

---

## **📈 Overview**
This toolkit helps you compute and summarize:
1. **Cyclomatic Complexity (TCC)** and **External Calls (TEC)** from Slither’s `function-summary`.
2. **Total Decision Points (TDP)** via custom parsing of Solidity/Vyper code.
3. **Inheritance Depth** from Slither’s `inheritance` printer.
4. **Deployment Dates** using Etherscan/Arbiscan.
5. **Average TVL** for DeFi protocols from DeFiLlama.

---

## **🛠️ Scripts**
| Script | Description |
|--------|-------------|
| `download_contracts.py` | Downloads verified smart contracts in batch from Etherscan/Arbiscan. |
| `codes.py` | Parses and analyzes each contract directory using Slither, outputs `code.json` files. |
| `summary.py` | Aggregates results from `code.json` files across contracts. Supports TSV or JSON output. |
| `deployment_dates.sh` | Fetches deployment timestamps for each contract via block explorers. |
| `avg_tvls.py` | Calculates average TVL for a DeFi protocol using the DeFiLlama API. |

---

## **📆 Setup**

### **1. Install Dependencies**
```sh
python3 -m venv venv
source venv/bin/activate
pip install slither-analyzer jq requests
```

### **2. Install `solc-select`**
```sh
pip install solc-select
solc-select install 0.8.20  # or whichever versions are required
solc-select use 0.8.20
```

---

## **🚀 Workflow**

### **Step 1: Download Contracts**
Download verified contracts for a list of addresses:
```sh
python download_contracts.py arb contracts.txt
```

### **Step 2: Analyze Contracts**
Each downloaded contract folder must include a `contract_details.json` (created automatically). Analyze them in batch:
```sh
python codes.py contracts.txt
```
This produces a `code.json` in each contract folder.

### **Step 3: Summarize Code Metrics**
Merge and summarize complexity and risk metrics:
```sh
python summary.py contracts.txt --tsv > dolomite_code.tsv
```

### **Step 4: Fetch Deployment Dates**
Get the contract deployment timestamps:
```sh
./deployment_dates.sh arb contracts.txt > deployment_dates.txt
```

### **Step 5: Fetch TVL Stats**
Fetch and compute average TVL over a time range:
```sh
python3 avg_tvls.py dolomite 2022-12-18 2025-02-28 > avg_tvls.txt
```

---

## **🧠 Metrics Extracted**

| Metric | Script | Description |
|--------|--------|-------------|
| **TCC (Cyclomatic Complexity)** | `codes.py`, `summary.py` | Sum of decision paths in each contract. |
| **TEC (External Calls)** | `codes.py`, `summary.py` | Number of calls to external contracts. |
| **TDP (Total Decision Points)** | `tdp.py` | Count of `if`, `for`, `require()`, etc. |
| **Inheritance Depth** | `code.py`, `summary.py` | Max inheritance depth per contract. |
| **Source Lines of Code (SLOC)** | `cloc` via `code.py` | Count of executable lines. |
| **TVL (Average)** | `avg_tvls.py` | Uses DeFiLlama to compute average locked value. |
| **Deployment Date** | `deployment_dates.sh` | Date the contract was deployed on-chain. |

---

## **🤝 Notes**
- Ensure environment variables `ETHERSCAN_API_KEY` or `ARBISCAN_API_KEY` are set.

---

## **✅ Example Use Case: Dolomite**
```sh
python download_contracts.py arb contracts.txt
python codes.py contracts.txt
python summary.py contracts.txt --tsv > dolomite_code.tsv
./deployment_dates.sh arb contracts.txt > deployment_dates.txt
python3 avg_tvls.py dolomite 2022-12-18 2025-02-28 > avg_tvls.txt
```

This will produce TSV and JSON outputs showing contract complexity and risk metrics.

---

## **🔛 End-to-End Summary**
These scripts automate the **retrieval, analysis, and summarization** of verified smart contracts for quick complexity risk assessments, especially useful in DeFi audit, governance, or research contexts.
