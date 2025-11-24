#!/usr/bin/env python3
"""
TRR Scripts - Unified CLI Tool
A swiss army knife for smart contract analysis
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def main():
    parser = argparse.ArgumentParser(
        prog="trr",
        description="TRR Scripts - Smart contract analysis toolkit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  trr download eth contracts.txt
  trr analyze contracts.txt
  trr summary contracts.txt --tsv
  trr tvl dolomite 2022-12-18 2025-02-28 --format csv
  trr deployments eth contracts.txt
  trr scan --strict-interactions
  trr compare file1.json file2.json --verbose
  trr tdp contract1.sol contract2.sol
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands", metavar="COMMAND")

    # Download command
    download_parser = subparsers.add_parser(
        "download",
        help="Download contracts from Etherscan/Arbiscan",
        description="Download verified smart contracts from block explorers",
    )
    download_parser.add_argument(
        "network", choices=["eth", "arb"], help="Network (eth=Ethereum, arb=Arbitrum)"
    )
    download_parser.add_argument(
        "addresses_file", help="File containing contract addresses (one per line)"
    )

    # Analyze command
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze contracts using Slither",
        description="Analyze downloaded contracts and generate code.json files",
    )
    analyze_parser.add_argument(
        "addresses_file", help="File containing contract addresses (one per line)"
    )

    # Summary command
    summary_parser = subparsers.add_parser(
        "summary",
        help="Aggregate and summarize contract metrics",
        description="Merge and summarize code.json files across contracts",
    )
    summary_parser.add_argument(
        "addresses_file", help="File containing contract addresses (one per line)"
    )
    summary_parser.add_argument(
        "--tsv", action="store_true", help="Output summary as TSV instead of JSON"
    )

    # TVL command
    tvl_parser = subparsers.add_parser(
        "tvl",
        help="Calculate TVL data for DeFi protocols",
        description="Fetch and calculate TVL data with optional interpolation",
    )
    tvl_parser.add_argument("protocol", help="Protocol name (as listed on DeFiLlama)")
    tvl_parser.add_argument("start_date", help="Start date in YYYY-MM-DD format (UTC)")
    tvl_parser.add_argument("end_date", help="End date in YYYY-MM-DD format (UTC)")
    tvl_parser.add_argument(
        "--format", choices=["csv", "json"], default="csv", help="Output format (default: csv)"
    )
    tvl_parser.add_argument(
        "--mean", action="store_true", help="Output only the average TVL (backward compatibility)"
    )

    # Deployments command
    deployments_parser = subparsers.add_parser(
        "deployments",
        help="Fetch contract deployment dates",
        description="Get deployment timestamps for contracts from block explorers",
    )
    deployments_parser.add_argument(
        "network", choices=["eth", "arb"], help="Network (eth=Ethereum, arb=Arbitrum)"
    )
    deployments_parser.add_argument(
        "addresses_file", help="File containing contract addresses (one per line)"
    )

    # Scan command
    scan_parser = subparsers.add_parser(
        "scan",
        help="Contract discovery and relationship mapping",
        description="Discover related contracts and build relationship graphs",
    )
    scan_parser.add_argument(
        "--previous", type=str, help="Path to previous discovered contracts file for comparison"
    )
    scan_parser.add_argument(
        "--strict-interactions",
        action="store_true",
        help="Enable strict trace-based interaction filtering",
    )

    # Compare command
    compare_parser = subparsers.add_parser(
        "compare",
        help="Compare contract discovery results",
        description="Compare two contract discovery files and show differences",
    )
    compare_parser.add_argument("file1", help="First contract file (JSON)")
    compare_parser.add_argument("file2", help="Second contract file (JSON)")
    compare_parser.add_argument("--verbose", action="store_true", help="Show sample addresses")
    compare_parser.add_argument("--output", action="store_true", help="Save full diff files")

    # TDP command
    tdp_parser = subparsers.add_parser(
        "tdp",
        help="Calculate Total Decision Points",
        description="Count decision points (if, for, require, etc.) in Solidity/Vyper files",
    )
    tdp_parser.add_argument("files", nargs="+", help="Solidity or Vyper files to analyze")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)  # noqa: F823

    # Route to appropriate command handler with lazy imports
    try:
        if args.command == "download":
            from download_contracts import main as download_main

            # Convert argparse args to function call
            sys.argv = ["download_contracts.py", args.network, args.addresses_file]
            download_main()

        elif args.command == "analyze":
            from codes import main as analyze_main

            sys.argv = ["codes.py", args.addresses_file]
            analyze_main(args.addresses_file)

        elif args.command == "summary":
            import json

            from summary import aggregate_by_hash, merge_code_outputs, output_tsv_from_aggregated

            with open(args.addresses_file) as f:
                contract_dirs = [line.strip() for line in f if line.strip()]

            merged_summary = merge_code_outputs(contract_dirs)
            aggregated = aggregate_by_hash(merged_summary, contract_dirs)

            if args.tsv:
                output_tsv_from_aggregated(aggregated)
            else:
                print(json.dumps(aggregated, indent=2))

        elif args.command == "tvl":
            import json

            from avg_tvls import get_average_tvl, get_tvl_dataset

            if args.mean:
                avg_tvl = get_average_tvl(args.protocol, args.start_date, args.end_date)
                print(
                    f"Average TVL for {args.protocol} from {args.start_date} to {args.end_date}: ${avg_tvl:,.2f}"
                )
            else:
                dataset = get_tvl_dataset(args.protocol, args.start_date, args.end_date)

                if args.format == "json":
                    output = json.dumps(dataset, indent=2)
                    print(output)
                else:
                    print("date,tvl,is_interpolated")
                    for row in dataset:
                        print(
                            f"{row['date']},{row['tvl']:.2f},{str(row['is_interpolated']).lower()}"
                        )

        elif args.command == "deployments":
            # Call the bash script or implement Python version
            import subprocess

            script_path = Path(__file__).parent / "deployment_dates.sh"

            if not script_path.exists():
                print(f"Error: deployment_dates.sh not found at {script_path}", file=sys.stderr)
                sys.exit(1)

            # Make sure script is executable
            os.chmod(script_path, 0o755)

            result = subprocess.run(
                [str(script_path), args.network, args.addresses_file], check=False
            )
            sys.exit(result.returncode)

        elif args.command == "scan":
            # Change to scanner directory for scanner.py to work correctly
            scanner_path = Path(__file__).parent / "scanner" / "scanner.py"
            if not scanner_path.exists():
                print(f"Error: scanner.py not found at {scanner_path}", file=sys.stderr)
                sys.exit(1)

            # Import and run scanner
            import sys

            original_argv = sys.argv.copy()
            sys.argv = ["scanner.py"]
            if args.previous:
                sys.argv.extend(["--previous", args.previous])
            if args.strict_interactions:
                sys.argv.append("--strict-interactions")

            # Change to scanner directory
            original_cwd = os.getcwd()
            os.chdir(scanner_path.parent)

            try:
                # Import and run
                import importlib.util

                spec = importlib.util.spec_from_file_location("scanner", scanner_path)
                scanner_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(scanner_module)
                scanner_module.main()
            finally:
                os.chdir(original_cwd)
                sys.argv = original_argv

        elif args.command == "compare":
            from scanner.compare_contracts import compare_contract_files

            compare_contract_files(
                args.file1, args.file2, verbose=args.verbose, output_diff=args.output
            )

        elif args.command == "tdp":
            import json

            from tdp import compute_tdp_from_file

            file_results = {}
            total_tdp_unique = 0
            total_tdp_all = 0
            seen_hashes = {}
            import hashlib

            for file_path in args.files:
                try:
                    file_path_obj = Path(file_path)
                    if not file_path_obj.exists():
                        file_results[file_path] = "Error: File not found"
                        continue

                    tdp = compute_tdp_from_file(str(file_path_obj))
                    file_results[file_path] = tdp
                    total_tdp_all += tdp

                    # Calculate hash for uniqueness check
                    with open(file_path_obj) as f:
                        lines = f.read().splitlines()
                    from tdp import remove_comments

                    file_type = (
                        "sol"
                        if file_path.endswith(".sol")
                        else "vy"
                        if file_path.endswith(".vy")
                        else None
                    )
                    if file_type:
                        cleaned_lines = remove_comments(lines, file_type)
                        file_hash = hashlib.md5("\n".join(cleaned_lines).encode()).hexdigest()
                        if file_hash not in seen_hashes:
                            seen_hashes[file_hash] = tdp
                            total_tdp_unique += tdp

                except Exception as e:
                    file_results[file_path] = f"Error: {e}"

            file_results["Total (Unique)"] = total_tdp_unique
            file_results["Total (All)"] = total_tdp_all
            print(json.dumps(file_results, indent=4))

    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
