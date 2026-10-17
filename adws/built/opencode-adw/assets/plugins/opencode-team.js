import { Plugin } from '@opencode/plugin';
import { spawn } from 'node:child_process';

// Rendered as JSON strings by the source installer.
const runtime = @RUNTIME_JSON@;
const python = @PYTHON_JSON@;
const opencode = @OPENCODE_JSON@;
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
  if (action !== 'status') {
    if (typeof value.state !== 'string' ||
        !(typeof value.adw_id === 'string' || typeof value.run_id === 'string')) return null;
    return compactRun(value);
  }
  if (!Array.isArray(value.runs) || value.runs.some((row) => !isObject(row) ||
      typeof row.state !== 'string' || typeof (row.adw_id ?? row.run_id) !== 'string')) return null;
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

export default Plugin.define({
  id: 'opencode-team',
  async setup(plugin) {
    await plugin.tool.transform((editor) => {
      editor.add({
        name: 'opencode_team',
        description: 'Run a native OpenCode team, resolve a repository, or inspect actual run status.',
        input: {
          type: 'object', additionalProperties: false,
          properties: {
            action: { type: 'string', enum: ['run', 'route', 'status'], default: 'run' },
            task: { type: 'string' }, repo: { type: 'string' },
            workflow: { type: 'string', enum: ['team', 'deep', 'build', 'review', 'takeover'], default: 'team' },
            model: { type: 'string' },
            models: { type: 'object', additionalProperties: false, properties: Object.fromEntries(
              ['worker', 'reviewer', 'planner', 'testdesigner'].map((role) => [role, { type: 'string' }])) },
            checks: { type: 'array', items: { type: 'string' } },
            max_repairs: { type: 'integer', minimum: 0, maximum: 2 },
            run_id: { type: 'string' },
          },
        },
        async execute(args, ctx) {
          if (!ctx.sessionID || !ctx.signal) throw new Error('Native OpenCode tool context is required.');
          const response = await plugin.session.get({ sessionID: ctx.sessionID });
          const parent = response?.data ?? response;
          const directory = parent?.location?.directory;
          if (parent?.id !== ctx.sessionID || typeof directory !== 'string' || !directory.startsWith('/')) {
            throw new Error('Native parent session location is required.');
          }
          const action = args.action ?? 'run';
          if (parent.agent === 'opencode-router' && action === 'run') {
            throw new Error('Router may only route or inspect status.');
          }
          if (action !== 'status' && !args.task?.trim()) {
            throw new Error('task is required for run and route.');
          }
          const workflow = args.workflow ?? 'team';
          const argv = [runtime, action === 'run' && workflow === 'takeover' ? 'takeover' : action];
          if (action === 'status') {
            if (args.run_id) argv.push('--adw-id', args.run_id);
          } else {
            argv.push('--parent-session', ctx.sessionID,
              '--parent-directory', directory, '--routing-context', directory);
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
          if (ctx.signal.aborted) return { content: 'Cancelled before start.' };
          return await new Promise((resolve) => {
            const child = spawn(python, argv, { shell: false, stdio: ['ignore', 'pipe', 'pipe'],
              env: { ...process.env, OPENCODE_ADW_OPENCODE: opencode } });
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
            ctx.signal.addEventListener('abort', abort, { once: true });
            if (ctx.signal.aborted) abort();
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
              ctx.signal.removeEventListener('abort', abort);
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
              const failed = cancelled || overflow || spawnFailed || code !== 0 || !receipt;
              const runID = receipt?.adw_id ?? receipt?.run_id ?? null;
              const team = receipt?.team ?? receipt?.report?.team ?? null;
              const output = {
                state: cancelled ? 'CANCELLED' : overflow ? 'OUTPUT_LIMIT' : spawnFailed ? 'SPAWN_FAILED' :
                  failed ? 'FAILED' : receipt?.state ?? 'RETURNED',
                exit_code: code, run_id: runID, team,
                receipt: overflow ? null : receipt ?? null,
              };
              resolve({ content: JSON.stringify(output) });
            });
          });
        },
      });
    });
  },
});
