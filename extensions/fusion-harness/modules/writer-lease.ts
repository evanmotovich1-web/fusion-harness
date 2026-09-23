import { createHash, randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { tmpRoot } from "./tmp-root";

export interface WriterLease {
	path: string;
	owner: string;
	release(): void;
}

function processAlive(pid: number): boolean {
	if (!Number.isInteger(pid) || pid <= 0) return false;
	try {
		process.kill(pid, 0);
		return true;
	} catch (error: any) {
		return error?.code === "EPERM";
	}
}

function canonicalCwd(cwd: string): string {
	try { return fs.realpathSync.native(cwd); } catch { return path.resolve(cwd); }
}

export function writerLeasePath(cwd: string): string {
	const root = path.join(tmpRoot(), "fusion-harness-writer-locks");
	const key = createHash("sha256").update(canonicalCwd(cwd)).digest("hex").slice(0, 24);
	return path.join(root, `${key}.lock`);
}

export function acquireWriterLease(cwd: string, ownerLabel: string): WriterLease {
	const lockPath = writerLeasePath(cwd);
	fs.mkdirSync(path.dirname(lockPath), { recursive: true });
	const owner = `${process.pid}:${randomUUID()}:${ownerLabel}`;
	for (let attempt = 0; attempt < 2; attempt++) {
		try {
			const fd = fs.openSync(lockPath, "wx", 0o600);
			fs.writeFileSync(fd, JSON.stringify({ owner, pid: process.pid, command: ownerLabel, cwd: canonicalCwd(cwd), createdAt: Date.now() }));
			fs.closeSync(fd);
			return {
				path: lockPath,
				owner,
				release() {
					try {
						const current = JSON.parse(fs.readFileSync(lockPath, "utf8"));
						if (current.owner === owner) fs.unlinkSync(lockPath);
					} catch {
						/* already released/replaced */
					}
				},
			};
		} catch (error: any) {
			if (error?.code !== "EEXIST") throw error;
			let existing: any;
			try { existing = JSON.parse(fs.readFileSync(lockPath, "utf8")); } catch {}
			if (existing && processAlive(Number(existing.pid))) {
				throw new Error(`writer lease busy for ${canonicalCwd(cwd)} — ${existing.command ?? existing.owner ?? `pid ${existing.pid}`} is already allowed to mutate this checkout`);
			}
			try { fs.unlinkSync(lockPath); } catch {}
		}
	}
	throw new Error(`could not acquire writer lease for ${canonicalCwd(cwd)}`);
}

export function isWriterLeaseBusy(error: unknown): boolean {
	return error instanceof Error && error.message.startsWith("writer lease busy");
}

/**
 * Queue for the checkout instead of failing: a second write-capable run waits
 * until the live holder releases (a dead holder is reclaimed immediately by
 * acquireWriterLease). No deadline — only the caller's stop signal ends the wait.
 */
export async function waitForWriterLease(
	cwd: string,
	ownerLabel: string,
	opts: { signal?: AbortSignal; pollMs?: number; onWait?: (holder: string) => void } = {},
): Promise<WriterLease> {
	let announced = false;
	for (;;) {
		try {
			return acquireWriterLease(cwd, ownerLabel);
		} catch (error) {
			if (!isWriterLeaseBusy(error)) throw error;
			if (!announced) {
				announced = true;
				opts.onWait?.((error as Error).message);
			}
		}
		if (opts.signal?.aborted) throw new Error(`stopped while waiting for the writer lease on ${canonicalCwd(cwd)}`);
		await new Promise<void>((resolve) => {
			const timer = setTimeout(resolve, opts.pollMs ?? 5_000);
			opts.signal?.addEventListener("abort", () => { clearTimeout(timer); resolve(); }, { once: true });
		});
	}
}
