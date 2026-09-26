// Fixture: UI-gated block only. The doctor must classify this fail-open — the block can
// only follow an interactive ctx.ui prompt, so a headless run can never be stopped by it.
export default function (pi: any) {
	const dangerousPatterns = [/\brm\s+-rf/i, /\bsudo\b/i];
	pi.on("tool_call", async (event: any, ctx: any) => {
		if (event.toolName !== "bash") return undefined;
		if (dangerousPatterns.some((p) => p.test(String(event.input?.command ?? "")))) {
			const choice = await ctx.ui.select("Dangerous command. Allow?", ["Yes", "No"]);
			if (choice !== "Yes") return { block: true, reason: "Blocked by user" };
		}
		return undefined;
	});
}
