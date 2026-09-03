#!/usr/bin/env node
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const fail = (message) => { throw new Error(`computer-use: ${message}`); };
const input = process.argv[2];
if (!input) fail("pass a JSON request as the first argument");
let request;
try { request = JSON.parse(input); } catch { fail("request must be valid JSON"); }
if (!request || typeof request !== "object" || Array.isArray(request)) fail("request must be an object");
const parsed = new URL(String(request.url ?? ""));
if (!['http:', 'https:'].includes(parsed.protocol)) fail("only http: and https: URLs are allowed");
const actions = Array.isArray(request.actions) ? request.actions : [];
const mutationActions = new Set(["click", "type", "press", "scroll"]);
if (actions.some((item) => mutationActions.has(item?.action)) && request.approve_mutation !== true) fail("mutating actions require approve_mutation: true after explicit user approval");
if (actions.some((item) => item?.sensitive === true) && request.approve_sensitive !== true) fail("sensitive actions require fresh approval and approve_sensitive: true");

const outputDir = await fs.mkdtemp(path.join(os.tmpdir(), "fusion-harness-computer-use-"));
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ acceptDownloads: false });
const page = await context.newPage();
page.on("download", (download) => download.cancel().catch(() => {}));
const results = [];
try {
	await page.goto(parsed.href, { waitUntil: "domcontentloaded", timeout: 30_000 });
	for (let index = 0; index < actions.length; index++) {
		const item = actions[index];
		if (!item || typeof item !== "object") fail(`action ${index + 1} must be an object`);
		switch (item.action) {
			case "extract": {
				const selector = String(item.selector ?? "body");
				results.push({ action: "extract", selector, text: (await page.locator(selector).innerText()).slice(0, 50_000) });
				break;
			}
			case "click":
				if (!item.selector) fail(`click ${index + 1} requires selector`);
				await page.locator(String(item.selector)).click({ timeout: 15_000 });
				break;
			case "type":
				if (!item.selector || typeof item.text !== "string") fail(`type ${index + 1} requires selector and text`);
				await page.locator(String(item.selector)).fill(item.text, { timeout: 15_000 });
				break;
			case "press":
				if (!item.key) fail(`press ${index + 1} requires key`);
				if (item.selector) await page.locator(String(item.selector)).press(String(item.key));
				else await page.keyboard.press(String(item.key));
				break;
			case "scroll":
				await page.mouse.wheel(0, Math.max(-5_000, Math.min(5_000, Number(item.delta_y) || 0)));
				break;
			case "wait":
				await page.waitForTimeout(Math.max(0, Math.min(10_000, Number(item.milliseconds) || 0)));
				break;
			default: fail(`unsupported action ${JSON.stringify(item.action)}`);
		}
		const current = new URL(page.url());
		if (!['http:', 'https:', 'about:'].includes(current.protocol)) fail(`navigation to ${current.protocol} is blocked`);
	}
	const screenshot = path.join(outputDir, "final.png");
	await page.screenshot({ path: screenshot, fullPage: false });
	const bodyText = await page.locator("body").innerText().catch(() => "");
	console.log(JSON.stringify({ ok: true, url: page.url(), title: await page.title(), text: bodyText.slice(0, 20_000), results, screenshot, outputDir }, null, 2));
} finally {
	await context.close().catch(() => {});
	await browser.close().catch(() => {});
}
