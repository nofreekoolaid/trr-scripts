export interface MultisigInfo {
  address: string;
  threshold: number;
  memberCount: number;
  thresholdDisplay: string; // "3 of 5" format
  timeLockSeconds: number;
  timeLockHours: number;
  timeLockDisplay: string; // "4 hours" or "None"
  createKey: string;
  configAuthority: string | null;
  rentCollector: string | null;
  bump: number;
  transactionIndex: string;
  staleTransactionIndex: string;
  members: MemberInfo[];
}

export interface MemberInfo {
  address: string;
  permissions: string[];
}

export interface ProgramInfo {
  programId: string;
  programName?: string;
  programDataAddress: string;
  upgradeAuthority: string | null;
  isUpgradeable: boolean;
}

export interface VaultInfo {
  vaultAddress: string;
  parentMultisig: string | null;
  vaultIndex: number | null;
}

export interface VerificationResult {
  program: ProgramInfo;
  vault: VaultInfo | null;
  multisig: MultisigInfo | null;
  error?: string;
  timestamp: string;
  rpcEndpoint: string;
}

export interface BatchVerificationResult {
  results: VerificationResult[];
  summary: {
    total: number;
    successful: number;
    failed: number;
    withTimelock: number;
    withoutTimelock: number;
  };
  timestamp: string;
}
