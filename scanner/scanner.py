#!/usr/bin/env python3
import os
import sys
import requests
import argparse
import json
import time
import yaml
import networkx as nx
import logging
import datetime
import re
import shutil
from typing import Set
from web3 import Web3
from typing import Set, Dict, List
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from requests.exceptions import RequestException

class APIRateLimiter:
    def __init__(self):
        self.last_call = 0
        self.min_delay = 1
    
    def wait(self):
        elapsed = time.time() - self.last_call
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self.last_call = time.time()

limiter = APIRateLimiter()

def display_label(addr: str) -> str:
    """Get display label for an address, using name if available or shortened address if not"""
    if addr in contract_graph.nodes:
        n = contract_graph.nodes[addr].get("name")
        if n and n.strip():
            return n
    return short_addr(addr)

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

DISCOVERED_CONTRACTS_FILE = "discovered_contracts.json"
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

ADDR_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
CONTRACT_CACHE_FILE = "contract_cache.json"

def parse_args():
    parser = argparse.ArgumentParser(description='Contract discovery tool')
    parser.add_argument('--previous', type=str, 
                       help='Path to previous discovered contracts file for comparison')
    return parser.parse_args()

def load_contract_cache() -> Dict[str, str]:
    try:
        with open(CONTRACT_CACHE_FILE, 'r') as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return {}
        cleaned = {}
        for k, v in raw.items():
            if isinstance(k, str) and ADDR_RE.match(k) and isinstance(v, str):
                # normalize keys to checksum
                try:
                    ck = Web3.to_checksum_address(k)
                except Exception:
                    continue
                cleaned[ck] = v
        return cleaned
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_contract_cache(cache: Dict[str, str]) -> None:
    tmp = CONTRACT_CACHE_FILE + ".tmp"
    with open(tmp, 'w') as f:
        json.dump(cache, f, indent=2, sort_keys=True)
    os.replace(tmp, CONTRACT_CACHE_FILE)

contract_name_cache = load_contract_cache()


def short_addr(addr: str) -> str:
    c = Web3.to_checksum_address(addr)
    return c[:6] + "..." + c[-4:]

@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(RequestException)
)
# Cache for names
def fetch_contract_name(addr):
    checksum_addr = Web3.to_checksum_address(addr)
    cached = contract_name_cache.get(checksum_addr)
    if isinstance(cached, str) and cached.strip():
        return cached

    params = {
        "module": "contract",
        "action": "getsourcecode",
        "address": checksum_addr,
        "apikey": ETHERSCAN_API_KEY
    }
    try:
        limiter.wait()
        resp = requests.get(ETHERSCAN_URL, params=params)
        resp.raise_for_status()
        result = resp.json().get("result") or []
        if result and isinstance(result, list):
            entry = result[0]

            # Some proxies come back with blank ContractName but have Implementation
            name = (entry.get("ContractName") or "").strip()
            if not name and entry.get("Proxy") == "1" and entry.get("Implementation"):
                impl = entry["Implementation"]
                # Try to name by implementation address
                impl_params = {
                    "module": "contract",
                    "action": "getsourcecode",
                    "address": impl,
                    "apikey": ETHERSCAN_API_KEY
                }
                limiter.wait()
                impl_resp = requests.get(ETHERSCAN_URL, params=impl_params)
                impl_resp.raise_for_status()
                impl_res = impl_resp.json().get("result") or []
                if impl_res and isinstance(impl_res, list):
                    name = (impl_res[0].get("ContractName") or "").strip()
                    if name:
                        name = f"{name} (Proxy)"

            if name:
                contract_name_cache[checksum_addr] = name
                save_contract_cache(contract_name_cache)
                return name
    except Exception:
        pass
    # fallback
    return short_addr(checksum_addr)

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
            unique_txs = list(dict.fromkeys(incoming_txs))
            if len(unique_txs) != len(incoming_txs):
                logging.warning(f"Removed {len(incoming_txs)-len(unique_txs)} duplicate TXs")
            return unique_txs[:limit]
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

    if not isinstance(result, list):
        logging.warning(f"Unexpected format in getcontractcreation for {contract_address}: {result}")
        return None
    
    if result and isinstance(result, list):
        creator = result[0].get("contractCreator")
        if creator:
            return Web3.to_checksum_address(creator)
    else:
        logging.warning(f"Unexpected item in result[0]: {result[0]}")
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

    if not isinstance(txs, list):
        logging.warning(f"Unexpected txlist result for {deployer_address}: {txs}")
        return []
    
    contracts = set()
    for tx in txs:
        if isinstance(tx, dict) and tx.get("to") == "" and tx.get("contractAddress"):
            try:
                contracts.add(Web3.to_checksum_address(tx["contractAddress"]))
            except Exception:
                continue
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
            label=name if name.strip() else short_addr(contract_addr),
            discovery_method=method
        )
    discovered_contracts.add(contract_addr)
    untraced_contracts.add(contract_addr)

def save_discovered_contracts(contracts: Set[str]):
    try:
        with open(DISCOVERED_CONTRACTS_FILE, 'w') as f:
            json.dump(list(contracts), f)
    except Exception as e:
        logging.error(f"Error saving discovered contracts: {e}")

def load_previous_discovered_contracts() -> Set[str]:
    try:
        with open(DISCOVERED_CONTRACTS_FILE, 'r') as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

# Using fetch_interactions_etherscan instead for now
@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(Exception)
)
def simulate_and_extract(tx_hash):
    limiter.wait()
    logging.info(f"Simulating tx: {tx_hash}")
    
    # Try Tenderly first
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": SIM_METHOD,
            "params": [tx_hash]
        }
        resp = requests.post(ETH_RPC_URL, headers={"Content-Type": "application/json"}, json=payload)
        resp.raise_for_status()
        resp_json = resp.json()
        
        # Handle error response
        if "error" in resp_json:
            logging.warning(f"Tenderly error: {resp_json['error']}")
            return []
            
        result = resp_json.get("result", {})
        
        # Extract all possible interaction targets
        targets = set()
        
        # 1. From trace calls
        trace = result.get("trace", [])
        if isinstance(trace, list):
            for call in trace:
                if call.get("to"):
                    targets.add(call["to"])
        
        # 2. From logs
        logs = result.get("logs", [])
        for log in logs:
            if log.get("address"):
                targets.add(log["address"])
        
        # 3. From state changes (contract creations)
        state_changes = result.get("stateChanges", [])
        for change in state_changes:
            addr = change.get("address")
            if addr and addr not in targets:
                # Check if it's a contract
                code = w3.eth.get_code(Web3.to_checksum_address(addr))
                if code and code != b'':
                    targets.add(addr)
        
        # Filter out EOAs and blacklisted addresses
        filtered_targets = []
        for addr in targets:
            try:
                checksum_addr = Web3.to_checksum_address(addr)
                if checksum_addr in BLACKLIST:
                    continue
                if not is_eoa(checksum_addr):
                    filtered_targets.append(checksum_addr)
            except:
                continue
        
        logging.info(f"Found {len(filtered_targets)} interactions")
        return sorted(filtered_targets)
        
    except Exception as e:
        logging.error(f"Tenderly simulation failed: {str(e)}")
        return fetch_interactions_etherscan(tx_hash)
    
def fetch_interactions_etherscan(tx_hash):
    params = {
        "module": "proxy",
        "action": "eth_getTransactionReceipt",
        "txhash": tx_hash,
        "apikey": ETHERSCAN_API_KEY
    }
    
    try:
        limiter.wait()
        response = requests.get(ETHERSCAN_URL, params=params)
        response.raise_for_status()
        receipt = response.json().get("result", {})
        
        targets = set()
        if receipt.get("to"):
            targets.add(receipt["to"])
        for log in receipt.get("logs", []):
            if log.get("address"):
                targets.add(log["address"])
                
        logging.debug(f"Etherscan found {len(targets)} interactions")
        return sorted(targets)
        
    except Exception as e:
        logging.error(f"Etherscan fallback failed: {str(e)}")
        return []


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

processed_deployers = set()

def deployer_discovery_pass(contracts_to_check, blacklist, contract_graph, discovered_contracts, untraced_contracts, label="deployer"):
    global processed_deployers
    new_contracts = set()
    
    for contract in contracts_to_check:
        try:
            if not Web3.is_address(contract) or Web3.to_checksum_address(contract) in blacklist:
                continue
                
            creator = get_contract_creator(contract)
            if not creator:
                logging.info(f"[{label}] Could not find creator for contract {contract[:8]}...")
                continue
                
            if creator in processed_deployers:
                logging.debug(f"[{label}] Skipping already-processed deployer: {creator[:8]}...")
                continue
                
            processed_deployers.add(creator)
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
                if sibling not in discovered_contracts:
                    annotate_and_add_contract(
                        sibling,
                        method=label,
                        contract_graph=contract_graph,
                        discovered_contracts=discovered_contracts,
                        untraced_contracts=untraced_contracts
                    )
                    if creator:
                        if contract_graph.has_edge(creator, sibling):
                            contract_graph[creator][sibling]["weight"] += 1
                        else:
                            contract_graph.add_edge(creator, sibling, weight=1)
                    new_contracts.add(sibling)
                    logging.info(f"[{label}] + Sibling contract discovered: {sibling[:8]}... (via {creator[:8]})")
                else:
                    logging.debug(f"[{label}] Skipping already-known contract: {sibling[:8]}...")
                    
        except Exception as e:
            logging.error(f"[{label}] Error discovering siblings for {contract}: {str(e)}")
    
    return new_contracts

def update_graph(source: str, targets: Set[str], current_depth: int, depth_queues: Dict[int, Set[str]]):
    global contract_graph, discovered_contracts
    # logging.info(f"Updating graph from {source[:8]}... to {len(targets)} targets")

    for target in targets:
        if is_eoa(target):
            # logging.info(f"Skipping EOA target: {target[:8]}...")
            continue
        if target in processed_contracts or target in depth_queues.get(current_depth + 1, set()):
            print(f"Skipping already processed or queued target: {target[:8]}...")
            continue 

        target = Web3.to_checksum_address(target)
        # logging.info(f"   - Target: {target[:8]}...")
        if target not in discovered_contracts:
            # logging.info(f"    - New contract discovered: {target[:8]}...")
            discovered_contracts.add(target)
            if target not in contract_graph:
                # logging.info(f"     - Adding to graph: {target[:8]}...")
                name = fetch_contract_name(target)
                contract_graph.add_node(
                    target,
                    name=name,
                    label=name if name.strip() else short_addr(target),
                    discovery_method="interaction"
                )
        if not any(target in q for q in depth_queues.values()):
            # logging.info(f"     - Adding to depth queue for depth {current_depth + 1}: {target[:8]}...")
            if current_depth + 1 not in depth_queues:
                depth_queues[current_depth + 1] = set()
            depth_queues[current_depth + 1].add(target)
        if contract_graph.has_edge(source, target):
            # logging.info(f"     - Incrementing edge weight from {source[:8]}... to {target[:8]}...")
            contract_graph[source][target]["weight"] += 1
        else:
            # logging.info(f"     - Adding edge from {source[:8]}... to {target[:8]}...")
            contract_graph.add_edge(source, target, weight=1)

        # if target not in contract_graph:
        #     name = fetch_contract_name(target)
        #     contract_graph.add_node(
        #         target, 
        #         name=name,
        #         label=name if name.strip() else short_addr(target),
        #         discovery_method="interaction"
        #     )
        # else:
        #     if "discovery_method" not in contract_graph.nodes[target]:
        #         contract_graph.nodes[target]["discovery_method"] = "interaction"

        # discovered_contracts.add(target)

        # already_queued = any(target in queue for queue in depth_queues.values())
        # if not already_queued:
        #     depth_queues[current_depth + 1].add(target)

        # if contract_graph.has_edge(source, target):
        #     contract_graph[source][target]["weight"] += 1
        # else:
        #     contract_graph.add_edge(source, target, weight=1)
processed_contracts = set()

def process_contract(contract: str, current_depth: int, depth_queues: Dict[int, Set[str]]):
    if contract in processed_contracts:
        logging.info(f"Skipping already-processed contract: {contract[:8]}...")
        return
    processed_contracts.add(contract)
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
                targets = fetch_interactions_etherscan(tx)
                if not targets:
                    continue
                
                logging.info(f"  -Transaction: {tx}... ({len(targets)} interactions)")
                update_graph(contract, targets, current_depth, depth_queues)
                
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
        name = display_label(contract)
        method = graph.nodes[contract].get('discovery_method', 'unknown')
        logging.info(f"{i}. {name} ({contract[:8]}...): {score:.6f} [via {method}]")
    
    return ranked


def main():
    global contract_graph, discovered_contracts, untraced_contracts

    args = parse_args()
    # Output directory setup
    output_dir = os.path.dirname(__file__)

    # Testing limitations
    test_mode_limit = 10

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

    contract_graph.clear()
    discovered_contracts.clear()
    untraced_contracts.clear()

    for contract in SEED_CONTRACTS:
        name = fetch_contract_name(contract)
        contract_graph.add_node(
            contract, 
            name=name,
            label=name if name.strip() else short_addr(contract),
            discovery_method="seed"
        )
        discovered_contracts.add(contract)
        untraced_contracts.add(contract)

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
    
    while current_depth <= MAX_DEPTH:
        logging.info(f"\n=== Depth {current_depth} === (Queue size: {len(depth_queues.get(current_depth, set()))})")

        if current_depth not in depth_queues or not depth_queues[current_depth]:
            current_depth += 1
            continue

        current_queue = depth_queues[current_depth].copy()
        depth_queues[current_depth].clear()
        for contract in current_queue:
            # logging.info(f"Processing Depth {current_depth} contract: {contract}")
            if is_eoa(contract):
                continue

            process_contract(contract, current_depth, depth_queues)
            contracts_processed += 1

            # if contracts_processed >= test_mode_limit:
            #     logging.info(f"\nTEST MODE: Processed {contracts_processed} contracts, stopping early")
            #     current_depth += 1
            #     contracts_processed = 0
            #     break

        if not depth_queues[current_depth]:
            current_depth += 1
        if all(not queue for queue in depth_queues.values()):
            break
                
        
        # for contract in list(depth_queues[current_depth]):
        #     if is_eoa(contract):
        #         depth_queues[current_depth].remove(contract)
        #         continue
        #     process_contract(contract)
        #     contracts_processed += 1
            
        #     if current_depth + 1 not in depth_queues:
        #         depth_queues[current_depth + 1] = set()
            
        #     for new_contract in discovered_contracts - set(depth_queues[current_depth]):
        #         if is_eoa(new_contract):
        #             continue
        #         if new_contract not in depth_queues.get(current_depth + 1, set()):
        #             depth_queues[current_depth + 1].add(new_contract)
        
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

    logging.info("\n=== Discovery Comparison ===")
    
    # Load previous contracts from either specified file or default location
    previous_file = args.previous if args.previous else DISCOVERED_CONTRACTS_FILE
    try:
        with open(previous_file, 'r') as f:
            previous_discovered = set(json.load(f))
        logging.info(f"Loaded {len(previous_discovered)} contracts from {previous_file}")
    except (FileNotFoundError, json.JSONDecodeError):
        previous_discovered = set()
        logging.info("No previous discovery file found or invalid format")
    
    # Calculate differences
    new_discovered = discovered_contracts - previous_discovered
    disappeared = previous_discovered - discovered_contracts
    
    # Report comparison stats
    logging.info(f"\nDiscovery results:")
    logging.info(f"Total discovered this run: {len(discovered_contracts)}")
    logging.info(f"Previously known contracts: {len(previous_discovered)}")
    logging.info(f"New contracts discovered: {len(new_discovered)}")
    logging.info(f"Contracts from previous run not rediscovered: {len(disappeared)}")
    
    # Save new discoveries to timestamped file
    if new_discovered:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        new_filename = f"new_contracts.json"
        with open(new_filename, 'w') as f:
            json.dump(list(new_discovered), f)
        logging.info(f"\nSaved {len(new_discovered)} new contracts to {new_filename}")
    
    # Print new contracts with names if verbose
    if new_discovered and config.get('verbose_diff', False):
        logging.info("\nNewly discovered contracts:")
        for i, contract in enumerate(sorted(new_discovered), 1):
            name = display_label(contract)
            logging.info(f"{i}. {contract} ({name})")

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
