## Deployer Discovery Feature

This tool includes a two-phase deployer discovery system that finds related contracts by:
1. Finding the deployer address of each seed contract
2. Discovering all contracts deployed by those deployers

### Usage

1. Configure `config.yaml`:
```yaml
seed_contracts:
  - "0x123..."              # Starting contract addresses
blacklist_contracts: []     # Addresses to exclude
num_transactions: 10        # Transactions to analyze per contract
max_depth: 1                # Crawl depth
etherscan_api_key: "YOUR_KEY"
tenderly_credentials:
  access_key: "YOUR_KEY"