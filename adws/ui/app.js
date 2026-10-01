/* Workflow-builder desk. All data from /api/*; unknown stays "unknown" (R9). */
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const ms = (v) => (v === null || v === undefined ? "—" : (v / 1000).toFixed(v >= 10000 ? 0 : 1) + "s");
const num = (v) => (v === null || v === undefined ? "—" : String(v));

async function get(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(path + " " + r.status);
  return r.json();
}

async function post(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return { status: r.status, data: await r.json().catch(() => ({})) };
}

function table(el, cols, rows) {
  el.innerHTML = "<tr>" + cols.map((c) => `<th>${esc(c[0])}</th>`).join("") + "</tr>" +
    (rows.length ? rows.map((r) => "<tr>" + cols.map((c) => `<td class="${c[2] || ""}">${c[1](r)}</td>`).join("") + "</tr>").join("")
      : `<tr><td colspan="${cols.length}" class="muted">Nothing yet.</td></tr>`);
}

const pill = (status) => `<span class="pill ${esc(status)}">${esc(status)}</span>`;
const toolsText = (t) => Object.entries(t || {}).map(([name, n]) => `${esc(name)}×${n}`).join(" ") || "—";
const tokensText = (t) => !t ? "unknown" : (t.total === "unknown" || t.total === undefined ? "unknown" : num(t.total));
const costText = (c) => !c ? "unknown" : (c.total === "unknown" || c.total === undefined ? "unknown" : `${num(c.total)} ${c.currency === "unknown" || !c.currency ? "" : c.currency}`.trim());

/* ── builds ── */
function agentCols() {
  return [
    ["Agent", (a) => esc(a.agent)],
    ["Attempts", (a) => num(a.attempts)],
    ["Gate", (a) => pill(a.gate_passed ? "passed" : "failed")],
    ["Tool calls", (a) => toolsText(a.tools)],
    ["Errors", (a) => num(a.tool_errors)],
    ["Incomplete", (a) => num(a.incomplete_calls)],
    ["Time", (a) => ms(a.duration_ms)],
    ["Model", (a) => esc(a.model)],
    ["Thinking", (a) => esc(a.thinking)],
    ["Tokens", (a) => tokensText(a.tokens)],
    ["Cost", (a) => costText(a.cost)],
    ["Mode", (a) => (a.stub ? "stub" : "live")],
  ];
}

async function showDetail(runId) {
  const el = document.getElementById("build-detail");
  el.classList.remove("hidden");
  document.getElementById("detail-title").textContent = `Run ${runId}`;
  let d;
  try { d = await get("/api/builds/" + encodeURIComponent(runId)); } catch (e) {
    document.getElementById("detail-title").textContent = `Run ${runId} — unavailable: ${e.message}`;
    return;
  }
  table(document.getElementById("detail-agents"), agentCols(), d.agents || []);
  table(document.getElementById("detail-phases"), [
    ["Phase", (p) => esc(p.phase_id)], ["Name", (p) => esc(p.phase_name)],
    ["Kind", (p) => esc(p.kind)], ["Owner", (p) => esc(p.owner)], ["Attempt", (p) => num(p.attempt)],
    ["Status", (p) => pill(p.status)], ["Gate", (p) => esc(p.gate_id) + " " + esc(p.gate_result || "")],
    ["Time", (p) => ms(p.duration_ms)], ["Model", (p) => esc(p.model)]], d.phases || []);
  table(document.getElementById("detail-reqs"), [
    ["Id", (r) => esc(r.req_id)], ["Requirement", (r) => esc(r.text), "wrap"],
    ["Phase", (r) => esc(r.phase_id)], ["Gate", (r) => esc(r.gate)],
    ["Status", (r) => pill(r.status)], ["Blocker", (r) => esc(r.blocker || "—"), "wrap"]], d.requirements || []);
}

async function loadBuilds() {
  const data = await get("/api/builds");
  table(document.getElementById("builds"), [
    ["Run", (b) => `<a href="#" class="run-link" data-run="${esc(b.run_id)}">${esc(b.run_id)}</a>`],
    ["Workflow", (b) => esc(b.workflow_id || "—")],
    ["Status", (b) => pill(b.status)],
    ["Reason", (b) => esc(b.reason || ""), "wrap"],
    ["Agents", (b) => (b.agents || []).map((a) => esc(a.agent)).join(", ") || "—"],
    ["Tool calls", (b) => num((b.agents || []).reduce((n, a) => n + (a.tool_calls || 0), 0))],
    ["Time", (b) => ms((b.agents || []).reduce((n, a) => n + (a.duration_ms || 0), 0) || null)],
    ["Created", (b) => esc(b.created_at)]], data.builds || []);
  table(document.getElementById("queued"), [
    ["File", (q) => esc(q.file)], ["Created", (q) => esc(q.created_at)],
    ["Request", (q) => esc(q.request_preview), "wrap"]], data.queued || []);
  document.querySelectorAll(".run-link").forEach((a) =>
    a.addEventListener("click", (e) => { e.preventDefault(); showDetail(a.dataset.run); }));
  return data;
}

/* ── built workflows + seats ── */
async function loadWorkflows() {
  const data = await get("/api/workflows");
  table(document.getElementById("workflows"), [
    ["Id", (w) => esc(w.id)], ["Name", (w) => esc(w.name)], ["Version", (w) => num(w.version)],
    ["Status", (w) => pill(w.desk_status)],
    ["Acceptance", (w) => `${w.acceptance.verified}/${w.acceptance.requirements_total} verified` +
      (w.acceptance.blocked ? ` · ${w.acceptance.blocked} blocked` : "")],
    ["Built", (w) => esc(w.built_at)], ["Entrypoint", (w) => `<code>${esc(w.entrypoint)}</code>`],
    ["Launch", (w) => w.desk_status === "verified"
      ? `<button class="launch" data-id="${esc(w.id)}">Launch (stub)</button>` : "—"]],
  data.workflows || []);
  document.querySelectorAll(".launch").forEach((button) =>
    button.addEventListener("click", () => launch(button.dataset.id, button)));
  table(document.getElementById("incomplete"), [
    ["Source", (i) => esc(i.source)], ["Status", (i) => pill(i.status)],
    ["Run / file", (i) => esc(i.run_id || i.file || "—")],
    ["Workflow", (i) => esc(i.workflow_id || "—")],
    ["Reason / request", (i) => esc(i.reason || ""), "wrap"],
    ["Since", (i) => esc(i.created_at)]], data.incomplete || []);
  const checksText = (c) => Object.entries(c || {}).map(([k, v]) =>
    `${esc(k)}=${v === true ? "yes" : v === false ? "no" : esc(v)}`).join(" ");
  table(document.getElementById("seats"), [
    ["Seat", (s) => esc(s.name)], ["Role", (s) => esc(s.role)],
    ["Model", (s) => esc(s.provider_model)], ["Status", (s) => pill(s.status)],
    ["Checks", (s) => checksText(s.checks), "wrap"],
    ["Stack", (s) => `<code>${esc(s.stack)}</code>`],
    ["Run it", (s) => `<code>${esc(s.recipe)}</code>`],
    ["Tokens", (s) => esc(s.tokens)], ["Cost", (s) => esc(s.cost)]], data.seats || []);
  return data;
}

async function launch(id, button) {
  button.disabled = true;
  const out = document.getElementById("launch-result");
  out.textContent = `Launching ${id} (stub)…`;
  const { status, data } = await post("/api/launch", { id });
  out.textContent = status === 200
    ? `${id} stub run — exit ${data.exit}, ${ms(data.duration_ms)}\nreports: ${data.reports_dir}\n\n${(data.log_tail || "").trim()}`
    : `Launch refused (${status}): ${data.error || "unknown error"}`;
  button.disabled = false;
}

/* ── submit ── */
async function submit(run) {
  const text = document.getElementById("request").value.trim();
  const out = document.getElementById("submit-result");
  if (!text) { out.textContent = "Write a request first."; return; }
  out.textContent = run ? "Queuing and building (stub)…" : "Queuing…";
  const { status, data } = await post("/api/builds", { request: text, run });
  if (status !== 200) { out.textContent = `Refused (${status}): ${data.error || "unknown error"}`; return; }
  let lines = [`Queued: ${data.file}`];
  if (data.build) {
    lines.push(`Builder (stub): exit ${data.build.exit} in ${ms(data.build.duration_ms)}`);
    lines.push("", (data.build.log_tail || "").trim().split("\n").slice(-12).join("\n"));
  } else {
    lines.push(`Consume with: ${data.consume}`);
  }
  out.textContent = lines.join("\n");
  await refresh();
}

async function refresh() {
  try {
    const [builds, workflows] = await Promise.all([loadBuilds(), loadWorkflows()]);
    const queued = (builds.queued || []).length;
    const incomplete = (workflows.incomplete || []).length;
    document.getElementById("status").textContent =
      `${(workflows.workflows || []).length} built workflow(s) · ${(builds.builds || []).length} build run(s)` +
      (queued ? ` · ${queued} queued request(s)` : "") +
      (incomplete ? ` · ${incomplete} in progress` : "") + " · stub-only · localhost";
  } catch (e) {
    document.getElementById("status").textContent = "Could not load data: " + e.message;
  }
}

document.getElementById("queue-only").addEventListener("click", () => submit(false));
document.getElementById("queue-build").addEventListener("click", () => submit(true));
refresh();
setInterval(refresh, 5000);
