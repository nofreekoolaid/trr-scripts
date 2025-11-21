## **🔍 Smart Contract Analysis Scripts**

This repository contains **Python and Bash scripts** for analyzing the **complexity, risk metrics, and metadata** of verified Ethereum/Arbitrum smart contracts. These tools use [Slither](https://github.com/crytic/slither), `solc-select`, and DeFiLlama APIs to extract and aggregate relevant data.

---

## **📈 Overview**
This toolkit helps you compute and summarize:
1. **Cyclomatic Complexity (TCC)** and **External Calls (TEC)** from Slither's `function-summary`.
2. **Total Decision Points (TDP)** via custom parsing of Solidity/Vyper code.
3. **Inheritance Depth** from Slither's `inheritance` printer.
4. **Deployment Dates** using Etherscan/Arbiscan.
5. **TVL Data** for DeFi protocols from DeFiLlama (with linear interpolation and extrapolation support).

---

## **🛠️ Scripts**
| Script | Description |
|--------|-------------|
| `download_contracts.py` | Downloads verified smart contracts in batch from Etherscan/Arbiscan. |
| `codes.py` | Parses and analyzes each contract directory using Slither, outputs `code.json` files. |
| `summary.py` | Aggregates results from `code.json` files across contracts. Supports TSV or JSON output. |
| `deployment_dates.sh` | Fetches deployment timestamps for each contract via block explorers. |
| `avg_tvls.py` | Calculates average TVL for a DeFi protocol using the DeFiLlama API. |

**Note**: All scripts are now accessible via the unified `trr` CLI tool (see Usage section below).

---

## **📆 Setup**

### **1. Install `uv` (if not already installed)**
```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
# Or via pip: pip install uv
```

### **2. Install Dependencies**
```sh
uv sync
```

This will create a virtual environment and install all dependencies automatically.

### **3. Install `solc-select`**
```sh
uv pip install solc-select
solc-select install 0.8.20  # or whichever versions are required
solc-select use 0.8.20
```

### **4. Use CLI Tool**
After syncing, use the CLI tool:
```sh
# Simplest: uv run can execute Python scripts directly
uv run trr.py --help

# Or use the installed command (after uv sync)
uv run trr --help

# Or activate the environment first
source .venv/bin/activate
trr --help
```

**Note**: `jq` is still required as a system dependency for some scripts (install via your package manager).

### **5. Configure Environment Variables**
Create a `.env` file in the project root with your API keys:
```sh
cp .env.example .env
# Edit .env with your actual API keys
```

The `.env` file is automatically loaded by the scripts. You can also set environment variables directly if preferred.

### **6. Development Scripts**
Run development tasks using make:
```sh
make lint         # Check code style
make lint-fix     # Auto-fix linting issues
make format       # Format code
make format-check # Check formatting without changing files
make test         # Run tests
make cichecks     # Run all CI checks (tests, lint, format-check)
make help         # Show all available commands

# Quick TVL queries
make tvl PROTOCOL=euler START=2025-01-01 END=2025-01-15
make avgtvl PROTOCOL=euler START=2025-01-01 END=2025-01-15
make tvl PROTOCOL=aave START=2025-01-01 END=2025-01-31 OPTS='--no-extrapolate'
```

Or run directly with uv:
```sh
uv run ruff check .           # Lint
uv run ruff check --fix .     # Lint and fix
uv run ruff format .          # Format
uv run ruff format --check .  # Check formatting
```

---

## **📊 TVL Data Analysis**

The `avg_tvls.py` script fetches Total Value Locked (TVL) data from DeFiLlama for any protocol. It supports linear interpolation for missing data and extrapolation at date range boundaries.

### **Quick Start with Make**

The easiest way to query TVL data:

```sh
# Basic usage: Get daily TVL in CSV format
make tvl PROTOCOL=euler START=2025-01-01 END=2025-01-15

# Get average TVL with interpolation/extrapolation
make avgtvl PROTOCOL=euler START=2025-01-01 END=2025-01-15

# Disable extrapolation (only show dates with surrounding data)
make tvl PROTOCOL=aave START=2025-01-01 END=2025-01-31 OPTS='--no-extrapolate'
```

### **Using the CLI Tool**

```sh
# CSV output (default)
uv run trr.py tvl euler 2025-01-01 2025-01-15

# JSON output
uv run trr.py tvl euler 2025-01-01 2025-01-15 --format json

# Get only the average (backward compatibility)
uv run trr.py tvl euler 2025-01-01 2025-01-15 --mean

# Disable extrapolation
uv run trr.py tvl euler 2025-01-01 2025-01-15 --no-extrapolate
```

### **Direct Script Usage**

```sh
# Basic usage
uv run python avg_tvls.py euler 2025-01-01 2025-01-15

# With options
uv run python avg_tvls.py euler 2025-01-01 2025-01-15 --format json
uv run python avg_tvls.py euler 2025-01-01 2025-01-15 --mean
uv run python avg_tvls.py euler 2025-01-01 2025-01-15 --no-extrapolate
```

### **Example Output**

**CSV format:**
```csv
date,tvl,is_interpolated
2025-01-01,110398623.00,false
2025-01-02,111157719.00,false
2025-01-03,115676449.00,false
2025-01-04,124228188.00,false
2025-01-05,137182701.00,false
```

**Mean format:**
```
Average TVL for euler from 2025-01-01 to 2025-01-15: $130,373,951.00
```

### **Features**

- **Linear Interpolation**: Automatically fills missing dates between data points
- **Extrapolation** (default): Uses linear extrapolation at start/end dates based on trend from nearest two points
- **No Extrapolation** (`--no-extrapolate`): Only returns dates that can be interpolated between two surrounding data points
- **Multiple Formats**: CSV, JSON, or simple mean value
- **Interpolation Flag**: Each date is marked with `is_interpolated` to show whether it's raw or calculated data

---

## **🚀 Usage**

### **Unified CLI (Recommended)**

The `trr` command provides a unified interface for all tools:

```sh
# Show all available commands
uv run trr.py --help
# Or: uv run trr --help

# Download contracts
uv run trr.py download eth contracts.txt
uv run trr.py download arb contracts.txt

# Analyze contracts
uv run trr.py analyze contracts.txt

# Summarize metrics
uv run trr.py summary contracts.txt --tsv > dolomite_code.tsv

# Fetch deployment dates
uv run trr.py deployments eth contracts.txt > deployment_dates.txt

# Calculate TVL data
uv run trr.py tvl dolomite 2022-12-18 2025-02-28 --format csv > avg_tvls.csv
uv run trr.py tvl dolomite 2022-12-18 2025-02-28 --format json
uv run trr.py tvl dolomite 2022-12-18 2025-02-28 --mean  # Backward compatibility

# Contract discovery
uv run trr.py scan --strict-interactions
uv run trr.py scan --previous previous_scan.json

# Compare discovery results
uv run trr.py compare file1.json file2.json --verbose

# Calculate Total Decision Points
uv run trr.py tdp contract1.sol contract2.sol

```

### **Individual Scripts (Legacy)**

You can still use individual scripts directly:

```sh
# Activate the environment
source .venv/bin/activate

# Or run directly with uv
uv run python download_contracts.py arb contracts.txt
uv run python codes.py contracts.txt
uv run python summary.py contracts.txt --tsv
uv run python avg_tvls.py dolomite 2022-12-18 2025-02-28
./deployment_dates.sh arb contracts.txt
```

---

## **🚀 Workflow Example**

### **Step 1: Download Contracts**
Download verified contracts for a list of addresses:
```sh
uv run trr.py download arb contracts.txt
```

### **Step 2: Analyze Contracts**
Each downloaded contract folder must include a `contract_details.json` (created automatically). Analyze them in batch:
```sh
uv run trr.py analyze contracts.txt
```
This produces a `code.json` in each contract folder.

### **Step 3: Summarize Code Metrics**
Merge and summarize complexity and risk metrics:
```sh
uv run trr.py summary contracts.txt --tsv > dolomite_code.tsv
```

### **Step 4: Fetch Deployment Dates**
Get the contract deployment timestamps:
```sh
uv run trr.py deployments arb contracts.txt > deployment_dates.txt
```

### **Step 5: Fetch TVL Stats**
Fetch and compute TVL data over a time range:
```sh
# Using make (easiest)
make tvl PROTOCOL=dolomite START=2022-12-18 END=2025-02-28 > avg_tvls.csv

# Get just the average
make avgtvl PROTOCOL=dolomite START=2022-12-18 END=2025-02-28

# Using CLI
uv run trr.py tvl dolomite 2022-12-18 2025-02-28 --format csv > avg_tvls.csv
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
# Using unified CLI
uv run trr.py download arb contracts.txt
uv run trr.py analyze contracts.txt
uv run trr.py summary contracts.txt --tsv > dolomite_code.tsv
uv run trr.py deployments arb contracts.txt > deployment_dates.txt
uv run trr.py tvl dolomite 2022-12-18 2025-02-28 --format csv > avg_tvls.csv

# Or use make for quick TVL queries
make tvl PROTOCOL=dolomite START=2022-12-18 END=2025-02-28 > avg_tvls.csv
make avgtvl PROTOCOL=dolomite START=2022-12-18 END=2025-02-28
```

This will produce TSV and CSV outputs showing contract complexity and risk metrics.

---

## **🔛 End-to-End Summary**
These scripts automate the **retrieval, analysis, and summarization** of verified smart contracts for quick complexity risk assessments, especially useful in DeFi audit, governance, or research contexts.
