#!/usr/bin/env node

import { Command } from "commander";
import { Connection } from "@solana/web3.js";
import { verifyProgram, verifyMultisigDirect } from "./verifier";
import {
  formatTable,
  formatMarkdown,
  formatJSON,
  formatCompact,
  formatBatchSummary,
} from "./formatters";
import { VerificationResult, BatchVerificationResult } from "./types";
import * as fs from "fs";

const program = new Command();

program
  .name("squads-verifier")
  .description("Verify Squads multisig configuration for Solana programs")
  .version("1.0.0");

// Get RPC endpoint from env or use default
function getRpcEndpoint(options: { rpc?: string }): string {
  if (options.rpc) return options.rpc;
  if (process.env.HELIUS_API_KEY) {
    return `https://mainnet.helius-rpc.com/?api-key=${process.env.HELIUS_API_KEY}`;
  }
  if (process.env.SOLANA_RPC_URL) {
    return process.env.SOLANA_RPC_URL;
  }
  return "https://api.mainnet-beta.solana.com";
}

// Format output based on options
function formatOutput(
  result: VerificationResult,
  format: string
): string {
  switch (format) {
    case "json":
      return formatJSON(result);
    case "markdown":
    case "md":
      return formatMarkdown(result);
    case "compact":
      return formatCompact(result);
    case "table":
    default:
      return formatTable(result);
  }
}

// Verify a single program
program
  .command("program <programId>")
  .description("Verify multisig configuration for a program by its program ID")
  .option("-n, --name <name>", "Program name for display")
  .option("-r, --rpc <url>", "RPC endpoint URL")
  .option(
    "-f, --format <format>",
    "Output format: table, json, markdown, compact",
    "table"
  )
  .option("-o, --output <file>", "Write output to file")
  .action(async (programId: string, options) => {
    try {
      const rpcEndpoint = getRpcEndpoint(options);
      const connection = new Connection(rpcEndpoint, "confirmed");

      console.error(`Verifying program: ${programId}`);
      console.error(`Using RPC: ${rpcEndpoint.replace(/api-key=.*/, "api-key=***")}`);
      console.error("");

      const result = await verifyProgram(connection, programId, options.name);
      const output = formatOutput(result, options.format);

      if (options.output) {
        fs.writeFileSync(options.output, output);
        console.error(`Output written to: ${options.output}`);
      } else {
        console.log(output);
      }

      // Exit with error code if verification failed
      if (result.error) {
        process.exit(1);
      }
    } catch (error) {
      console.error("Error:", error instanceof Error ? error.message : error);
      process.exit(1);
    }
  });

// Verify a multisig directly
program
  .command("multisig <address>")
  .description("Analyze a Squads multisig account directly by address")
  .option("-r, --rpc <url>", "RPC endpoint URL")
  .option("-f, --format <format>", "Output format: table, json", "table")
  .option("-o, --output <file>", "Write output to file")
  .action(async (address: string, options) => {
    try {
      const rpcEndpoint = getRpcEndpoint(options);
      const connection = new Connection(rpcEndpoint, "confirmed");

      console.error(`Analyzing multisig: ${address}`);
      console.error(`Using RPC: ${rpcEndpoint.replace(/api-key=.*/, "api-key=***")}`);
      console.error("");

      const result = await verifyMultisigDirect(connection, address);

      let output: string;
      if (options.format === "json") {
        output = JSON.stringify(result, null, 2);
      } else {
        const lines: string[] = [];
        lines.push("─".repeat(70));
        lines.push(`MULTISIG: ${result.address}`);
        lines.push("─".repeat(70));
        lines.push(`Threshold:          ${result.thresholdDisplay}`);
        lines.push(`Timelock:           ${result.timeLockDisplay}`);
        lines.push(`Timelock (seconds): ${result.timeLockSeconds}`);
        lines.push(`Create Key:         ${result.createKey}`);
        if (result.configAuthority) {
          lines.push(`Config Authority:   ${result.configAuthority}`);
        }
        lines.push("");
        lines.push("Members:");
        for (const member of result.members) {
          lines.push(`  ${member.address}`);
          lines.push(`    Permissions: ${member.permissions.join(", ")}`);
        }
        lines.push("─".repeat(70));
        output = lines.join("\n");
      }

      if (options.output) {
        fs.writeFileSync(options.output, output);
        console.error(`Output written to: ${options.output}`);
      } else {
        console.log(output);
      }
    } catch (error) {
      console.error("Error:", error instanceof Error ? error.message : error);
      process.exit(1);
    }
  });

// Batch verify multiple programs
program
  .command("batch <file>")
  .description("Verify multiple programs from a JSON file")
  .option("-r, --rpc <url>", "RPC endpoint URL")
  .option(
    "-f, --format <format>",
    "Output format: summary, json, markdown",
    "summary"
  )
  .option("-o, --output <file>", "Write output to file")
  .action(async (file: string, options) => {
    try {
      const rpcEndpoint = getRpcEndpoint(options);
      const connection = new Connection(rpcEndpoint, "confirmed");

      console.error(`Reading programs from: ${file}`);
      console.error(`Using RPC: ${rpcEndpoint.replace(/api-key=.*/, "api-key=***")}`);
      console.error("");

      const fileContent = fs.readFileSync(file, "utf-8");
      const programs: Array<{ programId: string; name?: string }> =
        JSON.parse(fileContent);

      const results: VerificationResult[] = [];
      let withTimelock = 0;
      let withoutTimelock = 0;
      let failed = 0;

      for (const prog of programs) {
        console.error(`Verifying: ${prog.name || prog.programId}...`);
        const result = await verifyProgram(
          connection,
          prog.programId,
          prog.name
        );
        results.push(result);

        if (result.error) {
          failed++;
        } else if (result.multisig) {
          if (result.multisig.timeLockSeconds > 0) {
            withTimelock++;
          } else {
            withoutTimelock++;
          }
        }
      }

      const batch: BatchVerificationResult = {
        results,
        summary: {
          total: programs.length,
          successful: programs.length - failed,
          failed,
          withTimelock,
          withoutTimelock,
        },
        timestamp: new Date().toISOString(),
      };

      let output: string;
      switch (options.format) {
        case "json":
          output = JSON.stringify(batch, null, 2);
          break;
        case "markdown":
        case "md":
          output = results.map((r) => formatMarkdown(r)).join("\n\n---\n\n");
          break;
        case "summary":
        default:
          output = formatBatchSummary(batch);
      }

      if (options.output) {
        fs.writeFileSync(options.output, output);
        console.error(`\nOutput written to: ${options.output}`);
      } else {
        console.log(output);
      }
    } catch (error) {
      console.error("Error:", error instanceof Error ? error.message : error);
      process.exit(1);
    }
  });

// List well-known programs
program
  .command("list-known")
  .description("List well-known Solana DeFi programs")
  .action(() => {
    const knownPrograms = [
      { programId: "KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD", name: "Klend (Kamino Lend)" },
      { programId: "dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH", name: "Drift Protocol" },
      { programId: "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4", name: "Jupiter v6" },
      { programId: "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc", name: "Orca Whirlpools" },
      { programId: "MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FZnsebVacA", name: "Marginfi" },
      { programId: "So1endDq2YkqhipRh3WViPa8hdiSpxWy6z3Z6tMCpAo", name: "Solend" },
      { programId: "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK", name: "Raydium CLMM" },
      { programId: "PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY", name: "Phoenix" },
    ];

    console.log("Well-known Solana DeFi Programs:");
    console.log("─".repeat(70));
    console.log("Name".padEnd(25) + "Program ID");
    console.log("─".repeat(70));
    for (const p of knownPrograms) {
      console.log(`${p.name.padEnd(25)}${p.programId}`);
    }
    console.log("─".repeat(70));
    console.log("\nTo verify a program:");
    console.log("  npx ts-node src/cli.ts program <programId> --name <name>");
  });

program.parse();
