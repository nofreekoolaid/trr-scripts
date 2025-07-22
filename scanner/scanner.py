#!/usr/bin/env python3
import os
import sys
import requests
import json
import time
import yaml
import networkx as nx
import logging
import datetime
import shutil
from typing import Set
from web3 import Web3
from typing import Set, Dict, List
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from requests.exceptions import RequestException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler()]
)

def load_config(config_path: str = "config.yaml") -> Dict:
    try:
        with open(config_path) as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.error(f"Error loading config file: {e}")
        sys.exit(1)

config = load_config()

SEED_CONTRACTS = [Web3.to_checksum_address(addr) for addr in config['seed_contracts']]
BLACKLIST = {Web3.to_checksum_address(addr) for addr in config['blacklist_contracts']}
LIMIT = config.get('num_transactions', 10)
MAX_DEPTH = config.get('max_depth', 1)
TENDERLY_CREDS = config['tenderly_credentials']
TENDERLY_KEY = TENDERLY_CREDS['access_key']
ETH_RPC_URL       = os.getenv("ETH_RPC_URL")
ETH_RPC_URL = f"https://mainnet.gateway.tenderly.co/{TENDERLY_KEY}"
w3 = Web3(Web3.HTTPProvider(ETH_RPC_URL))
SIM_METHOD = "tenderly_traceTransaction"
NETWORK_ID = "1"
ETHERSCAN_API_KEY = config['etherscan_api_key']

BASE_URL = "https://api.tenderly.co/api/v1"
ETHERSCAN_URL = "https://api.etherscan.io/api"

CONTRACT_CACHE_FILE = "contract_cache.json"

def load_contract_cache():
    try:
        with open(CONTRACT_CACHE_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_contract_cache(cache):
    with open(CONTRACT_CACHE_FILE, 'w') as f:
        json.dump(cache, f)

contract_name_cache = load_contract_cache()

@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(RequestException)
)
# Cache for names
def fetch_contract_name(addr):
    checksum_addr = Web3.to_checksum_address(addr)
    if checksum_addr in contract_name_cache:
        return contract_name_cache[checksum_addr]
    params = {
        "module": "contract",
        "action": "getsourcecode",
        "address": addr,
        "apikey": ETHERSCAN_API_KEY
    }
    try:
        time.sleep(0.3)
        
        resp = requests.get(ETHERSCAN_URL, params=params)
        resp.raise_for_status()
        result = resp.json().get("result") or []
        if result and isinstance(result, list):
            entry = result[0]
            name = entry.get("ContractName")
            if name:
                contract_name_cache[checksum_addr] = name
                save_contract_cache(contract_name_cache)
                return name
    except Exception:
        pass
    # fallback to shortened address
    short = checksum_addr[:6] + '...' + checksum_addr[-4:]
    contract_name_cache[checksum_addr] = short
    save_contract_cache(contract_name_cache)
    return short

@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(RequestException)
)
def fetch_recent_transactions(contract: str, limit=10):
    time.sleep(0.3)

    url = f"{BASE_URL}/public-contract/{NETWORK_ID}/address/{contract}/explorer/transactions"
    # headers = {"X-Access-Key": TENDERLY_KEY}
    # resp = requests.get(url, headers=headers, params={"limit": limit})
    resp = requests.get(url, params={"limit": limit})
    resp.raise_for_status()
    data = resp.json()
    txs = data.get("transactions", []) if isinstance(data, dict) else data
    return [tx.get("transaction_hash") or tx.get("hash") for tx in txs[:limit]]


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=5),
    stop=stop_after_attempt(3)
)
def simulate_and_extract(tx_hash):
    time.sleep(0.3)

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


# Initialize crawling data structures
discovered_contracts: Set[str] = set(SEED_CONTRACTS)
untraced_contracts: Set[str] = set(SEED_CONTRACTS)
contract_graph = nx.DiGraph()

for contract in SEED_CONTRACTS:
    name = fetch_contract_name(contract)
    contract_graph.add_node(contract, name=name, label=name)


def is_eoa(address: str) -> bool:
    try:
        checksum_addr = Web3.to_checksum_address(address)
        return (
            not w3.eth.get_code(checksum_addr)
            and checksum_addr not in BLACKLIST
        )
    except Exception as e:
        logging.warning(f"EOA check failed for {address[:10]}...: {str(e)}")
        return True

def update_graph(source: str, targets: Set[str]):
    for target in targets:
        if is_eoa(target):
            continue

        if target not in contract_graph:
            name = fetch_contract_name(target)
            logging.info(f"    + New contract: {target} ({name})")
            contract_graph.add_node(target, name=name, label=name)

        discovered_contracts.add(target)
        untraced_contracts.add(target)

        if contract_graph.has_edge(source, target):
            contract_graph[source][target]["weight"] += 1
        else:
            contract_graph.add_edge(source, target, weight=1)

def process_contract(contract: str):
    if Web3.to_checksum_address(contract) in BLACKLIST:
        logging.warning(f"Skipping blacklisted contract: {contract}")
        return
    logging.info(f"Processing contract: {contract} ({fetch_contract_name(contract)})")
    try:
        txs = fetch_recent_transactions(contract, LIMIT)
        logging.info(f"Transactions pulled: {len(txs)}")
        if not txs:
            logging.info(f"No transactions found for {contract}")
            return

        for tx in txs:
            try:
                targets = simulate_and_extract(tx)
                if not targets:
                    continue
                
                logging.info(f"Transaction: {tx}... ({len(targets)} interactions)")
                update_graph(contract, targets)
                
            except Exception as e:
                logging.error(f"Error processing tx {tx}...: {str(e)}")
                continue
                
    except Exception as e:
        logging.error(f"Failed to process contract {contract}: {str(e)}")


def rank_contracts(graph, top_n=10):    
    pr = nx.pagerank(graph, weight='weight')  
    ranked = sorted(pr.items(), key=lambda x: x[1], reverse=True)
    
    logging.info(f"Top {top_n} Critical Contracts:")
    for i, (contract, score) in enumerate(ranked[:top_n], 1):
        name = graph.nodes[contract].get('name', contract[:8]+'...')
        logging.info(f"{i}. {name} ({contract[:8]}...): {score:.6f}")
    
    return ranked


def main():
    # Output directory setup
    run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"run_output_{run_id}"
    os.makedirs(output_dir, exist_ok=True)

    global logging
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(os.path.join(output_dir, "run.log"))
        ]
    )

    current_depth = 0
    depth_queues = {0: set(untraced_contracts)}
    contracts_processed = 0
    max_contracts_to_process = 2
    
    while current_depth <= MAX_DEPTH and depth_queues.get(current_depth) and contracts_processed < max_contracts_to_process:
        logging.info(f"\n=== Depth {current_depth} ===")
        
        for contract in list(depth_queues[current_depth]):
            if is_eoa(contract):
                depth_queues[current_depth].remove(contract)
                continue
            process_contract(contract)
            contracts_processed += 1
            if contracts_processed >= max_contracts_to_process:
                break
            
            if current_depth + 1 not in depth_queues:
                depth_queues[current_depth + 1] = set()
            
            for new_contract in discovered_contracts - set(depth_queues[current_depth]):
                if is_eoa(new_contract):
                    continue
                if new_contract not in depth_queues.get(current_depth + 1, set()):
                    depth_queues[current_depth + 1].add(new_contract)
        if contracts_processed >= max_contracts_to_process:
            break
        
        current_depth += 1

    graph_path = os.path.join(output_dir, "contract_graph.gexf")
    nx.write_gexf(contract_graph, graph_path)

    logging.info("\n=== Summary ===")
    logging.info(f"Total contracts discovered: {len(discovered_contracts)}")
    logging.info(f"Graph size: {len(contract_graph.nodes())} nodes, {len(contract_graph.edges())} edges")

    ranked_contracts = rank_contracts(contract_graph)

if __name__ == '__main__':
    main()
