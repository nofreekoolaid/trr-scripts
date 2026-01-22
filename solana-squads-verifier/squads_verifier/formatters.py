"""Output formatters for Squads Multisig Verifier."""

import json
from typing import Optional

from .types import (
    VerificationResult,
    MultisigInfo,
    BatchVerificationResult,
)


def format_table(result: VerificationResult) -> str:
    """Format a verification result as a table."""
    lines = []
    divider = "─" * 70

    lines.append(divider)
    name = result.program.program_name or result.program.program_id
    lines.append(f"PROGRAM: {name}")
    lines.append(divider)

    # Program Info
    lines.append("Program Information:")
    lines.append(f"  Program ID:         {result.program.program_id}")
    lines.append(f"  ProgramData:        {result.program.program_data_address}")
    lines.append(f"  Upgrade Authority:  {result.program.upgrade_authority or 'None (Immutable)'}")
    lines.append(f"  Is Upgradeable:     {'Yes' if result.program.is_upgradeable else 'No'}")

    if result.error:
        lines.append("")
        lines.append(f"⚠️  Error: {result.error}")
        lines.append(divider)
        return "\n".join(lines)

    # Vault Info
    if result.vault:
        lines.append("")
        lines.append("Vault Information:")
        lines.append(f"  Vault Address:      {result.vault.vault_address}")
        lines.append(f"  Parent Multisig:    {result.vault.parent_multisig or 'Not found'}")
        if result.vault.vault_index is not None:
            lines.append(f"  Vault Index:        {result.vault.vault_index}")

    # Multisig Info
    if result.multisig:
        lines.append("")
        lines.append("Multisig Configuration:")
        lines.append(f"  Multisig Address:   {result.multisig.address}")
        lines.append(f"  Threshold:          {result.multisig.threshold_display}")
        lines.append(f"  Timelock:           {result.multisig.time_lock_display}")
        lines.append(f"  Timelock (seconds): {result.multisig.time_lock_seconds}")
        lines.append(f"  Create Key:         {result.multisig.create_key}")
        if result.multisig.config_authority:
            lines.append(f"  Config Authority:   {result.multisig.config_authority}")

        lines.append("")
        lines.append("Members:")
        for member in result.multisig.members:
            lines.append(f"  {member.address}")
            lines.append(f"    Permissions: {', '.join(member.permissions)}")

    lines.append("")
    lines.append(f"Timestamp: {result.timestamp}")
    lines.append(divider)

    return "\n".join(lines)


def format_multisig_table(multisig: MultisigInfo) -> str:
    """Format a multisig analysis as a table."""
    lines = []
    divider = "─" * 70

    lines.append(divider)
    lines.append(f"MULTISIG: {multisig.address}")
    lines.append(divider)
    lines.append(f"Threshold:          {multisig.threshold_display}")
    lines.append(f"Timelock:           {multisig.time_lock_display}")
    lines.append(f"Timelock (seconds): {multisig.time_lock_seconds}")
    lines.append(f"Create Key:         {multisig.create_key}")
    if multisig.config_authority:
        lines.append(f"Config Authority:   {multisig.config_authority}")

    lines.append("")
    lines.append("Members:")
    for member in multisig.members:
        lines.append(f"  {member.address}")
        lines.append(f"    Permissions: {', '.join(member.permissions)}")

    lines.append(divider)

    return "\n".join(lines)


def format_markdown(result: VerificationResult) -> str:
    """Format a verification result as markdown."""
    lines = []

    name = result.program.program_name or result.program.program_id
    lines.append(f"# {name} - Multisig Verification")
    lines.append("")
    lines.append(f"**Verification Date:** {result.timestamp}")
    lines.append("")

    # Summary Box
    if result.multisig:
        has_timelock = result.multisig.time_lock_seconds > 0
        lines.append("## Summary")
        lines.append("")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Threshold | **{result.multisig.threshold_display}** |")
        lines.append(f"| Timelock | **{result.multisig.time_lock_display}** {'✅' if has_timelock else '⚠️'} |")
        lines.append(f"| Upgradeable | {'Yes' if result.program.is_upgradeable else 'No'} |")
        lines.append("")

    # Program Info
    lines.append("## Program Information")
    lines.append("")
    lines.append(f"- **Program ID:** `{result.program.program_id}`")
    lines.append(f"- **ProgramData Address:** `{result.program.program_data_address}`")
    lines.append(f"- **Upgrade Authority:** `{result.program.upgrade_authority or 'None (Immutable)'}`")
    lines.append("")

    if result.error:
        lines.append("## ⚠️ Error")
        lines.append("")
        lines.append(f"> {result.error}")
        lines.append("")
        return "\n".join(lines)

    # Vault Info
    if result.vault and result.vault.parent_multisig:
        lines.append("## Vault Information")
        lines.append("")
        lines.append(f"- **Vault Address:** `{result.vault.vault_address}`")
        lines.append(f"- **Parent Multisig:** `{result.vault.parent_multisig}`")
        if result.vault.vault_index is not None:
            lines.append(f"- **Vault Index:** {result.vault.vault_index}")
        lines.append("")

    # Multisig Details
    if result.multisig:
        lines.append("## Multisig Configuration")
        lines.append("")
        lines.append(f"- **Multisig Address:** `{result.multisig.address}`")
        lines.append(f"- **Threshold:** {result.multisig.threshold_display}")
        lines.append(f"- **Timelock:** {result.multisig.time_lock_display} ({result.multisig.time_lock_seconds} seconds)")
        lines.append(f"- **Create Key:** `{result.multisig.create_key}`")
        if result.multisig.config_authority:
            lines.append(f"- **Config Authority:** `{result.multisig.config_authority}`")
        lines.append("")

        lines.append("## Members")
        lines.append("")
        lines.append("| Address | Permissions |")
        lines.append("|---------|-------------|")
        for member in result.multisig.members:
            lines.append(f"| `{member.address}` | {', '.join(member.permissions)} |")
        lines.append("")

    return "\n".join(lines)


def format_json(result: VerificationResult, pretty: bool = True) -> str:
    """Format as JSON."""
    def to_dict(obj):
        if hasattr(obj, "__dataclass_fields__"):
            return {k: to_dict(v) for k, v in obj.__dict__.items()}
        elif isinstance(obj, list):
            return [to_dict(item) for item in obj]
        else:
            return obj

    data = to_dict(result)
    if pretty:
        return json.dumps(data, indent=2)
    return json.dumps(data)


def format_multisig_json(multisig: MultisigInfo, pretty: bool = True) -> str:
    """Format multisig as JSON."""
    def to_dict(obj):
        if hasattr(obj, "__dataclass_fields__"):
            return {k: to_dict(v) for k, v in obj.__dict__.items()}
        elif isinstance(obj, list):
            return [to_dict(item) for item in obj]
        else:
            return obj

    data = to_dict(multisig)
    if pretty:
        return json.dumps(data, indent=2)
    return json.dumps(data)


def format_compact(result: VerificationResult) -> str:
    """Format a compact one-line summary."""
    name = result.program.program_name or result.program.program_id[:8] + "..."

    if result.error:
        return f"❌ {name}: {result.error}"

    if result.multisig:
        timelock_icon = "✅" if result.multisig.time_lock_seconds > 0 else "⚠️"
        return f"{timelock_icon} {name}: {result.multisig.threshold_display} | Timelock: {result.multisig.time_lock_display}"

    return f"⚠️ {name}: No multisig found"


def format_batch_summary(batch: BatchVerificationResult) -> str:
    """Format batch results as a summary table."""
    lines = []

    lines.append("═" * 90)
    lines.append("SQUADS MULTISIG VERIFICATION SUMMARY")
    lines.append("═" * 90)
    lines.append("")
    lines.append(f"Total Programs: {batch.summary['total']}")
    lines.append(f"Successful:     {batch.summary['successful']}")
    lines.append(f"Failed:         {batch.summary['failed']}")
    lines.append(f"With Timelock:  {batch.summary['with_timelock']}")
    lines.append(f"No Timelock:    {batch.summary['without_timelock']}")
    lines.append("")
    lines.append("─" * 90)
    lines.append(
        "Program".ljust(20) +
        "Threshold".ljust(15) +
        "Timelock".ljust(20) +
        "Status"
    )
    lines.append("─" * 90)

    for result in batch.results:
        name = (result.program.program_name or result.program.program_id[:16]).ljust(20)

        if result.error:
            lines.append(f"{name}{'N/A'.ljust(15)}{'N/A'.ljust(20)}❌ {result.error[:30]}")
        elif result.multisig:
            threshold = result.multisig.threshold_display.ljust(15)
            timelock = result.multisig.time_lock_display.ljust(20)
            status = "✅ OK" if result.multisig.time_lock_seconds > 0 else "⚠️ NO TIMELOCK"
            lines.append(f"{name}{threshold}{timelock}{status}")
        else:
            lines.append(f"{name}{'N/A'.ljust(15)}{'N/A'.ljust(20)}⚠️ No multisig")

    lines.append("─" * 90)
    lines.append(f"Verification completed: {batch.timestamp}")
    lines.append("═" * 90)

    return "\n".join(lines)
