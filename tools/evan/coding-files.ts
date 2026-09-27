import * as fs from "node:fs";
import * as path from "node:path";
import { createHash, randomUUID } from "node:crypto";

export const CODING_TOOLS = ["evan_read_file", "evan_write_file"] as const;
export type FileGrant = { root: string; readPaths: string[]; writePaths: string[]; protectedRoots: string[]; maxFileBytes: number; maxToolCalls: number };
export type FileChange = { path: string; before: string | null; after: string };
export type FileEvent = { tool: string; path: string | null; outcome: "started" | "succeeded" | "denied"; change?: FileChange };
export const fileHash = (bytes: string | Buffer): string => createHash("sha256").update(bytes).digest("hex");

const within = (root: string, candidate: string) => candidate === root || candidate.startsWith(root + path.sep);
const protectedName = (part: string) => part.startsWith(".") || /^(agents(?:\.override)?\.md|claude\.md|auth\.json|credentials(?:\..*)?|secrets?(?:\..*)?|.*\.(?:pem|key|p12|pfx))$/i.test(part);

/** Exact regular-file grants, no globs, directories, links, shell or network. Not an OS sandbox. */
export function createCodingFiles(grant: FileGrant, signal: AbortSignal, record: (event: FileEvent) => void) {
  const root = fs.realpathSync(grant.root);
  const protectedRoots = grant.protectedRoots.map((p) => fs.existsSync(p) ? fs.realpathSync(p) : path.resolve(p));
  const names = (values: string[]) => new Set(values.map((value) => {
    if (typeof value !== "string" || !value || value.length > 1024 || /[\x00-\x1f\\]/.test(value) || path.isAbsolute(value)) throw new Error("Invalid relative file grant");
    const parts = value.split("/");
    if (parts.some((part) => !part || part === "." || part === ".." || protectedName(part))) throw new Error("Protected or non-canonical file path");
    const target = path.resolve(root, value);
    if (!within(root, target) || protectedRoots.some((p) => within(p, target))) throw new Error("File grant overlaps protected application state");
    return value;
  }));
  const writes = names(grant.writePaths);
  const reads = names([...grant.readPaths, ...grant.writePaths]);
  const changed = new Map<string, FileChange>();
  let calls = 0;
  let sealed = false;
  let fault = false;
  const check = () => {
    signal.throwIfAborted();
    if (sealed || fault) throw new Error("Coding file capability is closed");
  };
  function locate(name: unknown, writing: boolean): string {
    if (typeof name !== "string" || !(writing ? writes : reads).has(name)) throw new Error("File is outside the explicit grant");
    let cursor = root;
    const parts = name.split("/");
    for (let i = 0; i < parts.length; i++) {
      cursor = path.join(cursor, parts[i]!);
      let stat: fs.Stats;
      try { stat = fs.lstatSync(cursor); }
      catch (error: any) {
        if (error.code === "ENOENT" && writing && i === parts.length - 1) return cursor;
        throw error;
      }
      if (stat.isSymbolicLink()) throw new Error("Symlink paths are unavailable");
      if (i < parts.length - 1) {
        if (!stat.isDirectory()) throw new Error("File parent must be an existing directory");
      } else if (!stat.isFile() || stat.nlink !== 1) throw new Error("Only single-link regular files are available");
    }
    return cursor;
  }
  function readBytes(target: string): Buffer {
    const fd = fs.openSync(target, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
    try {
      const stat = fs.fstatSync(fd);
      if (!stat.isFile() || stat.nlink !== 1 || stat.size > grant.maxFileBytes) throw new Error("File type or byte limit refused");
      // Bounded read even if an external editor grows the file after fstat.
      const buffer = Buffer.alloc(grant.maxFileBytes + 1);
      const count = fs.readSync(fd, buffer, 0, buffer.length, 0);
      if (count > grant.maxFileBytes) throw new Error("File byte limit exceeded");
      return buffer.subarray(0, count);
    } finally { fs.closeSync(fd); }
  }
  function currentHash(target: string): string | null {
    try { return fileHash(readBytes(target)); }
    catch (error: any) { if (error.code === "ENOENT") return null; throw error; }
  }
  // Validate existing parents/targets before dispatch, not just on the first model tool call.
  for (const name of reads) locate(name, writes.has(name));
  return {
    paths: { read: [...reads], write: [...writes] },
    get faulted() { return fault; },
    seal() { sealed = true; },
    changes(): FileChange[] { return [...changed.values()].map((change) => ({ ...change })); },
    verify(): boolean {
      return [...changed.values()].every((change) => {
        try { return fileHash(readBytes(locate(change.path, false))) === change.after; } catch { return false; }
      });
    },
    invoke(tool: string, raw: unknown): unknown {
      check();
      const args = raw && typeof raw === "object" && !Array.isArray(raw) ? raw as Record<string, unknown> : {};
      const name = typeof args.path === "string" ? args.path : null;
      try {
        if (++calls > grant.maxToolCalls) throw new Error("Coding tool-call budget exceeded");
        if (!(CODING_TOOLS as readonly string[]).includes(tool)) throw new Error("Operation unavailable: shell, Git and messaging are not granted");
        const allowedKeys = tool === "evan_read_file" ? ["path"] : ["path", "content", "expectedHash"];
        if (Object.keys(args).some((key) => !allowedKeys.includes(key))) throw new Error("Unexpected tool arguments");
        record({ tool, path: name, outcome: "started" });
        check();
        const target = locate(name, tool === "evan_write_file");
        if (tool === "evan_read_file") {
          const bytes = readBytes(target);
          const content = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
          record({ tool, path: name, outcome: "succeeded" });
          return { path: name, content, sha256: fileHash(bytes) };
        }
        if (typeof args.content !== "string" || Buffer.byteLength(args.content) > grant.maxFileBytes) throw new Error("Write content byte limit refused");
        if (!(args.expectedHash === null || typeof args.expectedHash === "string" && /^[a-f0-9]{64}$/.test(args.expectedHash))) throw new Error("expectedHash must be the original SHA256, or null for a new file");
        const before = currentHash(target);
        if (before !== args.expectedHash) throw new Error("File changed or already exists; expectedHash does not match");
        const temp = path.join(path.dirname(target), `.evan-write-${randomUUID()}`);
        try {
          fs.writeFileSync(temp, args.content, { flag: "wx", mode: before === null ? 0o600 : fs.statSync(target).mode & 0o777 });
          check();
          locate(name, true);
          if (currentHash(target) !== before) throw new Error("File changed before replacement");
          if (before === null) fs.linkSync(temp, target); // Atomic no-clobber create.
          else fs.renameSync(temp, target); // Does not modify another hard-linked inode.
        } finally {
          try { fs.unlinkSync(temp); } catch (error: any) { if (error.code !== "ENOENT") throw error; }
        }
        const change = { path: name!, before: changed.get(name!)?.before ?? before, after: fileHash(args.content) };
        // Preserve null (created file) across subsequent writes.
        if (changed.has(name!)) change.before = changed.get(name!)!.before;
        changed.set(name!, change);
        if (currentHash(target) !== change.after) throw new Error("Written content failed independent readback");
        record({ tool, path: name, outcome: "succeeded", change });
        return { path: name, sha256: change.after, verified: "file-readback", tests: "not-run" };
      } catch (error) {
        fault = true; // A denied operation cannot be hidden by a later successful model answer.
        record({ tool, path: name, outcome: "denied" });
        throw error;
      }
    },
  };
}
