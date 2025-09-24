#!/usr/bin/env python3
import os
import sys
import requests
import argparse
import json
import time
import yaml
import random
import networkx as nx
import logging
import datetime
import re
from web3 import Web3
from typing import Set, Dict, List, Tuple
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from requests.exceptions import RequestException
from functools import lru_cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from compare_contracts import compare_contract_files
from contextlib import redirect_stdout
from trace_providers import get_trace_provider
from interaction_filters import InteractionFilter
import io

random.seed(0)



# Create global session with pooling and retries
session = requests.Session()
session.headers.update({"User-Agent": "liftoff-scanner/1.0"})

retry_cfg = Retry(total=5, backoff_factor=0.5,
                  status_forcelist=(429,500,502,503,504),
                  allowed_methods=frozenset(["GET","POST"]))
adapter = HTTPAdapter(max_retries=retry_cfg, pool_connections=20, pool_maxsize=50)
session.mount("https://", adapter); session.mount("http://", adapter)

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


SAVE_DIR = "output_contracts"
DISCOVERED_CONTRACTS_FILE = os.path.join(SAVE_DIR, "discovered_contracts_latest.json")
SEED_CONTRACTS = [Web3.to_checksum_address(addr) for addr in config['seed_contracts']]
BLACKLIST = {Web3.to_checksum_address(addr) for addr in config['blacklist_contracts']}
LIMIT = config.get('num_transactions', 10)
MAX_DEPTH = config.get('max_depth', 1)
TENDERLY_CREDS = config['tenderly_credentials']
TENDERLY_KEY = TENDERLY_CREDS['access_key']
ETH_RPC_URL = os.getenv("ETH_RPC_URL") or f"https://mainnet.gateway.tenderly.co/{TENDERLY_KEY}"
w3 = Web3(Web3.HTTPProvider(ETH_RPC_URL))
SIM_METHOD = "tenderly_traceTransaction"
NETWORK_ID = "1"
ETHERSCAN_API_KEY = config['etherscan_api_key']

BASE_URL = "https://api.tenderly.co/api/v1"
ETHERSCAN_URL = "https://api.etherscan.io/api"

ADDR_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
CONTRACT_CACHE_FILE = "contract_cache.json"

NAME_BLACKLIST_RE = re.compile(config['name_blacklist_regex'], re.I) if config.get('name_blacklist_regex') else None

def should_skip_by_name(addr: str, name: str) -> bool:
    return bool(NAME_BLACKLIST_RE and name and NAME_BLACKLIST_RE.search(name))


def annotate_and_add_contract(contract_addr, method, contract_graph, discovered_contracts, untraced_contracts):
    name = fetch_contract_name(contract_addr)
    if should_skip_by_name(contract_addr, name):
        logging.info(f"Skipping by name blacklist: {name} ({contract_addr})")
        return
    
    if contract_addr not in contract_graph:
        cached = contract_name_cache.get(Web3.to_checksum_address(contract_addr))
        creation_date = cached.get('creation_date') if cached and isinstance(cached, dict) else None

        contract_graph.add_node(
            contract_addr, 
            name=name,
            label=name if name.strip() else short_addr(contract_addr),
            discovery_methods=[method],
            creation_date=creation_date
        )
    else:
        current_methods = contract_graph.nodes[contract_addr].get('discovery_methods', [])
        if method not in current_methods:
            current_methods.append(method)
            contract_graph.nodes[contract_addr]['discovery_methods'] = current_methods

    discovered_contracts.add(contract_addr)
    untraced_contracts.add(contract_addr)

def parse_args():
    parser = argparse.ArgumentParser(description='Contract discovery tool')
    parser.add_argument('--previous', type=str, 
                       help='Path to previous discovered contracts file for comparison')
    parser.add_argument('--strict-interactions', action='store_true',
                       help='Enable strict trace-based interaction filtering')
    return parser.parse_args()

def load_contract_cache() -> Dict[str, str]:
    try:
        with open(CONTRACT_CACHE_FILE, 'r') as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return {}
        cleaned = {}
        for k, v in raw.items():
            if not isinstance(k, str) or not ADDR_RE.match(k):
                continue
                
            try:
                ck = Web3.to_checksum_address(k)
            except Exception:
                continue

            # Old format
            if isinstance(v, str):
                cleaned[ck] = {
                    'name': v,
                    'creation_date': None,
                    'bytecode_hash': None,
                    'deployer': None
                }
            
            # New format
            elif isinstance(v, dict):
                cleaned[ck] = {
                    'name': v.get('name', ''),
                    'creation_date': v.get('creation_date'),
                    'bytecode_hash': v.get('bytecode_hash'),
                    'deployer': v.get('deployer')
                }

        return cleaned
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_contract_cache(cache: Dict[str, Dict]) -> None:
    tmp = CONTRACT_CACHE_FILE + ".tmp"
    cleaned = {}
    for addr, data in cache.items():
        try:
            ck = Web3.to_checksum_address(addr)
            cleaned[ck] = {
                'name': data.get('name', ''),
                'creation_date': data.get('creation_date'),
                'bytecode_hash': data.get('bytecode_hash'),
                'deployer': data.get('deployer')
            }
        except Exception:
            continue

    try:
        with open(tmp, 'w') as f:
            json.dump(cleaned, f, indent=2, sort_keys=True)
        os.replace(tmp, CONTRACT_CACHE_FILE)
    except Exception as e:
        logging.error(f"Error saving contract cache: {e}")
        if os.path.exists(tmp):
            os.unlink(tmp)

contract_name_cache = load_contract_cache()

@lru_cache(maxsize=100000)
def _bytecode(addr_checksum: str) -> bytes:
    return bytes(w3.eth.get_code(addr_checksum) or b"")

def get_bytecode_hash(addr: str) -> str | None:
    cs = Web3.to_checksum_address(addr)
    code = _bytecode(cs)
    if not code:
        return None
    return Web3.keccak(code).hex()

def short_addr(addr: str) -> str:
    c = Web3.to_checksum_address(addr)
    return c[:6] + "..." + c[-4:]



@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(RequestException)
)
def batch_get_contract_creation(contract_addresses: List[str]) -> Dict[str, str]:
    if not contract_addresses:
        return {}
    
    batch_size = 5
    results = {}
    
    for i in range(0, len(contract_addresses), batch_size):
        batch = contract_addresses[i:i + batch_size]
        batch_str = ",".join(batch)
        
        params = {
            "module": "contract",
            "action": "getcontractcreation",
            "contractaddresses": batch_str,
            "apikey": ETHERSCAN_API_KEY
        }
        
        try:
            limiter.wait()
            response = session.get(ETHERSCAN_URL, params=params, timeout=30)
            response.raise_for_status()
            result = response.json().get("result", [])
            
            if not isinstance(result, list):
                logging.warning(f"Unexpected batch result format: {result}")
                continue
            
            for item in result:
                if isinstance(item, dict):
                    contract_addr = item.get("contractAddress")
                    creator = item.get("contractCreator")
                    timestamp = item.get("timestamp")
                    
                    if contract_addr and Web3.is_address(contract_addr):
                        checksum_addr = Web3.to_checksum_address(contract_addr)
                        results[checksum_addr] = {
                            'creator': Web3.to_checksum_address(creator) if creator else None,
                            'timestamp': timestamp
                        }
            
            time.sleep(0.5)
            
        except Exception as e:
            logging.error(f"Batch contract creation fetch failed: {str(e)}")
            continue
    
    return results


def deduplicate_by_bytecode(contracts: Set[str]) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    unique_by_hash = {}
    duplicates_by_hash = {}
    
    for addr in sorted(contracts):
        meta = contract_name_cache.get(Web3.to_checksum_address(addr), {})
        bh = meta.get("bytecode_hash") or get_bytecode_hash(addr)
        
        if bh:
            contract_name_cache[Web3.to_checksum_address(addr)] = {
                **(meta or {}), 
                "bytecode_hash": bh
            }
            
            if bh not in unique_by_hash:
                unique_by_hash[bh] = addr
            else:
                # logging.info(f"Duplicate bytecode detected: {addr} and {unique_by_hash[bh]} (hash: {bh})")
                duplicates_by_hash.setdefault(bh, []).append(addr)
    
    save_contract_cache(contract_name_cache)
    
    return unique_by_hash, duplicates_by_hash

@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(RequestException)
)
# Cache for names
def fetch_contract_name(addr):
    checksum_addr = Web3.to_checksum_address(addr)
    cached = contract_name_cache.get(checksum_addr)

    if cached and isinstance(cached, dict) and cached.get('name'):
        return cached['name']
    # Old cache
    elif isinstance(cached, str) and cached.strip():
        return cached
    
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
        resp = session.get(ETHERSCAN_URL, params=params, timeout=30)
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
                impl_resp = session.get(ETHERSCAN_URL, params=impl_params, timeout=30)
                impl_resp.raise_for_status()
                impl_res = impl_resp.json().get("result") or []
                if impl_res and isinstance(impl_res, list):
                    name = (impl_res[0].get("ContractName") or "").strip()
                    if name:
                        name = f"{name} (Proxy)"

            if name:
                contract_name_cache[checksum_addr] = {
                    'name': name,
                    'creation_date': None
                }
                save_contract_cache(contract_name_cache)
                return name
    except Exception:
        pass
    # fallback
    return short_addr(checksum_addr)

def fetch_and_store_deployer_batch(contracts: List[str]) -> Dict[str, str]:
    creation_data = batch_get_contract_creation(contracts)
    deployers = {}
    
    for contract_addr, data in creation_data.items():
        deployer = data.get('creator')
        if deployer:
            checksum_contract_addr = Web3.to_checksum_address(contract_addr)
            checksum_deployer = Web3.to_checksum_address(deployer)
            
            deployers[checksum_contract_addr] = checksum_deployer
            
            # Update cache
            if contract_addr not in contract_name_cache:
                contract_name_cache[contract_addr] = {
                    'name': fetch_contract_name(contract_addr),
                    'deployer': deployer
                }
            else:
                if isinstance(contract_name_cache[contract_addr], dict):
                    contract_name_cache[contract_addr]['deployer'] = deployer
                else:  # Old format
                    contract_name_cache[contract_addr] = {
                        'name': contract_name_cache[contract_addr],
                        'deployer': deployer
                    }
    
    save_contract_cache(contract_name_cache)
    return deployers

def fetch_and_store_deployer(addr):
    results = fetch_and_store_deployer_batch([addr])
    return results.get(Web3.to_checksum_address(addr))

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
        resp = session.get(ETHERSCAN_URL, params=params, timeout=30)
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


def get_strict_interactions(tx_hash: str, source_addr: str, tx_data: Dict = None, interaction_filter: InteractionFilter = None) -> List[str]:
    """Get interactions using trace-based analysis with strict filtering"""
    if not config.get('strict_interaction_mode', False):
        interactions = get_receipt_interactions_strict(tx_hash, source_addr, interaction_filter)
        return interaction_filter.filter_interactions(interactions, source_addr, tx_data)

    providers = config.get('trace_provider_preference', ['tenderly', 'geth', 'erigon'])
    
    for provider_name in providers:
        try:
            provider = get_trace_provider(provider_name, ETH_RPC_URL)
            trace = provider.get_transaction_trace(tx_hash)
            
            if not trace:
                continue
                
            # Extract only direct calls where source is caller and of allowed types
            direct_calls = provider.extract_direct_calls(
                trace, 
                source_addr, 
                interaction_filter.get_allowed_call_types() if interaction_filter else None
            )
            
            # Filter out EOAs and blacklisted addresses
            basic_filtered = []
            for addr in direct_calls:
                try:
                    checksum_addr = Web3.to_checksum_address(addr)
                    if checksum_addr in BLACKLIST:
                        continue
                    if not is_eoa(checksum_addr):
                        basic_filtered.append(checksum_addr)
                except:
                    continue
            
            # Apply enhanced filtering
            enhanced_filtered = interaction_filter.filter_interactions(
                basic_filtered, source_addr, tx_data
            )

            # logging.info(f"Trace found {len(enhanced_filtered)} filtered calls from {source_addr[:8]}...")
            return sorted(enhanced_filtered)
            
        except Exception as e:
            logging.warning(f"Trace provider {provider_name} failed: {e}")
            continue
    
    # Fallback to receipt-based discovery
    logging.info(f"All trace providers failed, falling back for {tx_hash}")
    interactions = get_receipt_interactions_strict(tx_hash, source_addr, interaction_filter)
    return interaction_filter.filter_interactions(interactions, source_addr, tx_data)

def get_receipt_interactions_strict(tx_hash: str, source_addr: str, interaction_filter: InteractionFilter = None) -> List[str]:
    """Strict version of receipt-based interaction discovery"""
    # First get the transaction receipt for event analysis
    receipt = get_transaction_receipt(tx_hash)
    
    targets = fetch_interactions_etherscan(tx_hash)
    
    if not config.get('strict_interaction_mode', False):
        return targets
    
    # Basic filtering
    filtered_targets = []
    for addr in targets:
        try:
            checksum_addr = Web3.to_checksum_address(addr)
            if checksum_addr in BLACKLIST:
                continue
            if is_eoa(checksum_addr):
                continue
            filtered_targets.append(checksum_addr)
        except:
            continue
    
    # Apply enhanced filtering with receipt data for event analysis
    return interaction_filter.filter_interactions(filtered_targets, source_addr, receipt)


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
    response = session.get(ETHERSCAN_URL, params=params, timeout=30)
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
    response = session.get(ETHERSCAN_URL, params=params, timeout=30)
    response.raise_for_status()
    txs = response.json().get("result", [])

    if not isinstance(txs, list):
        logging.warning(f"Unexpected txlist result for {deployer_address}: {txs}")
        return []
    
    blacklist_lower = {addr.lower() for addr in BLACKLIST} if BLACKLIST else set()
    contracts = set()
    for tx in txs:
        if isinstance(tx, dict) and tx.get("to") == "" and tx.get("contractAddress"):
            try:
                addr = Web3.to_checksum_address(tx["contractAddress"])
                if addr.lower() not in blacklist_lower:
                    contracts.add(addr)
            except Exception:
                continue
    return list(contracts)


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(RequestException)
)
def fetch_and_store_creation_date_batch(contracts: List[str]) -> Dict[str, str]:
    if not contracts:
        return {}
    
    contracts_to_fetch = []
    for contract in contracts:
        checksum_addr = Web3.to_checksum_address(contract)
        cached = contract_name_cache.get(checksum_addr)
        if not cached or not isinstance(cached, dict) or not cached.get('creation_date'):
            contracts_to_fetch.append(checksum_addr)
    
    if not contracts_to_fetch:
        return {}
    
    batch_results = batch_get_contract_creation(contracts_to_fetch)
    
    creation_dates = {}
    for contract_addr, data in batch_results.items():
        if data.get('timestamp'):
            timestamp = int(data["timestamp"])
            creation_date = datetime.datetime.fromtimestamp(timestamp).isoformat()
            creation_dates[contract_addr] = creation_date
            
            # Update cache
            if contract_addr not in contract_name_cache:
                contract_name_cache[contract_addr] = {
                    'name': fetch_contract_name(contract_addr),
                    'creation_date': creation_date,
                    'deployer': data.get('creator')
                }
            else:
                if isinstance(contract_name_cache[contract_addr], dict):
                    contract_name_cache[contract_addr]['creation_date'] = creation_date
                    contract_name_cache[contract_addr]['deployer'] = data.get('creator')
                else:  # Old format
                    contract_name_cache[contract_addr] = {
                        'name': contract_name_cache[contract_addr],
                        'creation_date': creation_date,
                        'deployer': data.get('creator')
                    }
    
    save_contract_cache(contract_name_cache)
    return creation_dates

def fetch_and_store_creation_date(addr):
    """Single contract version - returns date string or None"""
    results = fetch_and_store_creation_date_batch([addr])
    return results.get(Web3.to_checksum_address(addr))


def display_newest_contracts(graph, top_n=10):
    """Display newest contracts by creation date"""
    contracts_with_dates = []
    
    for addr in graph.nodes():
        node = graph.nodes[addr]
        creation_date = node.get('creation_date')
        
        if creation_date:
            try:
                dt = datetime.datetime.fromisoformat(creation_date)
                contracts_with_dates.append((addr, dt, creation_date))
            except ValueError:
                continue
    
    contracts_with_dates.sort(key=lambda x: x[1], reverse=True)
    
    logging.info(f"Top {top_n} Newest Contracts:")
    for i, (addr, dt, date_str) in enumerate(contracts_with_dates[:top_n], 1):
        name = display_label(addr)
        methods = graph.nodes[addr].get('discovery_methods', ['unknown'])
        method_str = ", ".join(methods)
        logging.info(f"{i}. {name} ({addr}) - Created: {date_str} [via {method_str}]")
    
    return contracts_with_dates[:top_n]

def export_contracts_metadata(graph, ranked_contracts, output_path):
    import csv
    
    unique_by_hash, _ = deduplicate_by_bytecode(set(graph.nodes()))
    canonical_addrs = set(unique_by_hash.values())
    
    pagerank_dict = dict(ranked_contracts)
    
    with open(output_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['address', 'name', 'creation_date', 'methods', 'pagerank'])
        
        for addr in canonical_addrs:
            if addr in graph.nodes():
                node = graph.nodes[addr]
                
                name = node.get('name', '')
                creation_date = node.get('creation_date', '')
                
                methods = node.get('discovery_methods', [])
                methods_str = ','.join(methods) if isinstance(methods, list) else str(methods)
                
                pagerank = pagerank_dict.get(addr, 0)
                
                writer.writerow([addr, name, creation_date, methods_str, f"{pagerank:.8f}"])
    
    logging.info(f"Exported metadata for {len(canonical_addrs)} canonical contracts to {output_path}")

def save_discovered_contracts(contracts: Set[str], graph = None, ranked_contracts= None):
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamped_file = os.path.join(SAVE_DIR, f"discovered_contracts_{timestamp}.json")
        with open(timestamped_file, 'w') as f:
            json.dump(sorted(contracts), f, indent=2)
        # Latest
        with open(DISCOVERED_CONTRACTS_FILE, 'w') as f:
            json.dump(sorted(contracts), f, indent=2)

        # Export metadata CSV if graph and rankings are provided
        if graph is not None and ranked_contracts is not None:
            # export_contracts_metadata(graph, ranked_contracts, os.path.join(SAVE_DIR, f"discovered_contracts_meta_{timestamp}.csv"))
            export_contracts_metadata(graph, ranked_contracts, os.path.join(SAVE_DIR, "discovered_contracts_meta.csv"))

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
def simulate_and_extract(tx_hash, source_addr=None, tx_data=None, interaction_filter=None):
    if config.get('strict_interaction_mode', False) and source_addr:
        return get_strict_interactions(tx_hash, source_addr, tx_data, interaction_filter)
    else:

        limiter.wait()
        logging.info(f"Simulating tx: {tx_hash}")
        
        # Try Tenderly first
        try:
            # Issue with Tenderly using fetch_interactions_etherscan instead
            return fetch_interactions_etherscan(tx_hash)
            # payload = {
            #     "jsonrpc": "2.0",
            #     "id": 1,
            #     "method": SIM_METHOD,
            #     "params": [tx_hash]
            # }
            # resp = session.post(ETH_RPC_URL, headers={"Content-Type": "application/json"}, json=payload, timeout=60)
            # resp.raise_for_status()
            # resp_json = resp.json()
            
            # # Handle error response
            # if "error" in resp_json:
            #     logging.warning(f"Tenderly error: {resp_json['error']}")
            #     return []
                
            # result = resp_json.get("result", {})
            
            # # Extract all possible interaction targets
            # targets = set()
            
            # # 1. From trace calls
            # trace = result.get("trace", [])
            # if isinstance(trace, list):
            #     for call in trace:
            #         if call.get("to"):
            #             targets.add(call["to"])
            
            # # 2. From logs
            # logs = result.get("logs", [])
            # for log in logs:
            #     if log.get("address"):
            #         targets.add(log["address"])
            
            # # 3. From state changes (contract creations)
            # state_changes = result.get("stateChanges", [])
            # for change in state_changes:
            #     addr = change.get("address")
            #     if addr and addr not in targets:
            #         # Check if it's a contract
            #         code = w3.eth.get_code(Web3.to_checksum_address(addr))
            #         if code and code != b'':
            #             targets.add(addr)
            
            # # Filter out EOAs and blacklisted addresses
            # filtered_targets = []
            # for addr in targets:
            #     try:
            #         checksum_addr = Web3.to_checksum_address(addr)
            #         if checksum_addr in BLACKLIST:
            #             continue
            #         if not is_eoa(checksum_addr):
            #             filtered_targets.append(checksum_addr)
            #     except:
            #         continue
            
            # logging.info(f"Found {len(filtered_targets)} interactions")
            # return sorted(filtered_targets)
            
        except Exception as e:
            logging.error(f"Tenderly simulation failed: {str(e)}")
            return get_receipt_interactions_strict(tx_hash, source_addr, interaction_filter)
    
def fetch_interactions_etherscan(tx_hash):
    params = {
        "module": "proxy",
        "action": "eth_getTransactionReceipt",
        "txhash": tx_hash,
        "apikey": ETHERSCAN_API_KEY
    }
    
    try:
        limiter.wait()
        response = session.get(ETHERSCAN_URL, params=params, timeout=30)
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
    contract_graph.add_node(contract, name=name, label=name, discovery_methods=["seed"])


@lru_cache(maxsize=100000)
def _is_eoa_cached(cs: str) -> bool:
    try:
        return (not w3.eth.get_code(cs)) and (cs not in BLACKLIST)
    except Exception as e:
        logging.warning(f"EOA check failed for {cs[:10]}...: {e}")
        return True

def is_eoa(address: str) -> bool:
    try:
        return _is_eoa_cached(Web3.to_checksum_address(address))
    except Exception:
        return True

processed_deployers = set()

def deployer_discovery_pass(contracts_to_check, blacklist, contract_graph, discovered_contracts, untraced_contracts, label="deployer"):
    global processed_deployers
    new_contracts = set()
    
    for contract in contracts_to_check:
        try:
            if not Web3.is_address(contract) or Web3.to_checksum_address(contract) in blacklist:
                continue

            name = fetch_contract_name(contract)
            if should_skip_by_name(contract, name):
                logging.info(f"[{label}] Skipping by name blacklist: {name} ({contract})")
                continue
                
            creator = get_contract_creator(contract)
            if not creator:
                logging.info(f"[{label}] Could not find creator for contract {contract[:8]}...")
                continue
            
            checksum_contract = Web3.to_checksum_address(contract)
            if checksum_contract not in contract_name_cache:
                contract_name_cache[checksum_contract] = {
                    'name': fetch_contract_name(contract),
                    'deployer': creator
                }
            else:
                contract_name_cache[checksum_contract]['deployer'] = creator
                
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

    for target in targets:
        if is_eoa(target):
            continue

        name = fetch_contract_name(target)
        if should_skip_by_name(target, name):
            logging.info(f"Skipping by name blacklist: {name} ({target})")
            continue

        if target in processed_contracts or target in depth_queues.get(current_depth + 1, set()):
            continue 

        target = Web3.to_checksum_address(target)
        if target not in discovered_contracts:
            discovered_contracts.add(target)
            if target not in contract_graph:
                name = fetch_contract_name(target)
                contract_graph.add_node(
                    target,
                    name=name,
                    label=name if name.strip() else short_addr(target),
                    discovery_methods=["interaction"]
                )
            else:
                current_methods = contract_graph.nodes[target].get('discovery_methods', [])
                if "interaction" not in current_methods:
                    current_methods.append("interaction")
                    contract_graph.nodes[target]['discovery_methods'] = current_methods
                    
        if not any(target in q for q in depth_queues.values()):
            if current_depth + 1 not in depth_queues:
                depth_queues[current_depth + 1] = set()
            depth_queues[current_depth + 1].add(target)
        if contract_graph.has_edge(source, target):
            contract_graph[source][target]["weight"] += 1
        else:
            contract_graph.add_edge(source, target, weight=1)

processed_contracts = set()

def get_transaction_receipt(tx_hash: str) -> Dict:
    """Get transaction receipt"""
    params = {
        "module": "proxy",
        "action": "eth_getTransactionReceipt",
        "txhash": tx_hash,
        "apikey": ETHERSCAN_API_KEY
    }
    
    try:
        limiter.wait()
        response = session.get(ETHERSCAN_URL, params=params, timeout=30)
        response.raise_for_status()
        return response.json().get("result", {})
    except Exception as e:
        logging.warning(f"Failed to get receipt for {tx_hash}: {e}")
        return {}

def process_contract(contract: str, current_depth: int, depth_queues: Dict[int, Set[str]], interaction_filter: InteractionFilter = None):
    if contract in processed_contracts:
        logging.info(f"Skipping already-processed contract: {contract[:8]}...")
        return
    
    name = fetch_contract_name(contract)
    if should_skip_by_name(contract, name):
        logging.info(f"Skipping by name blacklist: {name} ({contract})")
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
                receipt_data = get_transaction_receipt(tx) if config.get('strict_interaction_mode', False) else None

                targets = simulate_and_extract(tx, source_addr=contract, tx_data=receipt_data, interaction_filter=interaction_filter)
                if not targets:
                    continue
                
                logging.info(f"  -Transaction: {tx}... ({len(targets)} interactions)")
                update_graph(contract, targets, current_depth, depth_queues)
                
            except Exception as e:
                logging.error(f"Error processing tx {tx}...: {str(e)}")
                continue
                
    except Exception as e:
        logging.error(f"Failed to process contract {contract}: {str(e)}")


def rank_contracts(graph, addresses=None, top_n=10):    
    if addresses is not None:
        subgraph = graph.subgraph(addresses).copy()
    else:
        subgraph = graph

    pr = nx.pagerank(subgraph, weight='weight')  
    ranked = sorted(pr.items(), key=lambda x: x[1], reverse=True)
    
    logging.info(f"\nTop {top_n} Critical Contracts:")
    for i, (contract, score) in enumerate(ranked[:top_n], 1):
        name = display_label(contract)
        methods = graph.nodes[contract].get('discovery_methods', ['unknown'])
        method_str = ", ".join(methods)
        logging.info(f"{i}. {name} ({contract}...): {score:.6f} [via {method_str}]")
    
    return ranked

def cleanup():
    """Close the session to free resources"""
    global session
    if session:
        session.close()

def main():
    global contract_graph, discovered_contracts, untraced_contracts

    args = parse_args()
    if args.strict_interactions:
        config['strict_interaction_mode'] = True
    # Output directory setup
    output_dir = os.path.dirname(__file__)

    # Testing limitations
    test_mode_limit = 10

    # Initialize interaction filter
    interaction_filter = InteractionFilter(config)

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
        creation_date = fetch_and_store_creation_date(contract)
        contract_graph.add_node(
            contract, 
            name=name,
            label=name if name.strip() else short_addr(contract),
            discovery_methods=["seed"],
            creation_date=creation_date
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
            if is_eoa(contract):
                continue

            process_contract(contract, current_depth, depth_queues, interaction_filter)
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
        
        # if current_depth == 1:
        #     logging.info("\n=== Deployer Discovery Pass (POST-CRAWL) ===")
        #     # Get contracts discovered through interactions only
        #     interaction_discovered = [
        #         c for c in discovered_contracts 
        #         if contract_graph.nodes[c].get('discovery_method') not in ["seed", "deployer_pre"]
        #     ]
        #     deployer_discovery_pass(
        #         contracts_to_check=interaction_discovered,
        #         blacklist=BLACKLIST,
        #         contract_graph=contract_graph,
        #         discovered_contracts=discovered_contracts,
        #         untraced_contracts=untraced_contracts,
        #         label="deployer_post"
        #     )
    
    logging.info("\n=== Batch Fetching Contract Creation Dates ===")
    # Process in batches to avoid overwhelming the API
    batch_size = 5
    all_contracts = list(discovered_contracts)
    creation_dates = {}

    for i in range(0, len(all_contracts), batch_size):
        batch = all_contracts[i:i + batch_size]
        batch_dates = fetch_and_store_creation_date_batch(batch)
        creation_dates.update(batch_dates)
        
        # Update graph with the fetched dates
        for contract, date in batch_dates.items():
            if contract in contract_graph:
                contract_graph.nodes[contract]['creation_date'] = date

    logging.info(f"Fetched creation dates for {len(creation_dates)} contracts")

    # Redundant

    # logging.info("\n=== Batch Fetching Contract Deployers ===")
    # # Collect contracts that need deployer information
    # contracts_needing_deployers = []
    # for contract in discovered_contracts:
    #     if 'deployer' not in contract_graph.nodes[contract] or contract_graph.nodes[contract].get('deployer') is None:
    #         contracts_needing_deployers.append(contract)

    # if contracts_needing_deployers:
    #     logging.info(f"Fetching deployers for {len(contracts_needing_deployers)} contracts")
        
    #     # Process in batches
    #     batch_size = 5
    #     all_deployers = {}
        
    #     for i in range(0, len(contracts_needing_deployers), batch_size):
    #         batch = contracts_needing_deployers[i:i + batch_size]
    #         batch_deployers = fetch_and_store_deployer_batch(batch)
    #         all_deployers.update(batch_deployers)
            
    #         # Update graph with the fetched deployers
    #         for contract, deployer in batch_deployers.items():
    #             if contract in contract_graph:
    #                 contract_graph.nodes[contract]['deployer'] = deployer
            
    #         # logging.info(f"Processed batch {i//batch_size + 1}/{(len(contracts_needing_deployers)-1)//batch_size + 1}")
        
    #     logging.info(f"Fetched deployers for {len(all_deployers)} contracts")
    # else:
    #     logging.info("All contracts already have deployer information")

    logging.info("\n=== Discovery Comparison ===")

    try:
        with open(DISCOVERED_CONTRACTS_FILE, 'r') as f:
            previous_discovered = set(json.load(f))
        logging.info(f"Loaded {len(previous_discovered)} contracts from previous run")
    except (FileNotFoundError, json.JSONDecodeError):
        previous_discovered = set()
        logging.info("No previous discovery file found or invalid format")

    # if config.get('verbose_diff', False):
        # Create temporary files for the enhanced comparison display
    temp_prev_file = os.path.join(SAVE_DIR, "temp_previous.json")
    temp_curr_file = os.path.join(SAVE_DIR, "temp_current.json")
        
    with open(temp_prev_file, 'w') as f:
        json.dump(sorted(previous_discovered), f)
    with open(temp_curr_file, 'w') as f:
        json.dump(sorted(discovered_contracts), f)
    logging.info("Comparing previous and current contract discoveries:")
    output_buffer = io.StringIO()

    with redirect_stdout(output_buffer):
        compare_contract_files(
            temp_prev_file, 
            temp_curr_file,
            contract_cache=contract_name_cache,
            verbose=True,
            output_diff=False
        )
    captured_output = output_buffer.getvalue()
    for line in captured_output.split('\n'):
        if line.strip():
            logging.info(line)
        
        # Clean up temp files
    try:
        os.remove(temp_prev_file)
        os.remove(temp_curr_file)
    except:
        pass

    # Final output and analysis
    graph_path = os.path.join(output_dir, "contract_graph.gexf")
    simplified_graph = contract_graph.copy()
    
    for node in simplified_graph.nodes():
        if 'discovery_methods' in simplified_graph.nodes[node]:
            methods = simplified_graph.nodes[node]['discovery_methods']
            if isinstance(methods, list):
                simplified_graph.nodes[node]['discovery_methods'] = ', '.join(methods)
            for attr_key, attr_value in list(simplified_graph.nodes[node].items()):
                if isinstance(attr_value, (list, dict, set)):
                    simplified_graph.nodes[node][attr_key] = str(attr_value)
                elif attr_value is None:
                    simplified_graph.nodes[node][attr_key] = ""

        # methods = contract_graph.nodes[node].get('discovery_methods', [])
        # if methods:
        #     contract_graph.nodes[node]['discovery_methods_str'] = ', '.join(methods)
        # elif 'discovery_method' in contract_graph.nodes[node]:
        #     old_method = contract_graph.nodes[node].get('discovery_method')
        #     if old_method:
        #         contract_graph.nodes[node]['discovery_methods_str'] = old_method
        #         contract_graph.nodes[node]['discovery_methods'] = [old_method]
    nx.write_gexf(simplified_graph, graph_path)

    logging.info("\n=== Bytecode Hash Deduplication ===")

    unique_by_hash, duplicates_by_hash = deduplicate_by_bytecode(discovered_contracts)
    canonical_addrs = set(unique_by_hash.values())

    total_duplicates = sum(len(dupes) for dupes in duplicates_by_hash.values())
    logging.info(f"Unique contracts (by bytecode): {len(canonical_addrs)}")
    logging.info(f"Duplicates collapsed: {total_duplicates}")

    logging.info("\n=== Ranking (Deduplicated) ===")
    ranked_contracts = rank_contracts(contract_graph, canonical_addrs)

    # save_discovered_contracts(discovered_contracts)
    # ranked_contracts = rank_contracts(contract_graph)

    logging.info("\n=== Summary ===")
    logging.info(f"Total contracts discovered: {len(discovered_contracts)}")
    logging.info(f"Graph size: {len(contract_graph.nodes())} nodes, {len(contract_graph.edges())} edges")

    # Show discovery method breakdown
    methods_count = {}
    for node in contract_graph.nodes():
        methods = contract_graph.nodes[node].get('discovery_methods', ['unknown'])
        for method in methods:
            methods_count[method] = methods_count.get(method, 0) + 1

    logging.info("\nDiscovery Methods:")
    for method, count in sorted(methods_count.items()):
        logging.info(f"  {method}: {count} contracts")
    
    multi_method_count = sum(1 for node in contract_graph.nodes() if len(contract_graph.nodes[node].get('discovery_methods', [])) > 1)
    logging.info(f"Contracts discovered via multiple methods: {multi_method_count}")

    save_discovered_contracts(discovered_contracts, contract_graph, ranked_contracts)

    display_newest_contracts(contract_graph)

if __name__ == '__main__':
    try:
        main()
    finally:
        cleanup()
