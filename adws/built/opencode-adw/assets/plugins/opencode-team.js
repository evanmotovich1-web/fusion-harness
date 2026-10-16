import { tool } from '@opencode-ai/plugin';
import { spawn } from 'node:child_process';

// Rendered as JSON strings by the source installer.
const runtime = @RUNTIME_JSON@;
const python = @PYTHON_JSON@;
const OUTPUT_LIMIT = 1024 * 1024;

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const scalarFields = (value, keys) => Object.fromEntries(keys.filter((key) =>
  isObject(value) && Object.hasOwn(value, key) &&
  (value[key] === null || ['string', 'number', 'boolean'].includes(typeof value[key]))
).map((key) => [key, value[key]]));

function compactTeam(value) {
  if (!isObject(value)) return undefined;
  const team = scalarFields(value, ['parent_session_id']);
  if (Array.isArray(value.children)) {
    team.children = value.children.filter(isObject).map((child) => scalarFields(child,
      ['role', 'label', 'session_id', 'parent_id', 'model', 'state', 'execution']));
  }
  return team;
}

function compactRouting(value) {
  if (!isObject(value)) return undefined;
  const routing = scalarFields(value, ['status', 'method', 'selected_repo', 'question',
    'model', 'model_requested', 'model_resolved', 'confidence', 'receipt_path']);
  if (isObject(value.jev)) {
    routing.jev = scalarFields(value.jev, ['status', 'model', 'model_requested', 'model_resolved', 'confidence']);
  }
  if (Array.isArray(value.candidates)) {
    routing.candidates = value.candidates.filter(isObject).slice(0, 3).map((candidate) => {
      const choice = scalarFields(candidate, ['name']);
      const path = candidate.selected_repo ?? candidate.canonical_checkout ?? candidate.path;
      if (typeof path === 'string') choice.path = path;
      return choice;
    });
  }
  return routing;
}

function compactRun(value) {
  const run = scalarFields(value, ['adw_id', 'run_id', 'state', 'repo', 'report', 'report_path',
    'stdout', 'output_dir', 'started_at', 'finished_at', 'workflow', 'mode',
    'checks_state', 'checks_executed', 'error_code', 'question']);
  if (!run.report && typeof value.output_dir === 'string') {
    run.report = value.output_dir.replace(/\/$/, '') + '/report.json';
  }
  if (isObject(value.models)) {
    run.models = scalarFields(value.models, ['worker', 'reviewer', 'planner', 'testdesigner']);
  }
  const routing = compactRouting(value.routing);
  if (routing) run.routing = routing;
  const team = compactTeam(value.team ?? value.report?.team);
  if (team) run.team = team;
  if (isObject(value.deep)) {
    run.deep = scalarFields(value.deep, ['actual_tests', 'repairs_performed', 'max_repairs']);
    const decisions = value.deep.jev_decisions;
    const advice = Array.isArray(decisions) ? decisions.filter(isObject).at(-1) : undefined;
    if (advice) {
      run.deep.jev_last_advice = scalarFields(advice, ['label', 'phase', 'recommendation', 'focus',
        'route', 'uncertain', 'confidence', 'confidence_floor', 'model', 'model_requested',
        'model_resolved', 'error_type']);
    }
  }
  return run;
}

function compactReceipt(value, action, runID, sessionID) {
  if (!isObject(value)) return null;
  if (action !== 'status' || !Array.isArray(value.runs)) return compactRun(value);
  const rows = value.runs.filter(isObject);
  let selected = rows;
  let scope = 'run';
  if (!runID) {
    const current = rows.filter((row) => row.team?.parent_session_id === sessionID);
    selected = current.length ? current : rows;
    scope = current.length ? 'current_session' : 'global_fallback';
  }
  // Sort a copy: statuses, including failures, are never used as a selection filter.
  const runs = [...selected].sort((a, b) => {
    const started = (row) => typeof row.started_at === 'number' && Number.isFinite(row.started_at)
      ? row.started_at : 0;
    return started(b) - started(a);
  }).slice(0, 10).map(compactRun);
  const result = { scope, runs };
  if (isObject(value.jev)) result.jev = scalarFields(value.jev, ['configured', 'model']);
  return result;
}

export default async function ({ serverUrl }) {
  return {
    tool: {
      opencode_team: tool({
        description: 'Run a native OpenCode team, resolve a repository, or inspect actual run status.',
        args: {
          action: tool.schema.enum(['run', 'route', 'status']).default('run'),
          task: tool.schema.string().optional(),
          repo: tool.schema.string().optional(),
          workflow: tool.schema.enum(['team', 'deep', 'build', 'review', 'takeover']).default('team'),
          model: tool.schema.string().optional(),
          models: tool.schema.object({
            worker: tool.schema.string().optional(),
            reviewer: tool.schema.string().optional(),
            planner: tool.schema.string().optional(),
            testdesigner: tool.schema.string().optional(),
          }).optional(),
          checks: tool.schema.array(tool.schema.string()).optional(),
          max_repairs: tool.schema.number().int().min(0).max(2).optional(),
          run_id: tool.schema.string().optional(),
        },
        async execute(args, ctx) {
          const action = args.action ?? 'run';
          if (ctx.agent === 'opencode-router' && action === 'run') {
            throw new Error('Router may only route or inspect status.');
          }
          if (action !== 'status' && !args.task?.trim()) {
            throw new Error('task is required for run and route.');
          }
          if (!ctx.sessionID || !ctx.directory || !serverUrl) {
            throw new Error('Native OpenCode tool context is required.');
          }
          const nativeURL = new URL(String(serverUrl));
          if (!['http:', 'https:'].includes(nativeURL.protocol) || nativeURL.username || nativeURL.password ||
              nativeURL.search || nativeURL.hash || nativeURL.pathname !== '/' ||
              !(nativeURL.hostname === 'localhost' || nativeURL.hostname === '[::1]' ||
                /^127(?:\.\d{1,3}){3}$/.test(nativeURL.hostname))) {
            throw new Error('Native OpenCode server must be a loopback URL without credentials.');
          }
          const workflow = args.workflow ?? 'team';
          const argv = [runtime, action === 'run' && workflow === 'takeover' ? 'takeover' : action];
          if (action === 'status') {
            if (args.run_id) argv.push('--adw-id', args.run_id);
          } else {
            argv.push('--native-server-url', String(serverUrl), '--parent-session', ctx.sessionID,
              '--parent-directory', ctx.directory, '--routing-context', ctx.directory);
            argv.push('--request', args.task, '--repo', args.repo ?? 'auto');
            if (action === 'run') {
              argv.push('--mode', workflow === 'takeover' ? 'build' : workflow);
              if (args.model) argv.push('--model', args.model);
              for (const role of ['worker', 'reviewer', 'planner', 'testdesigner']) {
                if (args.models?.[role]) argv.push(`--${role}-model`, args.models[role]);
              }
              for (const check of args.checks ?? []) argv.push('--check', check);
              if (args.max_repairs !== undefined) argv.push('--max-repairs', String(args.max_repairs));
            }
          }
          if (ctx.abort.aborted) return { title: 'OpenCode team cancelled', output: 'Cancelled before start.' };
          return await new Promise((resolve) => {
            const child = spawn(python, argv, { shell: false, stdio: ['ignore', 'pipe', 'pipe'] });
            const chunks = [];
            let bytes = 0;
            let overflow = false;
            let cancelled = false;
            let killTimer;
            const stop = () => {
              if (killTimer) return;
              child.kill('SIGTERM');
              // Core finally must have time to abort its native children first.
              killTimer = setTimeout(() => child.kill('SIGKILL'), 7000);
              killTimer.unref?.();
            };
            const abort = () => { cancelled = true; stop(); };
            ctx.abort.addEventListener('abort', abort, { once: true });
            if (ctx.abort.aborted) abort();
            child.stdout.on('data', (data) => {
              const buffer = Buffer.from(data);
              if (bytes + buffer.length > OUTPUT_LIMIT) {
                overflow = true;
                stop();
              } else if (!overflow) {
                bytes += buffer.length;
                chunks.push(buffer);
              }
            });
            // Drain stderr but never return raw exceptions, headers, or credentials.
            child.stderr.on('data', () => {});
            let spawnFailed = false;
            child.on('error', () => { spawnFailed = true; });
            child.on('close', (code) => {
              clearTimeout(killTimer);
              ctx.abort.removeEventListener('abort', abort);
              const stdout = Buffer.concat(chunks).toString('utf8');
              let receipt;
              try {
                // Parse pretty status JSON before any nested scalar lines can be mistaken for receipts.
                const value = JSON.parse(stdout);
                if (isObject(value)) receipt = value;
              } catch {
                for (const line of stdout.split('\n')) {
                  try {
                    const value = JSON.parse(line);
                    if (isObject(value)) receipt = value;
                  } catch { /* Only complete JSONL objects are receipts. */ }
                }
              }
              receipt = overflow ? null : compactReceipt(receipt, action, args.run_id, ctx.sessionID);
              const failed = cancelled || overflow || spawnFailed || code !== 0;
              const runID = receipt?.adw_id ?? receipt?.run_id ?? null;
              const team = receipt?.team ?? receipt?.report?.team ?? null;
              const output = {
                state: cancelled ? 'CANCELLED' : overflow ? 'OUTPUT_LIMIT' : spawnFailed ? 'SPAWN_FAILED' :
                  failed ? 'FAILED' : receipt?.state ?? 'RETURNED',
                exit_code: code, run_id: runID, team,
                receipt: overflow ? null : receipt ?? null,
              };
              resolve({ title: `OpenCode ${action}: ${output.state}`,
                output: JSON.stringify(output), metadata: { runID, team, exitCode: code } });
            });
          });
        },
      }),
    },
  };
}
