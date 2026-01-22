# Squads Multisig Verifier (Python)

Verify Squads v4 multisig configuration for Solana programs. Analyzes upgrade authorities, threshold requirements (n-of-m), and timelock durations.

## Installation

```bash
pip install -r requirements.txt
```

## Prerequisites

Set your RPC endpoint via environment variable:

```bash
# Helius (recommended)
export HELIUS_API_KEY=your_api_key

# Or use custom RPC
export SOLANA_RPC_URL=https://your-rpc-endpoint.com
```

## Usage

### Verify a Program's Upgrade Authority

```bash
# Basic usage
python -m squads_verifier program <programId>

# With name for display
python -m squads_verifier program KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD --name "Klend"

# Output as JSON
python -m squads_verifier program <programId> --format json

# Output as Markdown
python -m squads_verifier program <programId> --format markdown

# Save to file
python -m squads_verifier program <programId> --output report.md --format markdown
```

### Analyze a Multisig Directly

```bash
# By multisig address
python -m squads_verifier multisig <multisigAddress>

# JSON output
python -m squads_verifier multisig <multisigAddress> --format json
```

### Batch Verify Multiple Programs

Create a JSON file with programs to verify:

```json
[
  { "program_id": "KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD", "name": "Klend" },
  { "program_id": "dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH", "name": "Drift" }
]
```

Run batch verification:

```bash
python -m squads_verifier batch programs.json

# Output formats: summary (default), json, markdown
python -m squads_verifier batch programs.json --format json --output results.json
```

### List Well-Known Programs

```bash
python -m squads_verifier list-known
```

## Example Output

```
──────────────────────────────────────────────────────────────────────
PROGRAM: Klend
──────────────────────────────────────────────────────────────────────
Program Information:
  Program ID:         KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD
  ProgramData:        9uSbGW1y9H5Av6H5TKxQ1wnFApSq2t3oEpfF2YfjDQGA
  Upgrade Authority:  GzFgdRJXmawPhGeBsyRCDLx4jAKPsvbUqoqitzppkzkW
  Is Upgradeable:     Yes

Vault Information:
  Vault Address:      GzFgdRJXmawPhGeBsyRCDLx4jAKPsvbUqoqitzppkzkW
  Parent Multisig:    6hhBGCtmg7tPWUSgp3LG6X2rsmYWAc4tNsA6G4CnfQbM
  Vault Index:        0

Multisig Configuration:
  Multisig Address:   6hhBGCtmg7tPWUSgp3LG6X2rsmYWAc4tNsA6G4CnfQbM
  Threshold:          5 of 10
  Timelock:           4.0 hours
  Timelock (seconds): 14400
  Create Key:         Cyv5n1Ct4wLzCJoM7BDgwxkQ6rAZyyPAGWUu1yqF1Se1

Members:
  5ggs2vd1csz74YMCzxesmcUEd3ycYFKAW6kfyttVYwBv
    Permissions: Proposer, Voter, Executor
  ...
```

## Programmatic Usage

```python
from squads_verifier import verify_program, verify_multisig_direct

# Verify a program
result = verify_program(
    "KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD",
    program_name="Klend"
)

print(result.multisig.threshold_display)  # "5 of 10"
print(result.multisig.time_lock_hours)    # 4.0

# Analyze multisig directly
multisig = verify_multisig_direct("6hhBGCtmg7tPWUSgp3LG6X2rsmYWAc4tNsA6G4CnfQbM")
```

## What It Checks

1. **Program Upgradeability**: Whether the program can be upgraded
2. **Upgrade Authority**: The address that controls upgrades
3. **Vault Detection**: Identifies if authority is a Squads vault PDA
4. **Parent Multisig**: Traces vault to its parent multisig account
5. **Threshold**: n-of-m signature requirements
6. **Timelock**: Delay before transactions can be executed
7. **Members**: All multisig members and their permissions

## Understanding Results

### Threshold
- Format: `n of m` (e.g., "3 of 5")
- `n` = minimum signatures required
- `m` = total members

### Timelock
- Time delay (in seconds/hours) before approved transactions execute
- `0` = No timelock (transactions execute immediately after approval)
- Higher values = more time for users to react to malicious upgrades

### Member Permissions
- **Proposer**: Can create new transactions
- **Voter**: Can approve/reject transactions
- **Executor**: Can execute approved transactions
- **CancelProposer**: Can cancel pending transactions

## Security Considerations

- **No Timelock (⚠️)**: Users have no time to exit before potentially malicious upgrades
- **Low Threshold**: Fewer signatures needed increases centralization risk
- **Immutable Programs**: Cannot be upgraded (most secure, but inflexible)

## Dependencies

- `requests` - HTTP client for Solana RPC
- `base58` - Base58 encoding/decoding
- `click` - CLI framework
