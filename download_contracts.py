#!/usr/bin/env python3
import sys
import argparse
from download_contract import download_contract

def main():
    parser = argparse.ArgumentParser(
        description="Download multiple contracts from Ethereum or Arbitrum block explorers."
    )
    # Positional network argument (eth or arb)
    parser.add_argument("network", choices=["eth", "arb"], help="Network (eth=Ethereum, arb=Arbitrum)")
    # Positional file argument with contract addresses (one per line)
    parser.add_argument("filename", help="File containing contract addresses (one per line)")
    args = parser.parse_args()

    try:
        with open(args.filename, "r") as f:
            # Read each non-empty line, stripping whitespace
            addresses = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Error: File '{args.filename}' not found.")
        sys.exit(1)

    for address in addresses:
        print(f"\n📥 Downloading contract: {address} from {args.network.upper()}...")
        download_contract(address, args.network)

if __name__ == "__main__":
    main()
