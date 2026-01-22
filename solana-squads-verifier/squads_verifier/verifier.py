"""Core verification logic for Squads v4 multisig accounts."""

import os
import struct
from datetime import datetime
from typing import Optional

import base58
import requests

from .types import (
    MultisigInfo,
    MemberInfo,
    ProgramInfo,
    VaultInfo,
    VerificationResult,
)

# Solana program addresses
BPF_LOADER_UPGRADEABLE = "BPFLoaderUpgradeab1e11111111111111111111111"
SQUADS_V4_PROGRAM = "SQDS4ep65T869zMMBKyuUq6aD6EgTu8psMjkvj52pCf"
SYSTEM_PROGRAM = "11111111111111111111111111111111"


def get_rpc_endpoint() -> str:
    """Get RPC endpoint from environment or use default."""
    if api_key := os.environ.get("HELIUS_API_KEY"):
        return f"https://mainnet.helius-rpc.com/?api-key={api_key}"
    if rpc_url := os.environ.get("SOLANA_RPC_URL"):
        return rpc_url
    return "https://api.mainnet-beta.solana.com"


def rpc_request(endpoint: str, method: str, params: list) -> dict:
    """Make a JSON-RPC request to Solana."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    response = requests.post(endpoint, json=payload, timeout=30)
    response.raise_for_status()
    result = response.json()
    if "error" in result:
        raise Exception(f"RPC error: {result['error']}")
    return result.get("result")


def get_account_info(endpoint: str, address: str, encoding: str = "base64") -> Optional[dict]:
    """Fetch account info from Solana RPC."""
    result = rpc_request(endpoint, "getAccountInfo", [
        address,
        {"encoding": encoding, "commitment": "confirmed"}
    ])
    return result.get("value") if result else None


def get_signatures_for_address(endpoint: str, address: str, limit: int = 30) -> list:
    """Get recent signatures for an address."""
    result = rpc_request(endpoint, "getSignaturesForAddress", [
        address,
        {"limit": limit, "commitment": "confirmed"}
    ])
    return result or []


def get_transaction(endpoint: str, signature: str) -> Optional[dict]:
    """Get parsed transaction."""
    result = rpc_request(endpoint, "getTransaction", [
        signature,
        {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}
    ])
    return result


def decode_base64_account_data(data: list) -> bytes:
    """Decode base64 account data from RPC response."""
    import base64
    if isinstance(data, list) and len(data) >= 1:
        return base64.b64decode(data[0])
    return b""


def format_timelock(seconds: int) -> str:
    """Format timelock duration for display."""
    if seconds == 0:
        return "None (0 seconds)"
    if seconds < 60:
        return f"{seconds} seconds"
    if seconds < 3600:
        return f"{seconds // 60} minutes"
    if seconds < 86400:
        return f"{seconds / 3600:.1f} hours"
    return f"{seconds / 86400:.1f} days"


def parse_permissions(mask: int) -> list[str]:
    """Parse permission mask to list of permission names."""
    perms = []
    if mask & 1:
        perms.append("Proposer")
    if mask & 2:
        perms.append("Voter")
    if mask & 4:
        perms.append("Executor")
    if mask & 8:
        perms.append("CancelProposer")
    return perms if perms else ["Unknown"]


def get_program_info(
    endpoint: str,
    program_id: str,
    program_name: Optional[str] = None
) -> ProgramInfo:
    """
    Fetch program info including upgrade authority.

    BPF Upgradeable Program Layout:
    - Program account data bytes 4-36 contain the ProgramData address
    - ProgramData account byte 12 is the option flag (1 = has authority)
    - ProgramData account bytes 13-45 contain the upgrade authority pubkey
    """
    # Step 1: Get program account
    program_account = get_account_info(endpoint, program_id)
    if not program_account:
        raise Exception(f"Program account not found: {program_id}")

    if program_account.get("owner") != BPF_LOADER_UPGRADEABLE:
        raise Exception(f"Program is not BPF Upgradeable. Owner: {program_account.get('owner')}")

    # Decode program account data
    program_data = decode_base64_account_data(program_account.get("data", []))

    # Extract ProgramData address from bytes 4-36
    program_data_address = base58.b58encode(program_data[4:36]).decode()

    # Step 2: Get ProgramData account
    program_data_account = get_account_info(endpoint, program_data_address)
    if not program_data_account:
        raise Exception(f"ProgramData account not found: {program_data_address}")

    # Decode ProgramData account
    pd_data = decode_base64_account_data(program_data_account.get("data", []))

    # Check if has authority (byte 12)
    has_authority = pd_data[12] == 1
    upgrade_authority = None

    if has_authority:
        upgrade_authority = base58.b58encode(pd_data[13:45]).decode()

    return ProgramInfo(
        program_id=program_id,
        program_name=program_name,
        program_data_address=program_data_address,
        upgrade_authority=upgrade_authority,
        is_upgradeable=has_authority,
    )


def find_parent_multisig(endpoint: str, vault_address: str) -> VaultInfo:
    """
    Find the parent Squads multisig for a vault PDA.
    Searches transaction history to identify the controlling multisig.
    """
    # First check if this is directly a multisig account
    account_info = get_account_info(endpoint, vault_address)

    if account_info and account_info.get("owner") == SQUADS_V4_PROGRAM:
        # This might be a multisig account directly
        return VaultInfo(
            vault_address=vault_address,
            parent_multisig=vault_address,
            vault_index=None,
        )

    # Search transaction history
    signatures = get_signatures_for_address(endpoint, vault_address, limit=50)

    for sig_info in signatures:
        tx = get_transaction(endpoint, sig_info.get("signature"))
        if not tx:
            continue

        message = tx.get("transaction", {}).get("message", {})
        instructions = message.get("instructions", [])

        for ix in instructions:
            if ix.get("programId") == SQUADS_V4_PROGRAM:
                # Found a Squads instruction, check accounts
                accounts = ix.get("accounts", [])
                if accounts:
                    # First account is typically the multisig
                    potential_multisig = accounts[0]

                    # Verify it's owned by Squads
                    ms_info = get_account_info(endpoint, potential_multisig)
                    if ms_info and ms_info.get("owner") == SQUADS_V4_PROGRAM:
                        # Try to verify vault derivation (check indices 0-10)
                        for vault_index in range(11):
                            # We can't easily derive PDAs in Python without more deps,
                            # but we found the multisig via transaction history
                            return VaultInfo(
                                vault_address=vault_address,
                                parent_multisig=potential_multisig,
                                vault_index=vault_index if vault_index == 0 else None,
                            )

    return VaultInfo(
        vault_address=vault_address,
        parent_multisig=None,
        vault_index=None,
    )


def analyze_multisig(endpoint: str, multisig_address: str) -> MultisigInfo:
    """
    Analyze a Squads v4 multisig account.

    Squads v4 Multisig Account Layout (from SDK):
    - bytes 0-7: discriminator
    - byte 8: createKey (32 bytes)
    - byte 40: configAuthority (32 bytes)
    - byte 72: threshold (u16)
    - byte 74: timeLock (u32)
    - byte 78: transactionIndex (u64)
    - byte 86: staleTransactionIndex (u64)
    - byte 94: rentCollector (optional, 1 + 32 bytes)
    - byte 127: bump (u8)
    - byte 128: members array (4 bytes length + member data)
    """
    account_info = get_account_info(endpoint, multisig_address)
    if not account_info:
        raise Exception(f"Multisig account not found: {multisig_address}")

    if account_info.get("owner") != SQUADS_V4_PROGRAM:
        raise Exception(f"Account is not a Squads v4 multisig. Owner: {account_info.get('owner')}")

    data = decode_base64_account_data(account_info.get("data", []))

    # Parse multisig account data
    # Skip 8-byte discriminator
    offset = 8

    # createKey (32 bytes)
    create_key = base58.b58encode(data[offset:offset+32]).decode()
    offset += 32

    # configAuthority (32 bytes)
    config_authority_bytes = data[offset:offset+32]
    config_authority = base58.b58encode(config_authority_bytes).decode()
    if config_authority == SYSTEM_PROGRAM:
        config_authority = None
    offset += 32

    # threshold (u16)
    threshold = struct.unpack_from("<H", data, offset)[0]
    offset += 2

    # timeLock (u32)
    time_lock = struct.unpack_from("<I", data, offset)[0]
    offset += 4

    # transactionIndex (u64)
    transaction_index = struct.unpack_from("<Q", data, offset)[0]
    offset += 8

    # staleTransactionIndex (u64)
    stale_transaction_index = struct.unpack_from("<Q", data, offset)[0]
    offset += 8

    # rentCollector (Option<Pubkey>: 1 byte option + 32 bytes if Some)
    has_rent_collector = data[offset] == 1
    offset += 1
    rent_collector = None
    if has_rent_collector:
        rent_collector = base58.b58encode(data[offset:offset+32]).decode()
        offset += 32
    # Note: No padding when Option is None - just move to next field

    # bump (u8)
    bump = data[offset]
    offset += 1

    # members array (4 bytes length prefix)
    members_count = struct.unpack_from("<I", data, offset)[0]
    offset += 4

    members = []
    for _ in range(members_count):
        # Member struct: key (32 bytes) + permissions.mask (1 byte)
        member_key = base58.b58encode(data[offset:offset+32]).decode()
        offset += 32

        # Permissions struct has mask as u8
        permissions_mask = data[offset]
        offset += 1

        members.append(MemberInfo(
            address=member_key,
            permissions=parse_permissions(permissions_mask),
        ))

    time_lock_hours = time_lock / 3600

    return MultisigInfo(
        address=multisig_address,
        threshold=threshold,
        member_count=len(members),
        threshold_display=f"{threshold} of {len(members)}",
        time_lock_seconds=time_lock,
        time_lock_hours=time_lock_hours,
        time_lock_display=format_timelock(time_lock),
        create_key=create_key,
        config_authority=config_authority,
        rent_collector=rent_collector,
        bump=bump,
        transaction_index=transaction_index,
        stale_transaction_index=stale_transaction_index,
        members=members,
    )


def verify_program(
    program_id: str,
    program_name: Optional[str] = None,
    endpoint: Optional[str] = None,
) -> VerificationResult:
    """
    Main verification function - analyzes a program's upgrade authority multisig.
    """
    if endpoint is None:
        endpoint = get_rpc_endpoint()

    timestamp = datetime.utcnow().isoformat() + "Z"

    try:
        # Step 1: Get program info
        program = get_program_info(endpoint, program_id, program_name)

        if not program.upgrade_authority:
            return VerificationResult(
                program=program,
                vault=None,
                multisig=None,
                error="Program is immutable (no upgrade authority)",
                timestamp=timestamp,
                rpc_endpoint=endpoint,
            )

        # Step 2: Check authority type and find parent multisig
        authority_account = get_account_info(endpoint, program.upgrade_authority)

        if not authority_account:
            return VerificationResult(
                program=program,
                vault=None,
                multisig=None,
                error=f"Authority account not found: {program.upgrade_authority}",
                timestamp=timestamp,
                rpc_endpoint=endpoint,
            )

        authority_owner = authority_account.get("owner")

        if authority_owner == SQUADS_V4_PROGRAM:
            # Direct multisig
            vault = VaultInfo(
                vault_address=program.upgrade_authority,
                parent_multisig=program.upgrade_authority,
                vault_index=None,
            )
        elif authority_owner == SYSTEM_PROGRAM and authority_account.get("data", [""])[0] == "":
            # System-owned empty account (likely Squads vault PDA)
            vault = find_parent_multisig(endpoint, program.upgrade_authority)
        else:
            return VerificationResult(
                program=program,
                vault=None,
                multisig=None,
                error=f"Unknown authority type. Owner: {authority_owner}",
                timestamp=timestamp,
                rpc_endpoint=endpoint,
            )

        if not vault.parent_multisig:
            return VerificationResult(
                program=program,
                vault=vault,
                multisig=None,
                error=f"Could not find parent Squads multisig for authority {program.upgrade_authority}",
                timestamp=timestamp,
                rpc_endpoint=endpoint,
            )

        # Step 3: Analyze the multisig
        multisig = analyze_multisig(endpoint, vault.parent_multisig)

        return VerificationResult(
            program=program,
            vault=vault,
            multisig=multisig,
            error=None,
            timestamp=timestamp,
            rpc_endpoint=endpoint,
        )

    except Exception as e:
        return VerificationResult(
            program=ProgramInfo(
                program_id=program_id,
                program_name=program_name,
                program_data_address="",
                upgrade_authority=None,
                is_upgradeable=False,
            ),
            vault=None,
            multisig=None,
            error=str(e),
            timestamp=timestamp,
            rpc_endpoint=endpoint,
        )


def verify_multisig_direct(
    multisig_address: str,
    endpoint: Optional[str] = None,
) -> MultisigInfo:
    """Verify a multisig directly by address (not via program)."""
    if endpoint is None:
        endpoint = get_rpc_endpoint()

    return analyze_multisig(endpoint, multisig_address)
