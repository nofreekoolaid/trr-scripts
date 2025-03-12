import os
import json
import requests
import argparse
import re

# API endpoints for different networks
ETHERSCAN_API_URLS = {
    "eth": "https://api.etherscan.io/api",
    "arb": "https://api.arbiscan.io/api"
}

# Load API key from environment
API_KEY = os.getenv("ETHERSCAN_API_KEY")
if not API_KEY:
    print("Error: ETHERSCAN_API_KEY is not set. Please set it as an environment variable.")
    exit(1)

def fetch_contract_source(address, network="eth"):
    """Fetch contract source code from Etherscan or Arbiscan."""
    api_url = ETHERSCAN_API_URLS.get(network)
    if not api_url:
        print(f"Error: Unsupported network '{network}'")
        return None

    params = {
        "module": "contract",
        "action": "getsourcecode",
        "address": address,
        "apikey": API_KEY
    }
    
    response = requests.get(api_url, params=params)
    if response.status_code != 200:
        print(f"Error fetching data for {address}: HTTP {response.status_code}")
        return None

    data = response.json()
    if data["status"] != "1" or not data["result"]:
        return None

    source_code = data["result"][0].get("SourceCode", "")
    return source_code

def extract_title(source_code):
    """Extract the @title annotation from the contract source code."""
    title_match = re.search(r'@title\s+(.+)', source_code)
    return title_match.group(1).strip() if title_match else "N/A"

def main(json_file, network):
    """Load contract addresses from a JSON file and fetch contract titles."""
    try:
        with open(json_file, "r") as f:
            contracts = json.load(f)
    except Exception as e:
        print(f"Error loading JSON file: {e}")
        return
    
    if not isinstance(contracts, dict):
        print("Error: JSON file must contain a dictionary of contract names and addresses.")
        return

    # Print input JSON
    print("\n### Input JSON (Contract Addresses) ###")
    print(json.dumps(contracts, indent=4))

    results = {}
    for name, address in contracts.items():
        print(f"\nFetching contract: {name} ({address}) ...")
        source_code = fetch_contract_source(address, network)
        contract_title = extract_title(source_code) if source_code else "N/A"
        
        results[name] = {
            "address": address,
            "contract_title": contract_title
        }
        
        print(f"{name} ({address}) -> {contract_title}")

    # Print output JSON
    print("\n### Output JSON (Extracted Titles) ###")
    output_json = json.dumps(results, indent=4)
    print(output_json)

    # Save results to a new JSON file
    output_file = "contract_titles_output.json"
    with open(output_file, "w") as f:
        f.write(output_json)

    print(f"\nResults saved to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch contract titles from Etherscan/Arbiscan.")
    parser.add_argument("json_file", help="Path to the JSON file containing contract addresses.")
    parser.add_argument("--network", choices=["eth", "arb"], default="eth", help="Network (eth=Ethereum, arb=Arbitrum)")
    
    args = parser.parse_args()
    main(args.json_file, args.network)
