# Squads Multisig Verifier

A CLI tool to verify Squads v4 multisig configuration for Solana programs. Analyzes upgrade authorities, threshold requirements (n-of-m), and timelock durations.

## Installation

```bash
npm install
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
npx ts-node src/cli.ts program <programId>

# With name for display
npx ts-node src/cli.ts program KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD --name "Klend"

# Output as JSON
npx ts-node src/cli.ts program <programId> --format json

# Output as Markdown
npx ts-node src/cli.ts program <programId> --format markdown

# Save to file
npx ts-node src/cli.ts program <programId> --output report.md --format markdown
```

### Analyze a Multisig Directly

```bash
# By multisig address
npx ts-node src/cli.ts multisig <multisigAddress>

# JSON output
npx ts-node src/cli.ts multisig <multisigAddress> --format json
```

### Batch Verify Multiple Programs

Create a JSON file with programs to verify:

```json
[
  { "programId": "KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD", "name": "Klend" },
  { "programId": "dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH", "name": "Drift" }
]
```

Run batch verification:

```bash
npx ts-node src/cli.ts batch programs.json

# Output formats: summary (default), json, markdown
npx ts-node src/cli.ts batch programs.json --format json --output results.json
```

### List Well-Known Programs

```bash
npx ts-node src/cli.ts list-known
```

## Output Formats

### Table (default)
```
──────────────────────────────────────────────────────────────────────
MULTISIG: 6hhBGCtmg7tPWUSgp3LG6X2rsmYWAc4tNsA6G4CnfQbM
──────────────────────────────────────────────────────────────────────
Threshold:          5 of 10
Timelock:           4.0 hours
Timelock (seconds): 14400
Create Key:         Cyv5n1Ct4wLzCJoM7BDgwxkQ6rAZyyPAGWUu1yqF1Se1

Members:
  5ggs2vd1csz74YMCzxesmcUEd3ycYFKAW6kfyttVYwBv
    Permissions: Proposer, Voter, Executor
  ...
```

### JSON
```json
{
  "address": "6hhBGCtmg7tPWUSgp3LG6X2rsmYWAc4tNsA6G4CnfQbM",
  "threshold": 5,
  "memberCount": 10,
  "thresholdDisplay": "5 of 10",
  "timeLockSeconds": 14400,
  "timeLockHours": 4,
  "timeLockDisplay": "4.0 hours",
  "members": [...]
}
```

### Markdown
Formatted report suitable for documentation.

## Programmatic Usage

```typescript
import { Connection } from "@solana/web3.js";
import { verifyProgram, verifyMultisigDirect } from "squads-verifier";

const connection = new Connection("https://api.mainnet-beta.solana.com");

// Verify a program
const result = await verifyProgram(
  connection,
  "KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD",
  "Klend"
);

console.log(result.multisig?.thresholdDisplay); // "5 of 10"
console.log(result.multisig?.timeLockHours);    // 4

// Analyze multisig directly
const multisig = await verifyMultisigDirect(
  connection,
  "6hhBGCtmg7tPWUSgp3LG6X2rsmYWAc4tNsA6G4CnfQbM"
);
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

- `@solana/web3.js` - Solana SDK
- `@sqds/multisig` - Official Squads v4 SDK
- `commander` - CLI framework
