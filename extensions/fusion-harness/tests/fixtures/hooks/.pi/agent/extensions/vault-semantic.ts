// Fixture: fail-open injection hook.
import { execFileSync } from "node:child_process";

export default function (pi: any) {
	pi.on("before_agent_start", async (event: any) => {
		let text = "";
		try {
			text = execFileSync("vault-semantic", ["hook"], { timeout: 1500, encoding: "utf8" }).trim();
		} catch {
			return;
		}
		if (!text) return;
		return { systemPrompt: `${event.systemPrompt}\n\n${text}` };
	});
}
