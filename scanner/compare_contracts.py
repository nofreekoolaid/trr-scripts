#!/usr/bin/env python3
import json
from typing import Set, Dict, List
from web3 import Web3
import argparse

def compare_contract_files(file1: str, file2: str, verbose: bool = False, output_diff: bool = False):
    def load_contracts(file_path: str) -> Set[str]:
        try:
            with open(file_path, 'r') as f:
                return {Web3.to_checksum_address(addr) for addr in json.load(f)}
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error loading {file_path}: {str(e)}")
            return set()

    contracts1 = load_contracts(file1)
    contracts2 = load_contracts(file2)

    print(f"Comparison between {file1} and {file2}:")
    print(f"Total in {file1}: {len(contracts1)}")
    print(f"Total in {file2}: {len(contracts2)}")
    
    unique_to_file1 = contracts1 - contracts2
    unique_to_file2 = contracts2 - contracts1
    
    print(f"Contracts only in {file1}: {len(unique_to_file1)}")
    print(f"Contracts only in {file2}: {len(unique_to_file2)}")
    
    if verbose:
        print("Sample differences (max 20 each):")
        print(f"Unique to {file1}:")
        for i, addr in enumerate(sorted(unique_to_file1)[:20], 1):
            print(f"{i}. {addr}")
            
        print(f"Unique to {file2}:")
        for i, addr in enumerate(sorted(unique_to_file2)[:20], 1):
            print(f"{i}. {addr}")

    if output_diff:
        with open(f"diff_{file1}_unique.json", 'w') as f:
            json.dump(sorted(unique_to_file1), f, indent=2)
        with open(f"diff_{file2}_unique.json", 'w') as f:
            json.dump(sorted(unique_to_file2), f, indent=2)
        print("Saved full diffs to:")
        print(f"- diff_{file1}_unique.json")
        print(f"- diff_{file2}_unique.json")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Compare two contract discovery files')
    parser.add_argument('file1', help='First contract file (JSON)')
    parser.add_argument('file2', help='Second contract file (JSON)')
    parser.add_argument('--verbose', action='store_true', help='Show sample addresses')
    parser.add_argument('--output', action='store_true', help='Save full diff files')
    args = parser.parse_args()
    
    compare_contract_files(args.file1, args.file2, args.verbose, args.output)