#!/usr/bin/env python3
"""CLI interface for Squads Multisig Verifier."""

import json
import sys
from datetime import datetime
from typing import Optional

import click

from .verifier import (
    verify_program,
    verify_multisig_direct,
    get_rpc_endpoint,
)
from .formatters import (
    format_table,
    format_json,
    format_markdown,
    format_compact,
    format_multisig_table,
    format_multisig_json,
    format_batch_summary,
)
from .types import BatchVerificationResult


# Well-known Solana DeFi programs
KNOWN_PROGRAMS = [
    {"program_id": "KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD", "name": "Klend (Kamino Lend)"},
    {"program_id": "dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH", "name": "Drift Protocol"},
    {"program_id": "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4", "name": "Jupiter v6"},
    {"program_id": "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc", "name": "Orca Whirlpools"},
    {"program_id": "MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FZnsebVacA", "name": "Marginfi"},
    {"program_id": "So1endDq2YkqhipRh3WViPa8hdiSpxWy6z3Z6tMCpAo", "name": "Solend"},
    {"program_id": "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK", "name": "Raydium CLMM"},
    {"program_id": "PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY", "name": "Phoenix"},
]


def mask_api_key(url: str) -> str:
    """Mask API key in URL for display."""
    if "api-key=" in url:
        return url.split("api-key=")[0] + "api-key=***"
    return url


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """Verify Squads multisig configuration for Solana programs."""
    pass


@cli.command()
@click.argument("program_id")
@click.option("-n", "--name", help="Program name for display")
@click.option("-r", "--rpc", help="RPC endpoint URL")
@click.option(
    "-f", "--format",
    type=click.Choice(["table", "json", "markdown", "compact"]),
    default="table",
    help="Output format"
)
@click.option("-o", "--output", type=click.Path(), help="Write output to file")
def program(program_id: str, name: Optional[str], rpc: Optional[str], format: str, output: Optional[str]):
    """Verify multisig configuration for a program by its program ID."""
    endpoint = rpc or get_rpc_endpoint()

    click.echo(f"Verifying program: {program_id}", err=True)
    click.echo(f"Using RPC: {mask_api_key(endpoint)}", err=True)
    click.echo("", err=True)

    result = verify_program(program_id, name, endpoint)

    # Format output
    if format == "json":
        output_text = format_json(result)
    elif format == "markdown":
        output_text = format_markdown(result)
    elif format == "compact":
        output_text = format_compact(result)
    else:
        output_text = format_table(result)

    if output:
        with open(output, "w") as f:
            f.write(output_text)
        click.echo(f"Output written to: {output}", err=True)
    else:
        click.echo(output_text)

    if result.error:
        sys.exit(1)


@cli.command()
@click.argument("address")
@click.option("-r", "--rpc", help="RPC endpoint URL")
@click.option(
    "-f", "--format",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format"
)
@click.option("-o", "--output", type=click.Path(), help="Write output to file")
def multisig(address: str, rpc: Optional[str], format: str, output: Optional[str]):
    """Analyze a Squads multisig account directly by address."""
    endpoint = rpc or get_rpc_endpoint()

    click.echo(f"Analyzing multisig: {address}", err=True)
    click.echo(f"Using RPC: {mask_api_key(endpoint)}", err=True)
    click.echo("", err=True)

    try:
        result = verify_multisig_direct(address, endpoint)

        if format == "json":
            output_text = format_multisig_json(result)
        else:
            output_text = format_multisig_table(result)

        if output:
            with open(output, "w") as f:
                f.write(output_text)
            click.echo(f"Output written to: {output}", err=True)
        else:
            click.echo(output_text)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("-r", "--rpc", help="RPC endpoint URL")
@click.option(
    "-f", "--format",
    type=click.Choice(["summary", "json", "markdown"]),
    default="summary",
    help="Output format"
)
@click.option("-o", "--output", type=click.Path(), help="Write output to file")
def batch(file: str, rpc: Optional[str], format: str, output: Optional[str]):
    """Verify multiple programs from a JSON file."""
    endpoint = rpc or get_rpc_endpoint()

    click.echo(f"Reading programs from: {file}", err=True)
    click.echo(f"Using RPC: {mask_api_key(endpoint)}", err=True)
    click.echo("", err=True)

    with open(file) as f:
        programs = json.load(f)

    results = []
    with_timelock = 0
    without_timelock = 0
    failed = 0

    for prog in programs:
        prog_id = prog.get("program_id") or prog.get("programId")
        prog_name = prog.get("name")

        click.echo(f"Verifying: {prog_name or prog_id}...", err=True)
        result = verify_program(prog_id, prog_name, endpoint)
        results.append(result)

        if result.error:
            failed += 1
        elif result.multisig:
            if result.multisig.time_lock_seconds > 0:
                with_timelock += 1
            else:
                without_timelock += 1

    batch_result = BatchVerificationResult(
        results=results,
        summary={
            "total": len(programs),
            "successful": len(programs) - failed,
            "failed": failed,
            "with_timelock": with_timelock,
            "without_timelock": without_timelock,
        },
        timestamp=datetime.utcnow().isoformat() + "Z",
    )

    if format == "json":
        def to_dict(obj):
            if hasattr(obj, "__dataclass_fields__"):
                return {k: to_dict(v) for k, v in obj.__dict__.items()}
            elif isinstance(obj, list):
                return [to_dict(item) for item in obj]
            else:
                return obj
        output_text = json.dumps(to_dict(batch_result), indent=2)
    elif format == "markdown":
        output_text = "\n\n---\n\n".join(format_markdown(r) for r in results)
    else:
        output_text = format_batch_summary(batch_result)

    if output:
        with open(output, "w") as f:
            f.write(output_text)
        click.echo(f"\nOutput written to: {output}", err=True)
    else:
        click.echo(output_text)


@cli.command("list-known")
def list_known():
    """List well-known Solana DeFi programs."""
    click.echo("Well-known Solana DeFi Programs:")
    click.echo("─" * 70)
    click.echo("Name".ljust(25) + "Program ID")
    click.echo("─" * 70)

    for p in KNOWN_PROGRAMS:
        click.echo(f"{p['name'].ljust(25)}{p['program_id']}")

    click.echo("─" * 70)
    click.echo("")
    click.echo("To verify a program:")
    click.echo("  python -m squads_verifier program <programId> --name <name>")


def main():
    cli()


if __name__ == "__main__":
    main()
