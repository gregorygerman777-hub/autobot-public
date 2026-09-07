/**
 * Bridge to autobot_core (Python).
 *
 * Policy lives in Python so that the runtime enforcement, the cron scripts, and
 * the evaluation harness all share one implementation. This module only shells
 * out and parses; it deliberately contains no rules of its own.
 */

import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

export interface FenceResult {
  fenced: boolean;
  domain: string;
  source: string;
  content: string;
  nonce?: string;
  neutralized?: number;
  suspicious?: boolean;
  severity?: "none" | "low" | "high";
  signals?: string[];
  excerpts?: Record<string, string>;
}

export interface GuardResult {
  action: string;
  mode: string;
  decision: "allow" | "confirm" | "deny";
  allowed: boolean;
  reason: string;
}

/** Resolve an interpreter that satisfies the repo's >=3.12 requirement. */
function findPython(cwd: string): string {
  const venv = join(cwd, ".venv", "bin", "python");
  if (existsSync(venv)) return venv;
  for (const candidate of ["python3.13", "python3.12", "python3"]) {
    try {
      const version = execFileSync(candidate, ["-c", "import sys;print(sys.version_info[:2])"], {
        encoding: "utf-8",
        stdio: ["ignore", "pipe", "ignore"],
      }).trim();
      const match = version.match(/\((\d+),\s*(\d+)\)/);
      if (match && Number(match[1]) === 3 && Number(match[2]) >= 12) return candidate;
    } catch {
      // try the next candidate
    }
  }
  return "python3";
}

let cachedPython: string | null = null;

function python(cwd: string): string {
  if (!cachedPython) cachedPython = findPython(cwd);
  return cachedPython;
}

function run(cwd: string, args: string[], stdin?: string): string {
  return execFileSync(python(cwd), ["-m", "autobot_core.cli", ...args], {
    cwd,
    input: stdin,
    encoding: "utf-8",
    maxBuffer: 64 * 1024 * 1024,
    env: { ...process.env, PYTHONPATH: cwd },
  });
}

/**
 * Classify and, if untrusted, fence a tool result.
 * Returns null when the bridge is unavailable, so the caller can fail closed.
 */
export function fenceContent(
  cwd: string,
  toolName: string,
  toolInput: Record<string, unknown>,
  content: string,
): FenceResult | null {
  try {
    const out = run(
      cwd,
      ["fence", "--tool", toolName, "--input", JSON.stringify(toolInput ?? {})],
      content,
    );
    return JSON.parse(out) as FenceResult;
  } catch {
    return null;
  }
}

export function guardAction(
  cwd: string,
  action: string,
  opts: { untrusted: boolean; injection: boolean; target?: string },
): GuardResult | null {
  const args = ["guard", "--action", action];
  if (opts.untrusted) args.push("--untrusted");
  if (opts.injection) args.push("--injection");
  if (opts.target) args.push("--target", opts.target);
  try {
    return JSON.parse(run(cwd, args)) as GuardResult;
  } catch (err: unknown) {
    // Exit code 3 means DENY, which execFileSync throws on. Recover the body.
    const e = err as { stdout?: string };
    if (e?.stdout) {
      try {
        return JSON.parse(e.stdout) as GuardResult;
      } catch {
        return null;
      }
    }
    return null;
  }
}
