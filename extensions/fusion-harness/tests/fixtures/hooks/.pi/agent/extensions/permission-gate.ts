// Fixture: headless block contract. Mirrors the shape the doctor must flag can-block.
export default function (pi: any) {
	const dangerousPatterns = [/\brm\s+-rf/i, /\bsudo\b/i];
	pi.on("tool_call", async (event: any, ctx: any) => {
		if (event.toolName !== "bash") return undefined;
		if (dangerousPatterns.some((p) => p.test(String(event.input?.command ?? "")))) {
			if (!ctx.hasUI) return { block: true, reason: "Dangerous command blocked (no UI for confirmation)" };
		}
		return undefined;
	});
}
