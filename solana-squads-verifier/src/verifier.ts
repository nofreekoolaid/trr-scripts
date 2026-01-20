import { Connection, PublicKey } from "@solana/web3.js";
import * as multisig from "@sqds/multisig";
import {
  MultisigInfo,
  MemberInfo,
  ProgramInfo,
  VaultInfo,
  VerificationResult,
} from "./types";

const BPF_LOADER_UPGRADEABLE = new PublicKey(
  "BPFLoaderUpgradeab1e11111111111111111111111"
);
const SQUADS_V4_PROGRAM = new PublicKey(
  "SQDS4ep65T869zMMBKyuUq6aD6EgTu8psMjkvj52pCf"
);

/**
 * Fetch program info including upgrade authority
 *
 * BPF Upgradeable Program Layout:
 * - Program account data bytes 4-36 contain the ProgramData address
 * - ProgramData account byte 12 is the option flag (1 = has authority)
 * - ProgramData account bytes 13-45 contain the upgrade authority pubkey
 */
export async function getProgramInfo(
  connection: Connection,
  programId: PublicKey,
  programName?: string
): Promise<ProgramInfo> {
  // Step 1: Get program account to extract ProgramData address
  const programAccount = await connection.getAccountInfo(programId);

  if (!programAccount) {
    throw new Error(`Program account not found: ${programId.toBase58()}`);
  }

  if (!programAccount.owner.equals(BPF_LOADER_UPGRADEABLE)) {
    throw new Error(`Program is not BPF Upgradeable. Owner: ${programAccount.owner.toBase58()}`);
  }

  // Extract ProgramData address from program account (offset 4, 32 bytes)
  const programDataAddress = new PublicKey(programAccount.data.slice(4, 36));

  // Step 2: Get ProgramData account
  const programDataAccount = await connection.getAccountInfo(programDataAddress);

  if (!programDataAccount) {
    throw new Error(`ProgramData account not found: ${programDataAddress.toBase58()}`);
  }

  // ProgramData layout:
  // - byte 12: option flag (1 = has authority, 0 = no authority/immutable)
  // - bytes 13-45: upgrade authority pubkey (if option is 1)
  const data = programDataAccount.data;
  const hasAuthority = data[12] === 1;
  let upgradeAuthority: string | null = null;

  if (hasAuthority) {
    upgradeAuthority = new PublicKey(data.slice(13, 45)).toBase58();
  }

  return {
    programId: programId.toBase58(),
    programName,
    programDataAddress: programDataAddress.toBase58(),
    upgradeAuthority,
    isUpgradeable: hasAuthority,
  };
}

/**
 * Try to find parent multisig for a vault PDA
 * Searches through common vault indices (0-10)
 */
export async function findParentMultisig(
  connection: Connection,
  vaultAddress: PublicKey
): Promise<VaultInfo> {
  // First check if this address is itself a multisig account
  const accountInfo = await connection.getAccountInfo(vaultAddress);

  if (accountInfo && accountInfo.owner.equals(SQUADS_V4_PROGRAM)) {
    // This is a Squads account - check if it's a multisig directly
    try {
      await multisig.accounts.Multisig.fromAccountAddress(connection, vaultAddress);
      // It's a multisig account, not a vault
      return {
        vaultAddress: vaultAddress.toBase58(),
        parentMultisig: vaultAddress.toBase58(),
        vaultIndex: null,
      };
    } catch {
      // Not a multisig, continue searching
    }
  }

  // Search for parent multisig by trying different vault indices
  // We need to find which multisig derives this vault address
  const signatures = await connection.getSignaturesForAddress(vaultAddress, {
    limit: 50,
  });

  for (const sig of signatures) {
    const tx = await connection.getParsedTransaction(sig.signature, {
      maxSupportedTransactionVersion: 0,
    });

    if (!tx) continue;

    // Look for Squads program in the transaction
    for (const ix of tx.transaction.message.instructions) {
      if ("programId" in ix && ix.programId.equals(SQUADS_V4_PROGRAM)) {
        // Found a Squads transaction, check accounts for potential multisig
        const accountKeys = tx.transaction.message.accountKeys;
        for (const key of accountKeys) {
          const pubkey = key.pubkey;
          if (pubkey.equals(vaultAddress)) continue;

          try {
            const msInfo = await connection.getAccountInfo(pubkey);
            if (msInfo && msInfo.owner.equals(SQUADS_V4_PROGRAM)) {
              // Verify this is the parent by checking vault derivation
              for (let vaultIndex = 0; vaultIndex <= 10; vaultIndex++) {
                const [derivedVault] = multisig.getVaultPda({
                  multisigPda: pubkey,
                  index: vaultIndex,
                });
                if (derivedVault.equals(vaultAddress)) {
                  return {
                    vaultAddress: vaultAddress.toBase58(),
                    parentMultisig: pubkey.toBase58(),
                    vaultIndex,
                  };
                }
              }
            }
          } catch {
            continue;
          }
        }
      }
    }
  }

  return {
    vaultAddress: vaultAddress.toBase58(),
    parentMultisig: null,
    vaultIndex: null,
  };
}

/**
 * Parse permissions from the Squads SDK permission object
 */
function parsePermissions(permissions: any): string[] {
  const perms: string[] = [];
  if (permissions.mask !== undefined) {
    const mask = Number(permissions.mask);
    if (mask & 1) perms.push("Proposer");
    if (mask & 2) perms.push("Voter");
    if (mask & 4) perms.push("Executor");
    if (mask & 8) perms.push("CancelProposer");
  }
  return perms.length > 0 ? perms : ["Unknown"];
}

/**
 * Format timelock duration for display
 */
function formatTimelock(seconds: number): string {
  if (seconds === 0) return "None (0 seconds)";
  if (seconds < 60) return `${seconds} seconds`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} minutes`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)} hours`;
  return `${(seconds / 86400).toFixed(1)} days`;
}

/**
 * Analyze a Squads multisig account
 */
export async function analyzeMultisig(
  connection: Connection,
  multisigAddress: PublicKey
): Promise<MultisigInfo> {
  const msAccount = await multisig.accounts.Multisig.fromAccountAddress(
    connection,
    multisigAddress
  );

  const members: MemberInfo[] = msAccount.members.map((member: any) => ({
    address: member.key.toBase58(),
    permissions: parsePermissions(member.permissions),
  }));

  const timeLockSeconds = msAccount.timeLock;
  const threshold = msAccount.threshold;
  const memberCount = members.length;

  return {
    address: multisigAddress.toBase58(),
    threshold,
    memberCount,
    thresholdDisplay: `${threshold} of ${memberCount}`,
    timeLockSeconds,
    timeLockHours: timeLockSeconds / 3600,
    timeLockDisplay: formatTimelock(timeLockSeconds),
    createKey: msAccount.createKey.toBase58(),
    configAuthority:
      msAccount.configAuthority &&
      !msAccount.configAuthority.equals(PublicKey.default)
        ? msAccount.configAuthority.toBase58()
        : null,
    rentCollector:
      msAccount.rentCollector &&
      !msAccount.rentCollector.equals(PublicKey.default)
        ? msAccount.rentCollector.toBase58()
        : null,
    bump: msAccount.bump,
    transactionIndex: msAccount.transactionIndex.toString(),
    staleTransactionIndex: msAccount.staleTransactionIndex.toString(),
    members,
  };
}

/**
 * Main verification function - analyzes a program's upgrade authority multisig
 */
export async function verifyProgram(
  connection: Connection,
  programId: string | PublicKey,
  programName?: string
): Promise<VerificationResult> {
  const timestamp = new Date().toISOString();
  const rpcEndpoint = connection.rpcEndpoint;

  const pubkey =
    typeof programId === "string" ? new PublicKey(programId) : programId;

  try {
    // Step 1: Get program info
    const program = await getProgramInfo(connection, pubkey, programName);

    if (!program.upgradeAuthority) {
      return {
        program,
        vault: null,
        multisig: null,
        error: "Program is immutable (no upgrade authority)",
        timestamp,
        rpcEndpoint,
      };
    }

    // Step 2: Find parent multisig from vault/authority
    const authorityPubkey = new PublicKey(program.upgradeAuthority);
    const vault = await findParentMultisig(connection, authorityPubkey);

    if (!vault.parentMultisig) {
      return {
        program,
        vault,
        multisig: null,
        error: `Could not find parent Squads multisig for authority ${program.upgradeAuthority}`,
        timestamp,
        rpcEndpoint,
      };
    }

    // Step 3: Analyze the multisig
    const multisigPubkey = new PublicKey(vault.parentMultisig);
    const multisigInfo = await analyzeMultisig(connection, multisigPubkey);

    return {
      program,
      vault,
      multisig: multisigInfo,
      timestamp,
      rpcEndpoint,
    };
  } catch (error) {
    return {
      program: {
        programId: pubkey.toBase58(),
        programName,
        programDataAddress: "",
        upgradeAuthority: null,
        isUpgradeable: false,
      },
      vault: null,
      multisig: null,
      error: error instanceof Error ? error.message : String(error),
      timestamp,
      rpcEndpoint,
    };
  }
}

/**
 * Verify a multisig directly by address (not via program)
 */
export async function verifyMultisigDirect(
  connection: Connection,
  multisigAddress: string | PublicKey
): Promise<MultisigInfo> {
  const pubkey =
    typeof multisigAddress === "string"
      ? new PublicKey(multisigAddress)
      : multisigAddress;

  return analyzeMultisig(connection, pubkey);
}
