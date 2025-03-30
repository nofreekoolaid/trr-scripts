#!/usr/bin/env bash

set -euo pipefail

# Usage: ./script.sh [chain] [file]
# Example: ./script.sh eth addresses.txt

# Default chain is Ethereum
CHAIN="${1:-eth}"
INPUT_FILE="${2:-}"

# Check if input file is provided and exists
if [[ -z "$INPUT_FILE" || ! -f "$INPUT_FILE" ]]; then
  echo "❌ ERROR: Please provide a valid input file containing contract addresses (one per line)."
  echo "Usage: $0 [eth|arb] contracts.txt"
  exit 1
fi

# Set API base URL and key based on chain
case "$CHAIN" in
eth)
  API_BASE_URL="https://api.etherscan.io/api"
  API_KEY="${ETHERSCAN_API_KEY:-}"
  ;;
arb)
  API_BASE_URL="https://api.arbiscan.io/api"
  API_KEY="${ARBISCAN_API_KEY:-}"
  ;;
*)
  echo "❌ ERROR: Unsupported chain '$CHAIN'. Use 'eth' or 'arb'."
  exit 1
  ;;
esac

# Check API key
if [[ -z "$API_KEY" ]]; then
  echo "❌ ERROR: Please set the appropriate API key environment variable (ETHERSCAN_API_KEY or ARBISCAN_API_KEY)."
  exit 1
fi

lookup_deployment_info() {
  local address="$1"

  # Fetch contract name
  name_response=$(curl -s "$API_BASE_URL?module=contract&action=getsourcecode&address=$address&apikey=$API_KEY")
  contract_name=$(echo "$name_response" | jq -r '.result[0].ContractName')
  [[ "$contract_name" == "null" || -z "$contract_name" ]] && contract_name="Unknown Contract"

  # Use getcontractcreation endpoint (works for CREATE2/factory contracts)
  creation_response=$(curl -s "$API_BASE_URL?module=contract&action=getcontractcreation&contractaddresses=$address&apikey=$API_KEY")
  creation_tx=$(echo "$creation_response" | jq -r '.result[0].txHash')

  if [[ -z "$creation_tx" || "$creation_tx" == "null" ]]; then
    echo "❌ Could not find creation transaction for $contract_name ($address)"
    return
  fi

  # Use the tx hash to get the timestamp
  tx_info=$(curl -s "$API_BASE_URL?module=proxy&action=eth_getTransactionByHash&txhash=$creation_tx&apikey=$API_KEY")
  block_number=$(echo "$tx_info" | jq -r '.result.blockNumber')
  [[ "$block_number" == "null" || -z "$block_number" ]] && {
    echo "❌ Could not fetch block number for creation tx of $contract_name ($address)"
    return
  }

  # Get block timestamp
  block_info=$(curl -s "$API_BASE_URL?module=proxy&action=eth_getBlockByNumber&tag=$block_number&boolean=true&apikey=$API_KEY")
  timestamp_hex=$(echo "$block_info" | jq -r '.result.timestamp')
  timestamp=$((16#${timestamp_hex:2}))

  deployment_date=$(date -u -d @"$timestamp" +"%Y-%m-%dT%H:%M:%SZ")
  echo "✅ Contract: $contract_name ($address) was deployed on $deployment_date (UTC) on $CHAIN"
}

echo "🔍 Looking up deployment dates for contracts on $CHAIN..."

while read -r address; do
  [[ -z "$address" ]] && continue
  lookup_deployment_info "$address"
done <"$INPUT_FILE"
