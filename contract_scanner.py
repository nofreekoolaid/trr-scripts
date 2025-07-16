#!/usr/bin/env python3
import os
import sys
import requests
import json
import time

"""
Script to fetch recent on-chain transactions via Tenderly Public Explorer,
then trace each via Tenderly RPC to extract:
  - called contract addresses (via call trace)
  - asset transfer contracts (via assetChanges)
  - event-emitting contracts (via decodedLogs/logs)
  - look up verified contract names via Etherscan API

Requires environment variables:
  - TENDERLY_ACCESS_KEY  Tenderly API key for explorer (X-Access-Key header)
  - ETH_RPC_URL          Tenderly RPC URL (e.g. https://rpc.tenderly.co/<project>)
  - ETHERSCAN_API_KEY    Etherscan API key for name lookup
  - CONTRACT_ADDRESS     Contract address to inspect
  - NETWORK_ID           Chain ID (default: "1" for Ethereum Mainnet)
  - LIMIT                Number of txs to fetch (default: 10)
  - SIM_METHOD           Tenderly RPC method (default: tenderly_traceTransaction)
"""

# Load configuration
TENDERLY_KEY      = os.getenv("TENDERLY_ACCESS_KEY")
ETH_RPC_URL       = os.getenv("ETH_RPC_URL")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
CONTRACT          = os.getenv("CONTRACT_ADDRESS")
NETWORK_ID        = os.getenv("NETWORK_ID", "1")
LIMIT             = int(os.getenv("LIMIT", "10"))
SIM_METHOD        = os.getenv("SIM_METHOD", "tenderly_traceTransaction")

if not (TENDERLY_KEY and ETH_RPC_URL and ETHERSCAN_API_KEY and CONTRACT):
    print("ERROR: Set TENDERLY_ACCESS_KEY, ETH_RPC_URL, ETHERSCAN_API_KEY, and CONTRACT_ADDRESS.")
    sys.exit(1)

BASE_URL = "https://api.tenderly.co/api/v1"
ETHERSCAN_URL = "https://api.etherscan.io/api"

# Cache for names
def fetch_contract_name(addr, cache={}):
    if addr in cache:
        return cache[addr]
    params = {
        "module": "contract",
        "action": "getsourcecode",
        "address": addr,
        "apikey": ETHERSCAN_API_KEY
    }
    try:
        resp = requests.get(ETHERSCAN_URL, params=params)
        resp.raise_for_status()
        result = resp.json().get("result") or []
        if result and isinstance(result, list):
            entry = result[0]
            name = entry.get("ContractName")
            if name:
                cache[addr] = name
                return name
    except Exception:
        pass
    # fallback to shortened address
    short = addr[:6] + '...' + addr[-4:]
    cache[addr] = short
    return short


def fetch_recent_transactions(limit=10):
    url = f"{BASE_URL}/public-contract/{NETWORK_ID}/address/{CONTRACT}/explorer/transactions"
    headers = {"X-Access-Key": TENDERLY_KEY}
    resp = requests.get(url, headers=headers, params={"limit": limit})
    resp.raise_for_status()
    data = resp.json()
    txs = data.get("transactions") if isinstance(data, dict) else data
    return [tx.get("transaction_hash") or tx.get("hash") for tx in txs]


def simulate_and_extract(tx_hash):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": SIM_METHOD,
        "params": [tx_hash]
    }
    resp = requests.post(ETH_RPC_URL, headers={"Content-Type": "application/json"}, json=payload)
    resp.raise_for_status()
    resp_json = resp.json()
    raw = resp_json.get("result", resp_json)

    # Extract call targets
    if isinstance(raw, list):
        calls = raw
    elif isinstance(raw.get("trace"), list):
        calls = raw.get("trace")
    else:
        calls = raw.get("calls") or (raw.get("trace") or {}).get("calls") or []
    call_targets = {c.get("to") for c in calls if c.get("to")}

    # Extract asset transfers
    assets = raw.get("assetChanges", []) if isinstance(raw, dict) else []
    asset_targets = {a.get("address") for a in assets if a.get("address")}

    # Extract event addresses
    logs = raw.get("decodedLogs", []) or raw.get("logs", []) if isinstance(raw, dict) else []
    log_targets = {l.get("address") for l in logs if l.get("address")}

    return sorted(call_targets | asset_targets | log_targets)


def main():
    print(f"Fetching up to {LIMIT} recent transactions for {CONTRACT}...\n")
    txs = fetch_recent_transactions(LIMIT)
    valid = 0
    for tx in txs:
        targets = simulate_and_extract(tx)
        if not targets:
            continue
        print(f"Transaction: {tx}\n  Involved contracts:")
        for addr in targets:
            name = fetch_contract_name(addr)
            print(f"    - {addr}  ({name})")
        valid += 1
        if valid >= 1:
            break
    print("\nDone.")

if __name__ == '__main__':
    main()
