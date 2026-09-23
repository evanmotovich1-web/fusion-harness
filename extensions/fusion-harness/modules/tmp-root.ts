import * as fs from "node:fs";
import * as os from "node:os";

/**
 * Root for run artifacts and cross-run coordination (writer leases, vault locks, lanes).
 * Pinned to /tmp by default (os.tmpdir() on macOS is a per-user /var/folders path).
 * FH_TMP_ROOT overrides it: the eval loop gives each sandboxed run a private root, so a
 * run under test can neither see nor touch the leases and artifacts of anyone else's runs.
 */
export function tmpRoot(): string {
	const override = process.env.FH_TMP_ROOT;
	if (override) return override;
	return fs.existsSync("/tmp") ? "/tmp" : os.tmpdir();
}
