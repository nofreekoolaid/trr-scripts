"""Squads Multisig Verifier - Verify Squads v4 multisig configuration for Solana programs."""

from .verifier import (
    verify_program,
    verify_multisig_direct,
    get_program_info,
    analyze_multisig,
    find_parent_multisig,
)
from .formatters import (
    format_table,
    format_json,
    format_markdown,
    format_compact,
    format_batch_summary,
)
from .types import (
    MultisigInfo,
    MemberInfo,
    ProgramInfo,
    VaultInfo,
    VerificationResult,
    BatchVerificationResult,
)

__version__ = "1.0.0"
__all__ = [
    "verify_program",
    "verify_multisig_direct",
    "get_program_info",
    "analyze_multisig",
    "find_parent_multisig",
    "format_table",
    "format_json",
    "format_markdown",
    "format_compact",
    "format_batch_summary",
    "MultisigInfo",
    "MemberInfo",
    "ProgramInfo",
    "VaultInfo",
    "VerificationResult",
    "BatchVerificationResult",
]
