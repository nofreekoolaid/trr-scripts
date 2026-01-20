// Main exports for programmatic use
export {
  verifyProgram,
  verifyMultisigDirect,
  analyzeMultisig,
  getProgramInfo,
  findParentMultisig,
} from "./verifier";

export {
  formatTable,
  formatMarkdown,
  formatJSON,
  formatCompact,
  formatBatchSummary,
} from "./formatters";

export type {
  MultisigInfo,
  MemberInfo,
  ProgramInfo,
  VaultInfo,
  VerificationResult,
  BatchVerificationResult,
} from "./types";
