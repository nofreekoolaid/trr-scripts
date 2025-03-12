#!/usr/bin/env bash

set -e

# Chain selection (default: Ethereum)
CHAIN="${1:-eth}"

# Determine the correct API base URL and API key
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
  echo "❌ ERROR: Unsupported chain '$CHAIN'. Use 'eth' for Ethereum or 'arb' for Arbitrum."
  exit 1
  ;;
esac

# Throw an error if the selected API key is not set
if [[ -z "$API_KEY" ]]; then
  echo "❌ ERROR: Please set API_KEY environment variable before running the script."
  exit 1
fi

# List of contract addresses to check
addresses=(
  "0x0000000022D53366457F9d5E68Ec105046FC4383"
  "0xd533a949740bb3306d119cc777fa900ba034cd52"
  "0x5f3b5dfeb7b28cdbd7faba78963ee202a494e2a2"
  "0x6A8cbed756804B16E05E741eDaBd5cB544AE21bf"
  "0x98EE851a00abeE0d95D08cF4CA2BdCE32aeaAF7F"
  "0x0c0e5f2fF0ff18a3be9b835635039256dC4B4963"
  "0x6c3f90f043a72fa612cbac8115ee7e52bde6e490"
  "0xc2cb1040220768554cf699b0d863a3cd4324ce32"
  "0x8e595470ed749b85c6f7669de83eae304c2ec68f"
  "0xd1b5651e55d4ceed36251c61c50c889b36f6abb5"
  "0x95dfdc8161832e4ff7816ac4b6367ce201538253"
  "0x14139EB676342b6bC8E41E0d419969f23A49881e"
  "0xa464e6dcda8ac41e03616f95f4bc98a13b8922dc"
  "0x2F50D538606Fa9EDD2B11E2446BEb18C9D5846bB"
  "0xd061D61a4d941c39E5453435B6345Dc261C2fcE0"
)

lookup_deployment_info() {
  local address="$1"

  # Fetch contract name
  name_response=$(curl -s "$API_BASE_URL?module=contract&action=getsourcecode&address=$address&apikey=$API_KEY")
  contract_name=$(echo "$name_response" | jq -r '.result[0].ContractName')

  if [[ "$contract_name" == "null" || -z "$contract_name" ]]; then
    contract_name="Unknown Contract"
  fi

  # Fetch contract creation transaction (first tx)
  tx_response=$(curl -s "$API_BASE_URL?module=account&action=txlist&address=$address&startblock=0&endblock=99999999&sort=asc&apikey=$API_KEY")

  # Extract timestamp of first transaction
  timestamp=$(echo "$tx_response" | jq -r '.result[0].timeStamp')

  if [[ "$timestamp" == "null" || -z "$timestamp" ]]; then
    echo "❌ Failed to retrieve deployment date for $contract_name ($address) on $CHAIN"
  else
    deployment_date=$(date -d @"$timestamp" +"%Y-%m-%d %H:%M:%S UTC") # Convert timestamp to readable date
    echo "✅ Contract: $contract_name ($address) was deployed on $deployment_date on $CHAIN"
  fi
}

echo "🔍 Looking up deployment dates for contracts on $CHAIN..."

for address in "${addresses[@]}"; do
  lookup_deployment_info "$address"
done
