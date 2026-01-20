import { VerificationResult, BatchVerificationResult, MultisigInfo } from "./types";

/**
 * Format a single verification result as a table
 */
export function formatTable(result: VerificationResult): string {
  const lines: string[] = [];
  const divider = "─".repeat(70);

  lines.push(divider);
  lines.push(`PROGRAM: ${result.program.programName || result.program.programId}`);
  lines.push(divider);

  // Program Info
  lines.push("Program Information:");
  lines.push(`  Program ID:         ${result.program.programId}`);
  lines.push(`  ProgramData:        ${result.program.programDataAddress}`);
  lines.push(`  Upgrade Authority:  ${result.program.upgradeAuthority || "None (Immutable)"}`);
  lines.push(`  Is Upgradeable:     ${result.program.isUpgradeable ? "Yes" : "No"}`);

  if (result.error) {
    lines.push("");
    lines.push(`⚠️  Error: ${result.error}`);
    lines.push(divider);
    return lines.join("\n");
  }

  // Vault Info
  if (result.vault) {
    lines.push("");
    lines.push("Vault Information:");
    lines.push(`  Vault Address:      ${result.vault.vaultAddress}`);
    lines.push(`  Parent Multisig:    ${result.vault.parentMultisig || "Not found"}`);
    if (result.vault.vaultIndex !== null) {
      lines.push(`  Vault Index:        ${result.vault.vaultIndex}`);
    }
  }

  // Multisig Info
  if (result.multisig) {
    lines.push("");
    lines.push("Multisig Configuration:");
    lines.push(`  Multisig Address:   ${result.multisig.address}`);
    lines.push(`  Threshold:          ${result.multisig.thresholdDisplay}`);
    lines.push(`  Timelock:           ${result.multisig.timeLockDisplay}`);
    lines.push(`  Timelock (seconds): ${result.multisig.timeLockSeconds}`);
    lines.push(`  Create Key:         ${result.multisig.createKey}`);
    if (result.multisig.configAuthority) {
      lines.push(`  Config Authority:   ${result.multisig.configAuthority}`);
    }

    lines.push("");
    lines.push("Members:");
    for (const member of result.multisig.members) {
      lines.push(`  ${member.address}`);
      lines.push(`    Permissions: ${member.permissions.join(", ")}`);
    }
  }

  lines.push("");
  lines.push(`Timestamp: ${result.timestamp}`);
  lines.push(divider);

  return lines.join("\n");
}

/**
 * Format a single verification result as markdown
 */
export function formatMarkdown(result: VerificationResult): string {
  const lines: string[] = [];

  const name = result.program.programName || result.program.programId;
  lines.push(`# ${name} - Multisig Verification`);
  lines.push("");
  lines.push(`**Verification Date:** ${result.timestamp}`);
  lines.push("");

  // Summary Box
  if (result.multisig) {
    const hasTimelock = result.multisig.timeLockSeconds > 0;
    lines.push("## Summary");
    lines.push("");
    lines.push("| Property | Value |");
    lines.push("|----------|-------|");
    lines.push(`| Threshold | **${result.multisig.thresholdDisplay}** |`);
    lines.push(`| Timelock | **${result.multisig.timeLockDisplay}** ${hasTimelock ? "✅" : "⚠️"} |`);
    lines.push(`| Upgradeable | ${result.program.isUpgradeable ? "Yes" : "No"} |`);
    lines.push("");
  }

  // Program Info
  lines.push("## Program Information");
  lines.push("");
  lines.push(`- **Program ID:** \`${result.program.programId}\``);
  lines.push(`- **ProgramData Address:** \`${result.program.programDataAddress}\``);
  lines.push(`- **Upgrade Authority:** \`${result.program.upgradeAuthority || "None (Immutable)"}\``);
  lines.push("");

  if (result.error) {
    lines.push("## ⚠️ Error");
    lines.push("");
    lines.push(`> ${result.error}`);
    lines.push("");
    return lines.join("\n");
  }

  // Vault Info
  if (result.vault && result.vault.parentMultisig) {
    lines.push("## Vault Information");
    lines.push("");
    lines.push(`- **Vault Address:** \`${result.vault.vaultAddress}\``);
    lines.push(`- **Parent Multisig:** \`${result.vault.parentMultisig}\``);
    if (result.vault.vaultIndex !== null) {
      lines.push(`- **Vault Index:** ${result.vault.vaultIndex}`);
    }
    lines.push("");
  }

  // Multisig Details
  if (result.multisig) {
    lines.push("## Multisig Configuration");
    lines.push("");
    lines.push(`- **Multisig Address:** \`${result.multisig.address}\``);
    lines.push(`- **Threshold:** ${result.multisig.thresholdDisplay}`);
    lines.push(`- **Timelock:** ${result.multisig.timeLockDisplay} (${result.multisig.timeLockSeconds} seconds)`);
    lines.push(`- **Create Key:** \`${result.multisig.createKey}\``);
    if (result.multisig.configAuthority) {
      lines.push(`- **Config Authority:** \`${result.multisig.configAuthority}\``);
    }
    lines.push("");

    lines.push("## Members");
    lines.push("");
    lines.push("| Address | Permissions |");
    lines.push("|---------|-------------|");
    for (const member of result.multisig.members) {
      lines.push(`| \`${member.address}\` | ${member.permissions.join(", ")} |`);
    }
    lines.push("");
  }

  return lines.join("\n");
}

/**
 * Format as JSON
 */
export function formatJSON(result: VerificationResult, pretty = true): string {
  return pretty ? JSON.stringify(result, null, 2) : JSON.stringify(result);
}

/**
 * Format a compact one-line summary
 */
export function formatCompact(result: VerificationResult): string {
  const name = result.program.programName || result.program.programId.slice(0, 8) + "...";

  if (result.error) {
    return `❌ ${name}: ${result.error}`;
  }

  if (result.multisig) {
    const timelockIcon = result.multisig.timeLockSeconds > 0 ? "✅" : "⚠️";
    return `${timelockIcon} ${name}: ${result.multisig.thresholdDisplay} | Timelock: ${result.multisig.timeLockDisplay}`;
  }

  return `⚠️ ${name}: No multisig found`;
}

/**
 * Format batch results as a summary table
 */
export function formatBatchSummary(batch: BatchVerificationResult): string {
  const lines: string[] = [];

  lines.push("═".repeat(90));
  lines.push("SQUADS MULTISIG VERIFICATION SUMMARY");
  lines.push("═".repeat(90));
  lines.push("");
  lines.push(`Total Programs: ${batch.summary.total}`);
  lines.push(`Successful:     ${batch.summary.successful}`);
  lines.push(`Failed:         ${batch.summary.failed}`);
  lines.push(`With Timelock:  ${batch.summary.withTimelock}`);
  lines.push(`No Timelock:    ${batch.summary.withoutTimelock}`);
  lines.push("");
  lines.push("─".repeat(90));
  lines.push(
    "Program".padEnd(20) +
    "Threshold".padEnd(15) +
    "Timelock".padEnd(20) +
    "Status"
  );
  lines.push("─".repeat(90));

  for (const result of batch.results) {
    const name = (result.program.programName || result.program.programId.slice(0, 16)).padEnd(20);

    if (result.error) {
      lines.push(`${name}${"N/A".padEnd(15)}${"N/A".padEnd(20)}❌ ${result.error.slice(0, 30)}`);
    } else if (result.multisig) {
      const threshold = result.multisig.thresholdDisplay.padEnd(15);
      const timelock = result.multisig.timeLockDisplay.padEnd(20);
      const status = result.multisig.timeLockSeconds > 0 ? "✅ OK" : "⚠️ NO TIMELOCK";
      lines.push(`${name}${threshold}${timelock}${status}`);
    } else {
      lines.push(`${name}${"N/A".padEnd(15)}${"N/A".padEnd(20)}⚠️ No multisig`);
    }
  }

  lines.push("─".repeat(90));
  lines.push(`Verification completed: ${batch.timestamp}`);
  lines.push("═".repeat(90));

  return lines.join("\n");
}
