"""Type definitions for Squads Multisig Verifier."""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class MemberInfo:
    """Multisig member information."""
    address: str
    permissions: list[str]


@dataclass
class MultisigInfo:
    """Squads v4 multisig account information."""
    address: str
    threshold: int
    member_count: int
    threshold_display: str  # "3 of 5" format
    time_lock_seconds: int
    time_lock_hours: float
    time_lock_display: str  # "4 hours" or "None"
    create_key: str
    config_authority: Optional[str]
    rent_collector: Optional[str]
    bump: int
    transaction_index: int
    stale_transaction_index: int
    members: list[MemberInfo]


@dataclass
class ProgramInfo:
    """Solana program information."""
    program_id: str
    program_name: Optional[str]
    program_data_address: str
    upgrade_authority: Optional[str]
    is_upgradeable: bool


@dataclass
class VaultInfo:
    """Squads vault PDA information."""
    vault_address: str
    parent_multisig: Optional[str]
    vault_index: Optional[int]


@dataclass
class VerificationResult:
    """Result of program verification."""
    program: ProgramInfo
    vault: Optional[VaultInfo]
    multisig: Optional[MultisigInfo]
    error: Optional[str]
    timestamp: str
    rpc_endpoint: str


@dataclass
class BatchVerificationResult:
    """Result of batch program verification."""
    results: list[VerificationResult]
    summary: dict
    timestamp: str
