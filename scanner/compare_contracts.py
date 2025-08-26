#!/usr/bin/env python3
import json
import os
from typing import Set, Dict, List
from web3 import Web3
import argparse

def short_addr(addr: str) -> str:
    c = Web3.to_checksum_address(addr)
    return c[:6] + "..." + c[-4:]

def compare_contract_files(file1: str, file2: str, contract_cache=None, verbose: bool = False, output_diff: bool = False):
    def load_contracts(file_path: str) -> Set[str]:
        try:
            with open(file_path, 'r') as f:
                return {Web3.to_checksum_address(addr) for addr in json.load(f)}
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error loading {file_path}: {str(e)}")
            return set()
        
    def get_contract_name_from_cache(address: str) -> str:
        if contract_cache:
            cached = contract_cache.get(Web3.to_checksum_address(address))
            if cached:
                if isinstance(cached, dict):
                    name = cached.get('name', '')
                    if name and name.strip():
                        return name
                elif isinstance(cached, str) and cached.strip():
                    return cached
        # Fallback to shortened address if no name found
        return short_addr(address)
        

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
            name = get_contract_name_from_cache(addr)
            print(f"{i}. {name}")
            
        print(f"Unique to {file2}:")
        for i, addr in enumerate(sorted(unique_to_file2)[:20], 1):
            name = get_contract_name_from_cache(addr)
            print(f"{i}. {name}")

    if output_diff:
        unique1_with_names = []
        for addr in sorted(unique_to_file1):
            name = get_contract_name_from_cache(addr)
            unique1_with_names.append({"address": addr, "name": name})

        unique2_with_names = []
        for addr in sorted(unique_to_file2):
            name = get_contract_name_from_cache(addr)
            unique2_with_names.append({"address": addr, "name": name})

        with open(f"diff_{os.path.basename(file1)}_unique.json", 'w') as f:
            json.dump(unique1_with_names, f, indent=2)
        with open(f"diff_{os.path.basename(file2)}_unique.json", 'w') as f:
            json.dump(unique2_with_names, f, indent=2)
        print(f"\nSaved full diffs to:")
        print(f"- diff_{os.path.basename(file1)}_unique.json")
        print(f"- diff_{os.path.basename(file2)}_unique.json")
    
    return {
        'unique_to_file1': unique_to_file1,
        'unique_to_file2': unique_to_file2,
        'common': contracts1 & contracts2
    }

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Compare two contract discovery files')
    parser.add_argument('file1', help='First contract file (JSON)')
    parser.add_argument('file2', help='Second contract file (JSON)')
    parser.add_argument('--verbose', action='store_true', help='Show sample addresses')
    parser.add_argument('--output', action='store_true', help='Save full diff files')
    args = parser.parse_args()
    
    compare_contract_files(args.file1, args.file2, args.verbose, args.output)