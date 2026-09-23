import { afterEach, describe, expect, test } from "bun:test";
import { tmpRoot } from "../modules/tmp-root.ts";
import { writerLeasePath } from "../modules/writer-lease.ts";

const saved = process.env.FH_TMP_ROOT;
afterEach(() => { if (saved === undefined) delete process.env.FH_TMP_ROOT; else process.env.FH_TMP_ROOT = saved; });

describe("tmpRoot", () => {
	test("defaults to /tmp", () => {
		delete process.env.FH_TMP_ROOT;
		expect(tmpRoot()).toBe("/tmp");
	});
	test("FH_TMP_ROOT moves artifacts and leases into a private root (the eval loop's sandboxed runs)", () => {
		process.env.FH_TMP_ROOT = "/private/tmp/fh-eval-root-x/fh";
		expect(tmpRoot()).toBe("/private/tmp/fh-eval-root-x/fh");
		expect(writerLeasePath("/some/repo").startsWith("/private/tmp/fh-eval-root-x/fh/fusion-harness-writer-locks/")).toBe(true);
	});
});
