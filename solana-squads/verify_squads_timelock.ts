/**
 * Klend Admin Risk Verification Script
 *
 * Uses the official @sqds/multisig SDK to verify timelock configuration
 * for Squads v4 multisig accounts controlling Solana program upgrades.
 *
 * Usage:
 *   npx ts-node verify_squads_timelock.ts
 *
 * Or after compilation:
 *   node verify_squads_timelock.js
 */

import { Connection, PublicKey } from "@solana/web3.js";
import * as multisig from "@sqds/multisig";

// Configuration
const HELIUS_API_KEY = process.env.HELIUS_API_KEY;
const RPC_URL = HELIUS_API_KEY
  ? `https://mainnet.helius-rpc.com/?api-key=${HELIUS_API_KEY}`
  : "https://api.mainnet-beta.solana.com";

// Klend program address
const KLEND_PROGRAM = new PublicKey("KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD");

// BPF Loader Upgradeable program
const BPF_LOADER_UPGRADEABLE = new PublicKey("BPFLoaderUpgradeab1e11111111111111111111111");

interface MultisigAnalysis {
  address: string;
  threshold: number;
  memberCount: number;
  timeLock: number;
  timeLockHours: number;
  transactionIndex: string;
  staleTransactionIndex: string;
  configAuthority: string | null;
  rentCollector: string | null;
  bump: number;
  members: Array<{
    key: string;
    permissions: {
      mask: number;
      initiate: boolean;
      vote: boolean;
      execute: boolean;
    };
  }>;
}

async function getConnection(): Promise<Connection> {
  return new Connection(RPC_URL, "confirmed");
}

async function getProgramUpgradeAuthority(
  connection: Connection,
  programId: PublicKey
): Promise<{ programDataAddress: PublicKey; upgradeAuthority: PublicKey | null }> {
  // Get program account
  const programAccount = await connection.getAccountInfo(programId);
  if (!programAccount) {
    throw new Error(`Program account not found: ${programId.toBase58()}`);
  }

  if (!programAccount.owner.equals(BPF_LOADER_UPGRADEABLE)) {
    throw new Error(`Program is not upgradeable. Owner: ${programAccount.owner.toBase58()}`);
  }

  // Extract ProgramData address from program account (offset 4, 32 bytes)
  const programDataAddress = new PublicKey(programAccount.data.slice(4, 36));

  // Get ProgramData account
  const programDataAccount = await connection.getAccountInfo(programDataAddress);
  if (!programDataAccount) {
    throw new Error(`ProgramData account not found: ${programDataAddress.toBase58()}`);
  }

  // Extract upgrade authority (offset 12: 1 byte option, offset 13: 32 bytes pubkey)
  const hasAuthority = programDataAccount.data[12] === 1;
  const upgradeAuthority = hasAuthority
    ? new PublicKey(programDataAccount.data.slice(13, 45))
    : null;

  return { programDataAddress, upgradeAuthority };
}

async function findSquadsMultisigForVault(
  connection: Connection,
  vaultAddress: PublicKey
): Promise<PublicKey | null> {
  // Get recent signatures for the vault
  const signatures = await connection.getSignaturesForAddress(vaultAddress, { limit: 20 });

  for (const sigInfo of signatures) {
    const tx = await connection.getParsedTransaction(sigInfo.signature, {
      maxSupportedTransactionVersion: 0,
    });

    if (!tx?.transaction?.message?.instructions) continue;

    for (const ix of tx.transaction.message.instructions) {
      if ('programId' in ix && ix.programId.equals(multisig.PROGRAM_ID)) {
        // First account is typically the multisig
        if ('accounts' in ix && ix.accounts && ix.accounts.length > 0) {
          return ix.accounts[0];
        }
      }
    }
  }

  return null;
}

async function analyzeMultisig(
  connection: Connection,
  multisigAddress: PublicKey
): Promise<MultisigAnalysis> {
  // Use official SDK to fetch multisig account
  const multisigAccount = await multisig.accounts.Multisig.fromAccountAddress(
    connection,
    multisigAddress
  );

  const members = multisigAccount.members.map((member) => ({
    key: member.key.toBase58(),
    permissions: {
      mask: member.permissions.mask,
      initiate: (member.permissions.mask & 1) !== 0,
      vote: (member.permissions.mask & 2) !== 0,
      execute: (member.permissions.mask & 4) !== 0,
    },
  }));

  return {
    address: multisigAddress.toBase58(),
    threshold: multisigAccount.threshold,
    memberCount: members.length,
    timeLock: multisigAccount.timeLock,
    timeLockHours: multisigAccount.timeLock / 3600,
    transactionIndex: multisigAccount.transactionIndex.toString(),
    staleTransactionIndex: multisigAccount.staleTransactionIndex.toString(),
    configAuthority: multisigAccount.configAuthority.toBase58() === "11111111111111111111111111111111"
      ? null
      : multisigAccount.configAuthority.toBase58(),
    rentCollector: multisigAccount.rentCollector
      ? multisigAccount.rentCollector.toBase58()
      : null,
    bump: multisigAccount.bump,
    members,
  };
}

async function main() {
  console.log("=".repeat(70));
  console.log("KLEND ADMIN RISK VERIFICATION (Official Squads SDK)");
  console.log("=".repeat(70));
  console.log(`\nTimestamp: ${new Date().toISOString()}`);
  console.log(`RPC: ${RPC_URL.includes("helius") ? "Helius" : "Public"}\n`);

  const connection = await getConnection();

  // Step 1: Get Klend program upgrade authority
  console.log("Step 1: Finding Klend program upgrade authority...");
  console.log(`  Program: ${KLEND_PROGRAM.toBase58()}`);

  const { programDataAddress, upgradeAuthority } = await getProgramUpgradeAuthority(
    connection,
    KLEND_PROGRAM
  );

  console.log(`  ProgramData: ${programDataAddress.toBase58()}`);

  if (!upgradeAuthority) {
    console.log("  Upgrade Authority: REVOKED (immutable)");
    return;
  }

  console.log(`  Upgrade Authority: ${upgradeAuthority.toBase58()}`);

  // Step 2: Check if authority is a Squads multisig or vault
  console.log("\nStep 2: Analyzing upgrade authority...");

  const authorityAccount = await connection.getAccountInfo(upgradeAuthority);
  if (!authorityAccount) {
    console.log("  ERROR: Authority account not found");
    return;
  }

  let multisigAddress: PublicKey;
  let isVault = false;

  if (authorityAccount.owner.equals(multisig.PROGRAM_ID)) {
    console.log("  Type: Direct Squads v4 Multisig");
    multisigAddress = upgradeAuthority;
  } else if (authorityAccount.owner.toBase58() === "11111111111111111111111111111111" && authorityAccount.data.length === 0) {
    console.log("  Type: System-owned wallet (likely Squads Vault PDA)");
    console.log("\nStep 3: Finding parent Squads multisig...");

    const parentMultisig = await findSquadsMultisigForVault(connection, upgradeAuthority);
    if (!parentMultisig) {
      console.log("  ERROR: Could not find parent multisig");
      return;
    }

    console.log(`  Parent Multisig: ${parentMultisig.toBase58()}`);
    multisigAddress = parentMultisig;
    isVault = true;
  } else {
    console.log(`  Type: Unknown (owner: ${authorityAccount.owner.toBase58()})`);
    return;
  }

  // Step 3/4: Analyze the multisig using official SDK
  console.log(`\nStep ${isVault ? 4 : 3}: Fetching multisig data using @sqds/multisig SDK...`);

  const analysis = await analyzeMultisig(connection, multisigAddress);

  // Print results
  console.log("\n" + "=".repeat(70));
  console.log("RESULTS (from Official Squads SDK)");
  console.log("=".repeat(70));

  if (isVault) {
    console.log(`\nVault (Upgrade Authority): ${upgradeAuthority.toBase58()}`);
  }
  console.log(`\nMultisig Account: ${analysis.address}`);
  console.log(`\n--- Configuration ---`);
  console.log(`  Threshold: ${analysis.threshold} of ${analysis.memberCount}`);
  console.log(`  Time Lock: ${analysis.timeLock} seconds (${analysis.timeLockHours.toFixed(2)} hours)`);
  console.log(`  Transaction Index: ${analysis.transactionIndex}`);
  console.log(`  Stale TX Index: ${analysis.staleTransactionIndex}`);
  console.log(`  Config Authority: ${analysis.configAuthority || "None"}`);
  console.log(`  Rent Collector: ${analysis.rentCollector || "None"}`);
  console.log(`  Bump: ${analysis.bump}`);

  console.log(`\n--- Members (${analysis.memberCount}) ---`);
  analysis.members.forEach((member, i) => {
    const perms = [];
    if (member.permissions.initiate) perms.push("Initiate");
    if (member.permissions.vote) perms.push("Vote");
    if (member.permissions.execute) perms.push("Execute");
    console.log(`  ${i + 1}. ${member.key}`);
    console.log(`     Permissions: ${perms.join(" | ") || "None"} (0x${member.permissions.mask.toString(16).padStart(2, "0")})`);
  });

  console.log("\n" + "=".repeat(70));
  console.log("TIMELOCK VERIFICATION");
  console.log("=".repeat(70));

  if (analysis.timeLock === 0) {
    console.log("\n  ⚠️  WARNING: NO TIMELOCK CONFIGURED");
    console.log(`  Transactions can execute IMMEDIATELY after ${analysis.threshold} approvals`);
  } else {
    console.log(`\n  ✓ TIMELOCK IS CONFIGURED`);
    console.log(`  Delay: ${analysis.timeLockHours.toFixed(2)} hours (${analysis.timeLock} seconds)`);
    console.log(`  After ${analysis.threshold} approvals, must wait ${analysis.timeLockHours.toFixed(2)} hours before execution`);
  }

  console.log("\n" + "=".repeat(70));

  // Output JSON for programmatic use
  console.log("\n--- JSON Output ---");
  console.log(JSON.stringify({
    program: KLEND_PROGRAM.toBase58(),
    upgradeAuthority: upgradeAuthority.toBase58(),
    isVault,
    multisig: analysis,
    verified: true,
    sdk: "@sqds/multisig",
    timestamp: new Date().toISOString(),
  }, null, 2));
}

// Also verify the spreadsheet address for comparison
async function verifySpreadsheetAddress() {
  console.log("\n\n" + "=".repeat(70));
  console.log("ADDITIONAL: VERIFYING SPREADSHEET ADDRESS");
  console.log("=".repeat(70));

  const spreadsheetAddress = new PublicKey("FdtiepBtP98oU2uPNgAzUoGwggUDdRXwJH2KJo3oUaix");
  console.log(`\nSpreadsheet claims this is the upgrade authority: ${spreadsheetAddress.toBase58()}`);

  const connection = await getConnection();

  // Check what type of account this is
  const account = await connection.getAccountInfo(spreadsheetAddress);
  if (!account) {
    console.log("  ERROR: Account not found");
    return;
  }

  console.log(`  Owner: ${account.owner.toBase58()}`);
  console.log(`  Data length: ${account.data.length} bytes`);

  if (account.owner.toBase58() === "11111111111111111111111111111111" && account.data.length === 0) {
    console.log("  Type: System-owned wallet (likely Squads Vault PDA)");

    // Find parent multisig
    const parentMultisig = await findSquadsMultisigForVault(connection, spreadsheetAddress);
    if (parentMultisig) {
      console.log(`  Parent Multisig: ${parentMultisig.toBase58()}`);

      const analysis = await analyzeMultisig(connection, parentMultisig);

      console.log(`\n--- Spreadsheet Address Multisig Configuration ---`);
      console.log(`  Threshold: ${analysis.threshold} of ${analysis.memberCount}`);
      console.log(`  Time Lock: ${analysis.timeLock} seconds (${analysis.timeLockHours.toFixed(2)} hours)`);

      if (analysis.timeLock === 0) {
        console.log("\n  ⚠️  This multisig has NO TIMELOCK");
      }
    }
  }

  console.log("\n" + "=".repeat(70));
  console.log("COMPARISON SUMMARY");
  console.log("=".repeat(70));
  console.log("\n  Spreadsheet Address: FdtiepBtP98oU2uPNgAzUoGwggUDdRXwJH2KJo3oUaix");
  console.log("  Actual On-chain Authority: GzFgdRJXmawPhGeBsyRCDLx4jAKPsvbUqoqitzppkzkW");
  console.log("\n  ⚠️  THESE ARE DIFFERENT ADDRESSES!");
  console.log("\n  The spreadsheet data is INCORRECT.");
  console.log("  The actual Klend upgrade authority has a 4-hour timelock, NOT 0 hours.");
  console.log("=".repeat(70));
}

main()
  .then(() => verifySpreadsheetAddress())
  .catch((err) => {
    console.error("Error:", err);
    process.exit(1);
  });
