/**
 * knowledge-ingest.ts — governed write-back of an explicit durable Vault note.
 *
 * Only wiki/agent-learnings.md (interpretation lane). Never trading/, sessions/,
 * or agent-memory/. Capture is opt-in, idempotent by run id, secret-scanned, and
 * never git-commits the vault.
 */

import { createHash, randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { spawnSync } from "node:child_process";
import { DEFAULT_CAPTURE_RELATIVE } from "./knowledge-config.ts";

export interface KnowledgeCaptureResult {
	status: "captured" | "skipped" | "rejected" | "disabled";
	reason: string;
	dest?: string;
	runId: string;
	sync?: { ran: boolean; checkOk?: boolean; output?: string };
}

const EMPTY_NOTE_RE = /^(none|n\/a|na|no durable learning)(\s*[—\-].*)?$/i;
const SECRET_RE =
	/(api[_-]?key|secret|password|passwd|bearer\s+[a-z0-9._-]{8,}|sk-[a-z0-9]{8,}|AKIA[0-9A-Z]{8,}|-----BEGIN (?:RSA )?PRIVATE KEY-----|xox[baprs]-)/i;
const REFUSED_SEGMENTS = ["trading", "sessions", "agent-memory"];

function processAlive(pid: number): boolean {
	if (!Number.isInteger(pid) || pid <= 0) return false;
	try {
		process.kill(pid, 0);
		return true;
	} catch (error: any) {
		return error?.code === "EPERM";
	}
}

function canonical(p: string): string {
	try {
		return fs.realpathSync.native(p);
	} catch {
		return path.resolve(p);
	}
}

export function vaultLockPath(vaultRoot: string): string {
	const root = path.join(fs.existsSync("/tmp") ? "/tmp" : os.tmpdir(), "fusion-harness-vault-locks");
	const key = createHash("sha256").update(canonical(vaultRoot)).digest("hex").slice(0, 24);
	return path.join(root, `${key}.lock`);
}

export function acquireVaultLock(vaultRoot: string, ownerLabel: string): { path: string; owner: string; release(): void } {
	const lockPath = vaultLockPath(vaultRoot);
	fs.mkdirSync(path.dirname(lockPath), { recursive: true });
	const owner = `${process.pid}:${randomUUID()}:${ownerLabel}`;
	for (let attempt = 0; attempt < 2; attempt++) {
		try {
			const fd = fs.openSync(lockPath, "wx", 0o600);
			fs.writeFileSync(fd, JSON.stringify({ owner, pid: process.pid, command: ownerLabel, vault: canonical(vaultRoot), createdAt: Date.now() }));
			fs.closeSync(fd);
			return {
				path: lockPath,
				owner,
				release() {
					try {
						const current = JSON.parse(fs.readFileSync(lockPath, "utf8"));
						if (current.owner === owner) fs.unlinkSync(lockPath);
					} catch {
						/* already released */
					}
				},
			};
		} catch (error: any) {
			if (error?.code !== "EEXIST") throw error;
			let existing: any;
			try {
				existing = JSON.parse(fs.readFileSync(lockPath, "utf8"));
			} catch {}
			if (existing && processAlive(Number(existing.pid))) {
				throw new Error(`vault lock busy for ${canonical(vaultRoot)} — ${existing.command ?? existing.owner ?? `pid ${existing.pid}`} already holds it`);
			}
			try {
				fs.unlinkSync(lockPath);
			} catch {}
		}
	}
	throw new Error(`could not acquire vault lock for ${canonical(vaultRoot)}`);
}

export function extractVaultNote(text: string): string | undefined {
	const match = text.match(/^##[ \t]+Vault note[ \t]*\n([\s\S]*?)(?=^##[ \t]+|\s*$)/im);
	if (!match) return undefined;
	return match[1].trim();
}

export function extractVaultNotes(texts: string[]): string | undefined {
	for (const text of texts) {
		const note = extractVaultNote(text);
		if (note) return note;
	}
	return undefined;
}

function refusedLane(rel: string): string | undefined {
	const parts = rel.split(/[/\\]/).map((p) => p.toLowerCase());
	for (const seg of REFUSED_SEGMENTS) {
		if (parts.includes(seg)) return seg;
	}
	return undefined;
}

function atomicWrite(dest: string, body: string): void {
	fs.mkdirSync(path.dirname(dest), { recursive: true });
	const tmp = `${dest}.tmp-${process.pid}-${randomUUID()}`;
	fs.writeFileSync(tmp, body, { encoding: "utf8", mode: 0o644 });
	fs.renameSync(tmp, dest);
}

function maybeSync(vaultRoot: string): KnowledgeCaptureResult["sync"] {
	const script = path.join(vaultRoot, "scripts", "llmwiki_sync.py");
	if (!fs.existsSync(script)) return { ran: false, output: "llmwiki_sync.py not present" };
	const run = spawnSync("python3", [script], { cwd: vaultRoot, encoding: "utf8", timeout: 120_000 });
	const check = spawnSync("python3", [script, "--check"], { cwd: vaultRoot, encoding: "utf8", timeout: 120_000 });
	return {
		ran: true,
		checkOk: check.status === 0,
		output: [run.stdout, run.stderr, check.stdout, check.stderr].filter(Boolean).join("\n").slice(0, 4_000),
	};
}

export function captureVaultNote(opts: {
	enabled: boolean;
	vaultRoot?: string;
	runId: string;
	texts: string[];
	destRelative?: string;
	ownerLabel?: string;
	sync?: boolean;
}): KnowledgeCaptureResult {
	const runId = opts.runId;
	if (!opts.enabled) return { status: "disabled", reason: "capture opt-in is off", runId };
	if (!opts.vaultRoot) return { status: "skipped", reason: "no second-brain vault configured", runId };
	const rel = (opts.destRelative ?? DEFAULT_CAPTURE_RELATIVE).replace(/^[./]+/, "");
	const lane = refusedLane(rel);
	if (lane) return { status: "rejected", reason: `refused evidence lane ${lane}/`, runId, dest: rel };
	const note = extractVaultNotes(opts.texts);
	if (!note) return { status: "skipped", reason: "no ## Vault note in write-capable output", runId };
	if (!note.trim() || EMPTY_NOTE_RE.test(note.trim())) return { status: "rejected", reason: "empty or non-durable vault note", runId };
	if (SECRET_RE.test(note)) return { status: "rejected", reason: "credential-like vault note rejected", runId };

	const dest = path.join(opts.vaultRoot, rel);
	const marker = `<!-- agent-run:${runId} -->`;
	let lock: { release(): void } | undefined;
	try {
		lock = acquireVaultLock(opts.vaultRoot, opts.ownerLabel ?? `knowledge-capture ${runId}`);
		let existing = "";
		try {
			existing = fs.readFileSync(dest, "utf8");
		} catch {
			existing = "";
		}
		if (existing.includes(marker)) {
			return { status: "captured", reason: "idempotent — run marker already present", runId, dest };
		}
		const stamp = new Date().toISOString().slice(0, 10);
		const block = [
			"",
			marker,
			`### ${stamp} · fusion-harness run \`${runId}\``,
			"",
			note.trim(),
			"",
		].join("\n");
		const next = existing.trimEnd() ? `${existing.trimEnd()}\n${block}` : `# Agent learnings\n\nHarness-captured durable notes. Interpretation lane only.\n${block}`;
		atomicWrite(dest, `${next.trimEnd()}\n`);
		const sync = opts.sync === false ? { ran: false, output: "sync skipped" } : maybeSync(opts.vaultRoot);
		return { status: "captured", reason: "appended vault note", runId, dest, sync };
	} catch (error) {
		return { status: "rejected", reason: error instanceof Error ? error.message : String(error), runId, dest };
	} finally {
		lock?.release();
	}
}
