import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** Evan's app-local identity, never a replacement for Fusion's temporary worker UI. */
export default function evanUI(pi: ExtensionAPI) {
  pi.on("session_start", (_event, ctx) => {
    if (ctx.mode !== "tui") return;
    ctx.ui.setTitle("Evan Agent");
    ctx.ui.setHeader((_tui, theme) => ({
      render(width: number) {
        const label = "EVAN AGENT · single-model chat";
        return [theme.fg("accent", label.slice(0, Math.max(0, width)))];
      },
      invalidate() {},
    }));
    ctx.ui.setStatus("evan-chat", "chat · read-only");
  });
  pi.on("session_shutdown", (_event, ctx) => {
    if (ctx.mode === "tui") ctx.ui.setStatus("evan-chat", undefined);
  });
}
