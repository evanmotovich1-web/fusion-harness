import { afterAll, describe, expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, existsSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
	CONTRACT_BEGIN,
	CONTRACT_END,
	KNOWLEDGE_INSTALL_JSON_KEYS,
	SURFACE_JSON_KEYS,
	adwSurfacesFor,
	currentBlockOf,
	extractContractBody,
	findSystemPrompts,
	lineDiff,
	renderContractBlock,
	runKnowledgeInstall,
	sha256,
} from "../tools/knowledge-install.ts";

const toolPath = join(import.meta.dir, "..", "tools", "knowledge-install.ts");
const contractPath = join(import.meta.dir, "..", "prompts", "KNOWLEDGE_GLOBAL_CONTRACT.md");
const block = renderContractBlock(extractContractBody(readFileSync(contractPath, "utf8")));

const homes: string[] = [];
function tempHome(): string {
	const home = mkdtempSync(join(tmpdir(), "fh-knowledge-install-"));
	homes.push(home);
	return home;
}

afterAll(() => {
	for (const home of homes) rmSync(home, { recursive: true, force: true });
});

function seed(home: string): { root: string; claude: string; rootText: string; claudeText: string } {
	const root = join(home, "AGENTS.md");
	const claude = join(home, ".claude", "CLAUDE.md");
	const rootText = "# Root rules\n\nKeep me.\n";
	const claudeText = "User claude text";
	writeFileSync(root, rootText, "utf8");
	mkdirSync(join(home, ".claude"), { recursive: true });
	writeFileSync(claude, claudeText, "utf8");
	return { root, claude, rootText, claudeText };
}

describe("knowledge-install dry run", () => {
	test("writes nothing and reports absent/missing surfaces", () => {
		const home = tempHome();
		const { root, claude, rootText, claudeText } = seed(home);
		const result = runKnowledgeInstall(["--home", home]);
		expect(result.exitCode).toBe(0);
		expect(readFileSync(root, "utf8")).toBe(rootText);
		expect(readFileSync(claude, "utf8")).toBe(claudeText);
		expect(existsSync(join(home, ".fh-knowledge"))).toBe(false);
		const map = new Map(result.report.surfaces.map((surface) => [surface.id, surface]));
		expect(map.get("root")?.status).toBe("missing");
		expect(map.get("claude")?.status).toBe("missing");
		expect(map.get("pi")?.status).toBe("absent");
		expect(map.get("adw")?.status).toBe("skipped");
		expect(result.report.contractHash).toBe(sha256(block));
	});

	test("--help exits 0", () => {
		const result = runKnowledgeInstall(["--help"]);
		expect(result.exitCode).toBe(0);
		expect(result.stdout).toContain("knowledge-install");
		expect(result.stdout).toContain("fail-open");
	});
});

describe("knowledge-install apply", () => {
	test("installs the marker block, preserves user text, and records a manifest", () => {
		const home = tempHome();
		const { root, claude, rootText, claudeText } = seed(home);
		const result = runKnowledgeInstall(["--home", home, "--apply"]);
		expect(result.exitCode).toBe(0);

		const rootInstalled = readFileSync(root, "utf8");
		const claudeInstalled = readFileSync(claude, "utf8");
		expect(rootInstalled).toBe(`${rootText}\n${block}\n`);
		expect(claudeInstalled).toBe(`${claudeText}\n\n${block}\n`);
		expect(currentBlockOf(rootInstalled)).toBe(block);
		expect((rootInstalled.match(/fh-knowledge:begin/g) ?? []).length).toBe(1);
		expect(rootInstalled.startsWith(rootText)).toBe(true);

		for (const relative of [".pi/agent/AGENTS.md", ".codex/AGENTS.md", ".hermes/SOUL.md"]) {
			expect(readFileSync(join(home, relative), "utf8")).toBe(`${block}\n`);
		}

		const manifest = JSON.parse(readFileSync(join(home, ".fh-knowledge", "manifest.json"), "utf8"));
		expect(manifest.version).toBe(1);
		expect(manifest.contractHash).toBe(sha256(block));
		expect(manifest.entries.map((entry: any) => entry.id).sort()).toEqual(["claude", "codex", "hermes", "pi", "root"]);
		const rootEntry = manifest.entries.find((entry: any) => entry.id === "root");
		expect(rootEntry.originalHash).toBe(sha256(rootText));
		expect(rootEntry.createdByUs).toBe(false);
		const piEntry = manifest.entries.find((entry: any) => entry.id === "pi");
		expect(piEntry.createdByUs).toBe(true);
	});

	test("second apply is idempotent: current, unchanged, byte-identical", () => {
		const home = tempHome();
		const { root } = seed(home);
		runKnowledgeInstall(["--home", home, "--apply"]);
		const first = readFileSync(root, "utf8");
		const second = runKnowledgeInstall(["--home", home, "--apply", "--json"]);
		expect(second.exitCode).toBe(0);
		expect(readFileSync(root, "utf8")).toBe(first);
		const parsed = JSON.parse(second.stdout);
		const rootResult = parsed.surfaces.find((surface: any) => surface.id === "root");
		expect(rootResult.status).toBe("current");
		expect(rootResult.changed).toBe(false);
	});

	test("--check reports current with an empty diff, then stale with a diff", () => {
		const home = tempHome();
		const { root } = seed(home);
		runKnowledgeInstall(["--home", home, "--apply"]);
		const clean = runKnowledgeInstall(["--home", home, "--check", "--json"]);
		const cleanRoot = JSON.parse(clean.stdout).surfaces.find((surface: any) => surface.id === "root");
		expect(cleanRoot.status).toBe("current");
		expect(cleanRoot.diff).toBe("");

		writeFileSync(root, readFileSync(root, "utf8").replace(CONTRACT_END, `drifted line\n${CONTRACT_END}`), "utf8");
		const stale = runKnowledgeInstall(["--home", home, "--check", "--json"]);
		const staleRoot = JSON.parse(stale.stdout).surfaces.find((surface: any) => surface.id === "root");
		expect(staleRoot.status).toBe("stale");
		expect(staleRoot.diff.length).toBeGreaterThan(0);
		expect(staleRoot.diff).toContain("+ drifted line");
	});
});

describe("knowledge-install uninstall", () => {
	test("dry run removes nothing", () => {
		const home = tempHome();
		const { root } = seed(home);
		runKnowledgeInstall(["--home", home, "--apply"]);
		const installed = readFileSync(root, "utf8");
		const plan = runKnowledgeInstall(["--home", home, "--uninstall"]);
		expect(plan.exitCode).toBe(0);
		expect(readFileSync(root, "utf8")).toBe(installed);
		expect(plan.report.surfaces.find((surface) => surface.id === "root")?.status).toBe("would-uninstall");
	});

	test("restores byte-identical originals and deletes files it created", () => {
		const home = tempHome();
		const { root, claude, rootText, claudeText } = seed(home);
		const pi = join(home, ".pi", "agent", "AGENTS.md");
		runKnowledgeInstall(["--home", home, "--apply"]);
		expect(existsSync(pi)).toBe(true);

		const result = runKnowledgeInstall(["--home", home, "--uninstall", "--apply"]);
		expect(result.exitCode).toBe(0);
		expect(readFileSync(root, "utf8")).toBe(rootText);
		expect(readFileSync(claude, "utf8")).toBe(claudeText);
		expect(existsSync(pi)).toBe(false);
		expect(readFileSync(root, "utf8").includes(CONTRACT_BEGIN)).toBe(false);
		expect(existsSync(join(home, ".fh-knowledge", "manifest.json"))).toBe(false);
		const map = new Map(result.report.surfaces.map((surface) => [surface.id, surface]));
		expect(map.get("root")?.status).toBe("restored");
		expect(map.get("claude")?.status).toBe("restored");
		expect(map.get("pi")?.status).toBe("restored");
	});

	test("keeps user edits made outside the block and reports restored-with-edits", () => {
		const home = tempHome();
		const { root } = seed(home);
		runKnowledgeInstall(["--home", home, "--apply"]);
		writeFileSync(root, `${readFileSync(root, "utf8")}\nuser added after install\n`, "utf8");
		const result = runKnowledgeInstall(["--home", home, "--uninstall", "--apply"]);
		const content = readFileSync(root, "utf8");
		expect(content.includes("user added after install")).toBe(true);
		expect(content.includes(CONTRACT_BEGIN)).toBe(false);
		expect(result.report.surfaces.find((surface) => surface.id === "root")?.status).toBe("restored-with-edits");
	});
});

describe("knowledge-install ADW surface", () => {
	test("is skipped without both flags and installed only with --adw-path and --allow-adw", () => {
		const home = tempHome();
		const adw = join(home, "planner-prompt.md");
		writeFileSync(adw, "# planner\n", "utf8");

		const skipped = runKnowledgeInstall(["--home", home, "--adw-path", adw, "--apply"]);
		expect(skipped.report.surfaces.find((surface) => surface.id === "adw")?.status).toBe("skipped");
		expect(readFileSync(adw, "utf8")).toBe("# planner\n");

		const enabled = runKnowledgeInstall(["--home", home, "--adw-path", adw, "--allow-adw", "--apply"]);
		expect(enabled.report.surfaces.find((surface) => surface.id === "adw")?.status).toBe("current");
		expect(readFileSync(adw, "utf8")).toContain(CONTRACT_BEGIN);
		expect(readFileSync(adw, "utf8").startsWith("# planner\n")).toBe(true);

		const removed = runKnowledgeInstall(["--home", home, "--adw-path", adw, "--allow-adw", "--uninstall", "--apply"]);
		expect(removed.report.surfaces.find((surface) => surface.id === "adw")?.status).toBe("restored");
		expect(readFileSync(adw, "utf8")).toBe("# planner\n");
	});
});

describe("knowledge-install safety", () => {
	test("refuses to write the real home without --allow-real-home", () => {
		const realHome = process.env.HOME ?? "";
		const manifestPath = join(realHome, ".fh-knowledge", "manifest.json");
		// Do not assert the machine is uninstalled: the real home may legitimately carry an
		// install. Assert the refusal changed nothing (the manifest is byte-identical before
		// and after, or stays absent). Sandboxed runs (the eval loop's fix/test profiles allow
		// metadata but deny reading the real home) cannot read the manifest at all; there the
		// witness reads return undefined before and after, so the refusal itself is still
		// fully asserted while byte identity stays unverifiable — not silently presumed.
		const witness = (): string | null | undefined => {
			try {
				return existsSync(manifestPath) ? readFileSync(manifestPath, "utf8") : null;
			} catch {
				return undefined;
			}
		};
		const before = witness();
		const result = runKnowledgeInstall(["--home", realHome, "--apply", "--json"]);
		expect(result.exitCode).toBe(2);
		expect(result.stderr).toContain("--allow-real-home");
		expect(JSON.parse(result.stdout).applied).toBe(false);
		const after = witness();
		expect(after).toBe(before);
	});

	test("installs fail-open rules only and never a blocking hook", () => {
		const home = tempHome();
		seed(home);
		runKnowledgeInstall(["--home", home, "--apply"]);
		const installed = readFileSync(join(home, "AGENTS.md"), "utf8");
		expect(installed).toContain("must never block the task");
		expect(installed).not.toContain('"decision"');
		expect(installed).not.toContain('"permissionDecision"');
		expect(installed).not.toContain("fail_closed");
		// It writes instruction surfaces only; no settings.json and no hook file is touched.
		expect(existsSync(join(home, ".claude", "settings.json"))).toBe(false);
		expect(existsSync(join(home, ".pi", "agent", "extensions"))).toBe(false);
		const manifest = JSON.parse(readFileSync(join(home, ".fh-knowledge", "manifest.json"), "utf8"));
		for (const entry of manifest.entries) expect(entry.path).not.toContain("settings.json");
	});

	test("--json exits 0 with the frozen key order via the shim", () => {
		const home = tempHome();
		const run = spawnSync("bun", [toolPath, "--home", home, "--json"], { encoding: "utf8", timeout: 20_000 });
		expect(run.status).toBe(0);
		const report = JSON.parse(run.stdout);
		expect(Object.keys(report)).toEqual([...KNOWLEDGE_INSTALL_JSON_KEYS]);
		for (const surface of report.surfaces) expect(Object.keys(surface)).toEqual([...SURFACE_JSON_KEYS]);
	});

	test("lineDiff marks changed lines and is empty for identical input", () => {
		expect(lineDiff(block, block)).toBe("");
		const diff = lineDiff("a\nb\n", "a\nc\n");
		expect(diff).toContain("- b");
		expect(diff).toContain("+ c");
	});
});

describe("knowledge-install ADW directory", () => {
	function seedTree(dir: string): { planner: string; builder: string; nested: string; user: string; texts: Record<string, string> } {
		const planner = join(dir, "planner", "system.md");
		const builder = join(dir, "builder", "system.md");
		const nested = join(dir, "builder", "nested", "system.md");
		const user = join(dir, "planner", "user.md");
		mkdirSync(join(dir, "planner"), { recursive: true });
		mkdirSync(join(dir, "builder", "nested"), { recursive: true });
		const texts: Record<string, string> = {
			[planner]: "# planner\n\nkeep this\n",
			[builder]: "builder without trailing newline",
			[nested]: "# nested\n",
			[user]: "# user prompt, not a system.md\n",
		};
		for (const [file, text] of Object.entries(texts)) writeFileSync(file, text, "utf8");
		return { planner, builder, nested, user, texts };
	}

	test("findSystemPrompts finds every system.md recursively in sorted order", () => {
		const dir = mkdtempSync(join(tmpdir(), "fh-adw-tree-"));
		homes.push(dir);
		const tree = seedTree(dir);
		expect(findSystemPrompts(dir)).toEqual([tree.nested, tree.builder, tree.planner]);
		expect(adwSurfacesFor(undefined, dir).map((surface) => surface.id)).toEqual([
			"adw:builder/nested/system.md",
			"adw:builder/system.md",
			"adw:planner/system.md",
		]);
	});

	test("is skipped without --allow-adw and writes nothing", () => {
		const home = tempHome();
		const dir = join(home, "adw");
		const tree = seedTree(dir);
		const result = runKnowledgeInstall(["--home", home, "--adw-dir", dir, "--apply"]);
		expect(result.exitCode).toBe(0);
		for (const [file, text] of Object.entries(tree.texts)) expect(readFileSync(file, "utf8")).toBe(text);
		const adw = result.report.surfaces.filter((surface) => surface.id.startsWith("adw"));
		expect(adw.length).toBe(3);
		expect(adw.every((surface) => surface.status === "skipped")).toBe(true);
	});

	test("dry run lists each system.md and writes nothing", () => {
		const home = tempHome();
		const dir = join(home, "adw");
		const tree = seedTree(dir);
		const result = runKnowledgeInstall(["--home", home, "--adw-dir", dir, "--allow-adw", "--json"]);
		expect(result.exitCode).toBe(0);
		const adw = JSON.parse(result.stdout).surfaces.filter((surface: any) => surface.id.startsWith("adw:"));
		expect(adw.map((surface: any) => surface.id)).toEqual(["adw:builder/nested/system.md", "adw:builder/system.md", "adw:planner/system.md"]);
		expect(adw.every((surface: any) => surface.status === "missing")).toBe(true);
		for (const [file, text] of Object.entries(tree.texts)) expect(readFileSync(file, "utf8")).toBe(text);
	});

	test("installs exactly one marker pair per system.md and preserves user text", () => {
		const home = tempHome();
		const dir = join(home, "adw");
		const tree = seedTree(dir);
		const result = runKnowledgeInstall(["--home", home, "--adw-dir", dir, "--allow-adw", "--apply"]);
		expect(result.exitCode).toBe(0);
		for (const file of [tree.planner, tree.builder, tree.nested]) {
			const content = readFileSync(file, "utf8");
			expect((content.match(/fh-knowledge:begin/g) ?? []).length).toBe(1);
			expect((content.match(/fh-knowledge:end/g) ?? []).length).toBe(1);
			expect(currentBlockOf(content)).toBe(block);
		}
		expect(readFileSync(tree.planner, "utf8").startsWith("# planner\n\nkeep this\n")).toBe(true);
		expect(readFileSync(tree.user, "utf8")).toBe(tree.texts[tree.user]);
	});

	test("second apply is idempotent and --check reports current", () => {
		const home = tempHome();
		const dir = join(home, "adw");
		const tree = seedTree(dir);
		runKnowledgeInstall(["--home", home, "--adw-dir", dir, "--allow-adw", "--apply"]);
		const before = Object.fromEntries(Object.keys(tree.texts).map((file) => [file, readFileSync(file, "utf8")]));
		const second = runKnowledgeInstall(["--home", home, "--adw-dir", dir, "--allow-adw", "--apply", "--json"]);
		const secondAdw = JSON.parse(second.stdout).surfaces.filter((surface: any) => surface.id.startsWith("adw:"));
		expect(secondAdw.every((surface: any) => surface.status === "current" && surface.changed === false)).toBe(true);
		for (const [file, text] of Object.entries(before)) expect(readFileSync(file, "utf8")).toBe(text);

		const check = runKnowledgeInstall(["--home", home, "--adw-dir", dir, "--allow-adw", "--check", "--json"]);
		const checkAdw = JSON.parse(check.stdout).surfaces.filter((surface: any) => surface.id.startsWith("adw:"));
		expect(checkAdw.every((surface: any) => surface.status === "current" && surface.diff === "")).toBe(true);
	});

	test("uninstall restores byte-identical originals", () => {
		const home = tempHome();
		const dir = join(home, "adw");
		const tree = seedTree(dir);
		const originals = Object.fromEntries(Object.entries(tree.texts).map(([file, text]) => [file, Buffer.from(text, "utf8")]));
		runKnowledgeInstall(["--home", home, "--adw-dir", dir, "--allow-adw", "--apply"]);
		const result = runKnowledgeInstall(["--home", home, "--adw-dir", dir, "--allow-adw", "--uninstall", "--apply"]);
		expect(result.exitCode).toBe(0);
		const adw = result.report.surfaces.filter((surface) => surface.id.startsWith("adw:"));
		expect(adw.every((surface) => surface.status === "restored")).toBe(true);
		for (const [file, bytes] of Object.entries(originals)) expect(readFileSync(file)).toEqual(bytes);
		expect(existsSync(join(home, ".fh-knowledge", "manifest.json"))).toBe(false);
	});

	test("a directory with no system.md leaves ADW unselected", () => {
		const home = tempHome();
		const dir = join(home, "adw");
		mkdirSync(dir, { recursive: true });
		writeFileSync(join(dir, "README.md"), "no system prompt here\n", "utf8");
		const result = runKnowledgeInstall(["--home", home, "--adw-dir", dir, "--allow-adw", "--apply"]);
		expect(result.report.surfaces.filter((surface) => surface.id.startsWith("adw:")).length).toBe(0);
		expect(result.report.surfaces.find((surface) => surface.id === "adw")?.status).toBe("skipped");
		expect(readFileSync(join(dir, "README.md"), "utf8")).toBe("no system prompt here\n");
	});
});
