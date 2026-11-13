/**
 * Dependency vulnerability scan (requirement 12.5): OSV-Scanner over every lockfile in the
 * repository (pnpm, uv, Cargo). Every finding is listed; the scan fails only for a high or
 * critical one (CVSS 7.0 or more) that a newer version fixes, since only those have an action.
 *
 * Run with `make audit`. It needs the network (osv.dev), so it is a CI step rather than part of
 * `pnpm check`.
 */
import { spawnSync } from "node:child_process";

interface Affected {
  package?: { name?: string; ecosystem?: string };
  ranges?: { events?: { fixed?: string }[] }[];
}
interface Vulnerability {
  id: string;
  summary?: string;
  affected?: Affected[];
}
interface Group {
  ids: string[];
  max_severity?: string;
}
interface PackageResult {
  package: { name: string; version: string; ecosystem: string };
  vulnerabilities?: Vulnerability[];
  groups?: Group[];
}
interface Report {
  results?: { source: { path: string }; packages: PackageResult[] }[];
}

const HIGH = 7.0;

const scan = spawnSync("osv-scanner", ["scan", "source", "--recursive", "--format", "json", "."], {
  encoding: "utf8",
  maxBuffer: 256 * 1024 * 1024,
});
// Exit 0: nothing found. 1: vulnerabilities found. Anything else: the scan itself failed.
if (scan.status !== 0 && scan.status !== 1) {
  process.stderr.write(scan.stderr);
  throw new Error(`osv-scanner failed with exit code ${scan.status}`);
}
const report = JSON.parse(scan.stdout) as Report;

function fixedVersions(vulns: Vulnerability[], name: string): string[] {
  const fixed = new Set<string>();
  for (const v of vulns) {
    for (const a of v.affected ?? []) {
      if (a.package?.name !== name) continue;
      for (const r of a.ranges ?? []) {
        for (const e of r.events ?? []) if (e.fixed) fixed.add(e.fixed);
      }
    }
  }
  return [...fixed];
}

const blocking: string[] = [];
let total = 0;
for (const result of report.results ?? []) {
  for (const p of result.packages) {
    const vulns = p.vulnerabilities ?? [];
    for (const group of p.groups ?? []) {
      total += 1;
      const score = Number(group.max_severity);
      const inGroup = vulns.filter((v) => group.ids.includes(v.id));
      const fixes = fixedVersions(inGroup, p.package.name);
      const summary = inGroup.find((v) => v.summary)?.summary ?? "";
      const line = `${p.package.ecosystem} ${p.package.name}@${p.package.version}: ${group.ids[0]} (severity ${
        Number.isFinite(score) ? score.toFixed(1) : "unknown"
      }${fixes.length > 0 ? `, fixed in ${fixes.join(", ")}` : ", no fix yet"}) ${summary} [${result.source.path}]`;
      console.log(line);
      if (Number.isFinite(score) && score >= HIGH && fixes.length > 0) blocking.push(line);
    }
  }
}

if (blocking.length > 0) {
  console.error(`\nscan-dependencies: ${blocking.length} high-severity issue(s) with a fix:`);
  for (const line of blocking) console.error(`  ${line}`);
  console.error("Update those packages (or the dependency that pulls them in), then scan again.");
  process.exit(1);
}
console.log(`scan-dependencies: ${total} known issue(s), none high-severity with an available fix`);
