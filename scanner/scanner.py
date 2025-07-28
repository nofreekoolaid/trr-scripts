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

class APIRateLimiter:
    def __init__(self):
        self.last_call = 0
        self.min_delay = 0.4
    
    def wait(self):
        elapsed = time.time() - self.last_call
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self.last_call = time.time()

limiter = APIRateLimiter()

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
        limiter.wait()
        
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
    # fallback
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
    time.sleep(0.5)

    params = {
        "module": "account",
        "action": "txlist",
        "address": contract,
        "startblock": 0,
        "endblock": 99999999,
        "sort": "desc",  # Most recent
        "apikey": ETHERSCAN_API_KEY
    }

    try:
        resp = requests.get(ETHERSCAN_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") == "1" and data.get("message") == "OK":
            txs = data.get("result", [])
            incoming_txs = [tx["hash"] for tx in txs if tx.get("to", "").lower() == contract.lower()]
            return incoming_txs[:limit]
        logging.warning(f"Etherscan API error for {contract[:8]}...: {data.get('message')}")
        return []
    except Exception as e:
        logging.warning(f"Error fetching Etherscan transactions for {contract[:8]}...: {str(e)}")
        return []



@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(RequestException)
)
def get_contract_creator(contract_address):
    limiter.wait()
    params = {
        "module": "contract",
        "action": "getcontractcreation",
        "contractaddresses": contract_address,
        "apikey": ETHERSCAN_API_KEY
    }
    response = requests.get(ETHERSCAN_URL, params=params)
    response.raise_for_status()
    result = response.json().get("result", [])
    if result and isinstance(result, list):
        creator = result[0].get("contractCreator")
        if creator:
            return Web3.to_checksum_address(creator)
    return None

@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(RequestException)
)
def get_contracts_deployed_by(deployer_address):
    limiter.wait()
    params = {
        "module": "account",
        "action": "txlist",
        "address": deployer_address,
        "startblock": 0,
        "endblock": 99999999,
        "sort": "asc",
        "apikey": ETHERSCAN_API_KEY
    }
    response = requests.get(ETHERSCAN_URL, params=params)
    response.raise_for_status()
    txs = response.json().get("result", [])
    contracts = set()
    for tx in txs:
        if tx.get("to") == "" and tx.get("contractAddress"):
            contracts.add(Web3.to_checksum_address(tx["contractAddress"]))
    return list(contracts)

def annotate_and_add_contract(contract_addr, method, contract_graph, discovered_contracts, untraced_contracts):
    """
    Add a contract to the graph (if not present), annotate with discovery method,
    and add to discovered/untraced sets.
    """
    if contract_addr not in contract_graph:
        name = fetch_contract_name(contract_addr)
        contract_graph.add_node(
            contract_addr, 
            name=name, 
            label=name,
            discovery_method=method
        )
    discovered_contracts.add(contract_addr)
    untraced_contracts.add(contract_addr)


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=5),
    stop=stop_after_attempt(3)
)
def simulate_and_extract(tx_hash):
    limiter.wait()

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

    if isinstance(raw, list):
        calls = raw
    elif isinstance(raw.get("trace"), list):
        calls = raw.get("trace")
    else:
        calls = raw.get("calls") or (raw.get("trace") or {}).get("calls") or []
    call_targets = {c.get("to") for c in calls if c.get("to")}

    assets = raw.get("assetChanges", []) if isinstance(raw, dict) else []
    asset_targets = {a.get("address") for a in assets if a.get("address")}

    logs = raw.get("decodedLogs", []) or raw.get("logs", []) if isinstance(raw, dict) else []
    log_targets = {l.get("address") for l in logs if l.get("address")}

    return sorted(call_targets | asset_targets | log_targets)


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

def deployer_discovery_pass(contracts_to_check, blacklist, contract_graph, discovered_contracts, untraced_contracts, label="deployer"):
    """
    For each contract in contracts_to_check:
        - Find its deployer
        - Get all contracts deployed by that deployer
        - Add them to candidate sets/graph, annotated as discovered via 'deployer'
    """
    new_contracts = set()
    for contract in contracts_to_check:
        try:
            if not Web3.is_address(contract) or Web3.to_checksum_address(contract) in blacklist:
                continue
            creator = get_contract_creator(contract)
            if not creator:
                logging.info(f"[{label}] Could not find creator for contract {contract[:8]}...")
                continue
            logging.info(f"[{label}] Deployer for {contract[:8]}...: {creator[:8]}...")
            deployed = get_contracts_deployed_by(creator)
            valid_deployed = [
                addr for addr in deployed 
                if Web3.is_address(addr) and 
                Web3.to_checksum_address(addr) not in blacklist and
                not is_eoa(addr)
            ]
            logging.info(f"[{label}] {len(valid_deployed)} valid contracts deployed by {creator[:8]}...")
            for sibling in valid_deployed:
                annotate_and_add_contract(
                    sibling,
                    method=label,
                    contract_graph=contract_graph,
                    discovered_contracts=discovered_contracts,
                    untraced_contracts=untraced_contracts
                )
                new_contracts.add(sibling)
                logging.info(f"[{label}] + Sibling contract discovered: {sibling}")
                
        except Exception as e:
            logging.error(f"[{label}] Error discovering siblings for {contract}: {str(e)}")
    
    return new_contracts

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
    checksum_addr = Web3.to_checksum_address(contract)
    if checksum_addr in BLACKLIST:
        logging.warning(f"Skipping blacklisted contract: {contract}")
        return
    if Web3.to_checksum_address(contract) in BLACKLIST:
        logging.warning(f"Skipping blacklisted contract: {contract}")
        return
    contract_name = fetch_contract_name(contract)
    logging.info(f"Processing contract: {contract} ({contract_name})")

    try:
        txs = fetch_recent_transactions(contract, LIMIT)
        logging.info(f"Transactions pulled: {len(txs)}")
        if not isinstance(txs, list) or not txs:
            logging.info(f"No valid transactions found for {contract}")
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
    
    logging.info(f"\nTop {top_n} Critical Contracts:")
    for i, (contract, score) in enumerate(ranked[:top_n], 1):
        name = graph.nodes[contract].get('name', contract[:8]+'...')
        method = graph.nodes[contract].get('discovery_method', 'unknown')
        logging.info(f"{i}. {name} ({contract[:8]}...): {score:.6f} [via {method}]")
    
    return ranked


def main():
    # Output directory setup
    output_dir = os.path.dirname(__file__)

    global logging
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(os.path.join(output_dir, "output.log"))
        ]
    )

    discovered_contracts: Set[str] = set(SEED_CONTRACTS)
    untraced_contracts: Set[str] = set(SEED_CONTRACTS)
    contract_graph = nx.DiGraph()

    for contract in SEED_CONTRACTS:
        name = fetch_contract_name(contract)
        contract_graph.add_node(contract, name=name, label=name)

    logging.info("\n=== Deployer Discovery Pass (PRE-CRAWL) ===")
    deployer_discovery_pass(
        contracts_to_check=SEED_CONTRACTS,
        blacklist=BLACKLIST,
        contract_graph=contract_graph,
        discovered_contracts=discovered_contracts,
        untraced_contracts=untraced_contracts,
        label="deployer_pre"
    )

    valid_contracts = [
        c for c in untraced_contracts 
        if Web3.is_address(c) and 
        Web3.to_checksum_address(c) not in BLACKLIST and
        not is_eoa(c)
    ]
    untraced_contracts = set(valid_contracts)

    current_depth = 0
    depth_queues = {0: set(untraced_contracts)}
    contracts_processed = 0
    
    while current_depth <= MAX_DEPTH and depth_queues.get(current_depth):
        logging.info(f"\n=== Depth {current_depth} ===")
        
        for contract in list(depth_queues[current_depth]):
            if is_eoa(contract):
                depth_queues[current_depth].remove(contract)
                continue
            process_contract(contract)
            contracts_processed += 1
            
            if current_depth + 1 not in depth_queues:
                depth_queues[current_depth + 1] = set()
            
            for new_contract in discovered_contracts - set(depth_queues[current_depth]):
                if is_eoa(new_contract):
                    continue
                if new_contract not in depth_queues.get(current_depth + 1, set()):
                    depth_queues[current_depth + 1].add(new_contract)
        
        if current_depth == 1:
            logging.info("\n=== Deployer Discovery Pass (POST-CRAWL) ===")
            # Get contracts discovered through interactions only
            interaction_discovered = [
                c for c in discovered_contracts 
                if contract_graph.nodes[c].get('discovery_method') not in ["seed", "deployer_pre"]
            ]
            deployer_discovery_pass(
                contracts_to_check=interaction_discovered,
                blacklist=BLACKLIST,
                contract_graph=contract_graph,
                discovered_contracts=discovered_contracts,
                untraced_contracts=untraced_contracts,
                label="deployer_post"
            )
        
        current_depth += 1

    # Final output and analysis
    graph_path = os.path.join(output_dir, "contract_graph.gexf")
    nx.write_gexf(contract_graph, graph_path)

    logging.info("\n=== Summary ===")
    logging.info(f"Total contracts discovered: {len(discovered_contracts)}")
    logging.info(f"Graph size: {len(contract_graph.nodes())} nodes, {len(contract_graph.edges())} edges")

    # Show discovery method breakdown
    methods = {}
    for node in contract_graph.nodes():
        method = contract_graph.nodes[node].get('discovery_method', 'unknown')
        methods[method] = methods.get(method, 0) + 1
    logging.info("\nDiscovery Methods:")
    for method, count in sorted(methods.items()):
        logging.info(f"  {method}: {count} contracts")

    ranked_contracts = rank_contracts(contract_graph)

if __name__ == '__main__':
    main()
