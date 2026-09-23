/**
 * Provider quota / rate-limit handling for delegated children.
 *
 * A 429 is not a task failure: the work is fine, the account is out of budget
 * until a reset. Callers wait for the reset and rerun the same child. There is
 * no retry cap — a quota always resets — only the run's stop signal ends it.
 */

const QUOTA_PATTERN = /\b429\b|rate[ _-]?limit|usage limit|quota|too many requests|使用上限|限额/i;
const CJK = /[㐀-鿿]/;
/** Longest single sleep, so a mis-parsed reset time is re-checked instead of trusted. */
const MAX_STEP_MS = 15 * 60_000;
/** No reset hint at all: probe again after this long. */
const DEFAULT_WAIT_MS = 60_000;
/** Absolute reset times get a small margin for clock skew. */
const RESET_MARGIN_MS = 30_000;

export function isQuotaError(text: string): boolean {
	return QUOTA_PATTERN.test(text);
}

/** Epoch ms when the provider says the quota resets, if the message says. */
export function quotaResetAt(text: string, now = Date.now()): number | undefined {
	const relative = text.match(/retry[ _-]?after["':\s]*(\d+(?:\.\d+)?)\s*(ms|milliseconds?|s|secs?|seconds?|m|mins?|minutes?)?/i);
	if (relative) {
		const value = Number(relative[1]);
		const unit = (relative[2] ?? "s").toLowerCase();
		const ms = unit.startsWith("ms") || unit.startsWith("milli") ? value : unit.startsWith("m") ? value * 60_000 : value * 1000;
		return now + ms;
	}
	const iso = text.match(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})/);
	if (iso) {
		const at = Date.parse(iso[0]);
		if (Number.isFinite(at)) return at + RESET_MARGIN_MS;
	}
	const bare = text.match(/(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})/);
	if (bare) {
		// Zone-less stamps from CJK-language providers (e.g. Zhipu/z.ai) are China time.
		const zone = CJK.test(text) ? "+08:00" : "";
		const at = Date.parse(`${bare[1]}T${bare[2]}${zone}`);
		if (Number.isFinite(at)) return at + RESET_MARGIN_MS;
	}
	return undefined;
}

/** How long to sleep before the next attempt (one step; the caller loops). */
export function quotaWaitMs(text: string, now = Date.now()): number {
	const reset = quotaResetAt(text, now);
	const wait = reset === undefined ? DEFAULT_WAIT_MS : Math.max(0, reset - now);
	return Math.min(wait, MAX_STEP_MS);
}

export function sleepUnlessStopped(ms: number, signal?: AbortSignal): Promise<void> {
	if (ms <= 0 || signal?.aborted) return Promise.resolve();
	return new Promise((resolve) => {
		const timer = setTimeout(resolve, ms);
		signal?.addEventListener("abort", () => { clearTimeout(timer); resolve(); }, { once: true });
	});
}
