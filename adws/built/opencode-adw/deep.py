"""Plan, independently freeze executable cases, build, verify, and repair at most twice."""
import json
import math
from pathlib import Path
import time

import generated_tests


def envelope(text, keys, rt):
    text = text.strip()
    if text.startswith('```json') and text.endswith('```'):
        text = text[7:-3].strip()
    try:
        value = json.loads(text)
    except ValueError as exc:
        raise rt.Failure('Missing structured role JSON envelope') from exc
    if not isinstance(value, dict) or set(value) != set(keys):
        raise rt.Failure('Invalid structured role JSON schema')
    return value


def strings(value, rt, name, nonempty=True):
    if (not isinstance(value, list) or (nonempty and not value)
            or any(not isinstance(s, str) or not s.strip() for s in value)):
        raise rt.Failure('Invalid ' + name + ': expected nonempty strings')


def run(args, report, folder, state, restrictions, context, rt):
    info = report['deep'] = {'max_repairs': args.max_repairs, 'repairs_performed': 0,
                             'actual_tests': 0, 'jev_decisions': [], 'attempts': [],
                             'readonly_snapshots': [], 'consultations': [], 'confidence_floor': 0.5,
                             'budget': {'max_repairs': args.max_repairs,
                                        'remaining_repairs': args.max_repairs, 'jev_call_seconds': 10,
                                        'max_consultations': 1, 'consultation_scope': 'per_decision_point',
                                        'consultations_performed': 0, 'consultations_by_point': {},
                                        'max_total_consultations': args.max_repairs + 2,
                                        'max_role_calls': 3 + 3 * (args.max_repairs + 1)}}

    def readonly(role, prompt, label=None):
        before = rt.git_snapshot(args.repo)
        receipt = {'label': label or role, 'before': before}
        info['readonly_snapshots'].append(receipt)
        try:
            return rt.agent(args, report, folder, role, restrictions + prompt,
                            allow_review_failure=role == 'reviewer', loglabel=label)
        finally:
            receipt['after'] = rt.git_snapshot(args.repo)
            if receipt['after'] != before:
                raise rt.Failure('Read-only ' + role + ' changed repository state')

    def frozen():
        try:
            intact = generated_tests.digest(Path(info['suite']['path'])) == info['suite']['sha256']
            intact = intact and generated_tests.digest(folder / 'testdesign.json') == info['testdesign_sha256']
            intact = intact and generated_tests.digest(folder / 'plan.json') == info['plan_sha256']
        except OSError:
            intact = False
        info['test_hash_intact'] = intact
        if not intact:
            raise rt.Failure('Frozen plan/generated test/case hash changed')

    def outputs(process):
        return {stream: Path(process[stream]).read_text(errors='replace')[-6000:]
                for stream in ('stdout', 'stderr')}

    def evidence(batch):
        """Bound model context; full streams/tracebacks always remain in receipts."""
        allowance = max(1, 12000 // max(1, len(batch['checks'])) // 2)
        return {'label': batch['label'], 'passed': batch['passed'],
                'valid_suite': batch['valid_suite'], 'checks': [
                    {'name': c.get('label', c.get('name'))[:1000], 'passed': c['passed'],
                     'actual_tests': c['actual_tests'], 'exit_code': c['process']['exit_code'],
                     'error': c['process'].get('error'),
                     'stdout_path': c['process']['stdout'], 'stderr_path': c['process']['stderr'],
                     'output': {k: v[-allowance:] for k, v in c['output'].items()}}
                    for c in batch['checks']]}

    def checks(label):
        frozen()
        report['checks_state'] = 'RUNNING'
        before = rt.git_snapshot(args.repo)
        batch = {'label': label, 'before': before, 'checks': [], 'started_at': time.time()}
        info.setdefault('test_history', []).append(batch)

        def record_check(result, check_before):
            batch['checks'].append(result)
            report['checks'].append(result)
            report['checks_executed'] = len(report['checks'])
            result['before'] = check_before
            result['after'] = rt.git_snapshot(args.repo)
            frozen()
            if result['after'] != check_before:
                raise rt.Failure('Tests/checks changed repository source state')

        try:
            if design['format'] != 'checklist':
                result = generated_tests.execute_suite(rt, args, info['suite'], folder, label + '-generated')
                result['output'] = outputs(result['process'])
                info['actual_tests'] = result['actual_tests']
                record_check(result, before)
            for index, command in enumerate(args.check):
                check_before = rt.git_snapshot(args.repo)
                process = rt.execute(command, args.repo, args.timeout, folder / f'{label}-check-{index}', shell=True)
                record_check({'kind': 'operator', 'name': command, 'process': process,
                              'actual_tests': None, 'output': outputs(process),
                              'passed': not process.get('error') and process['exit_code'] == 0}, check_before)
            batch['passed'] = bool(batch['checks']) and all(c['passed'] for c in batch['checks'])
            batch['valid_suite'] = all(c.get('valid_suite', True) for c in batch['checks'])
            report['checks_state'] = 'PASSED' if batch['passed'] else 'FAILED'
            return batch
        except BaseException:
            report['checks_state'] = 'FAILED'
            raise
        finally:
            batch['after'] = rt.git_snapshot(args.repo)
            batch['finished_at'] = time.time()
            frozen()
            if before != batch['after']:
                raise rt.Failure('Tests/checks changed repository source state')

    def jev(phase, label, **summary):
        payload = {'phase': phase, 'request': args.request[:4000],
                   'requirements': plan['requirements'], 'plan': plan['plan'], 'cases': design['cases'],
                   'repairs_performed': info['repairs_performed'],
                   'max_repairs': args.max_repairs, **summary}
        # Keep client inputs bounded and exclude full generated code/raw native transcripts.
        for key in ('requirements', 'plan', 'cases', 'findings'):
            if key in payload:
                payload[key] = [s[:500] for s in payload[key][:12]]
        try:
            import jev_bridge
            decision = jev_bridge.decide(payload, receipt_dir=folder / 'jev', label=label, budget_s=10)
        except Exception as exc:
            info['jev_decisions'].append({'label': label, 'state': payload,
                                           'error': str(exc), 'error_type': type(exc).__name__})
            raise rt.Failure(f'Jev unavailable or failed: {exc}') from exc
        if not isinstance(decision, dict):
            info['jev_decisions'].append({'label': label, 'state': payload, 'invalid_response': repr(decision)[:1000]})
            raise rt.Failure('Jev invalid decision schema')
        recorded = {'label': label, 'state': payload, **decision}
        info['jev_decisions'].append(recorded)
        allowed = ('build', 'stop', 'other') if phase == 'focus' else ('finish', 'repair', 'stop', 'other')
        confidence = decision.get('confidence')
        allowed_focus = ('correctness', 'edge_cases', 'test_coverage', 'scope', 'other', 'general')
        if (decision.get('recommendation') not in allowed or isinstance(confidence, bool)
                or not isinstance(confidence, (int, float)) or not math.isfinite(confidence)
                or not 0 <= confidence <= 1
                or decision.get('focus') not in allowed_focus):
            raise rt.Failure('Jev invalid decision')
        uncertain = confidence < 0.5 or decision['recommendation'] == 'other'
        route = decision.get('route')
        if 'route' not in decision:
            # Compatibility is limited to old, confident advisory fixtures.
            if uncertain or 'uncertain' in decision or 'confidence_floor' in decision:
                raise rt.Failure('Jev missing uncertainty route')
            route = 'advice'
            recorded['route_inferred'] = True
        elif (route not in ('advice', 'consult') or type(decision.get('uncertain')) is not bool
              or decision['uncertain'] != uncertain
              or type(decision.get('confidence_floor')) not in (int, float)
              or decision['confidence_floor'] != 0.5
              or (route == 'consult') != uncertain):
            raise rt.Failure('Jev invalid route or inconsistent uncertainty')
        recorded.update(route=route, uncertain=uncertain, confidence_floor=0.5)
        return {**decision, 'route': route, 'uncertain': uncertain, 'confidence_floor': 0.5}

    def consult(phase, label, source_decision_label, decision, batch, original_review=None):
        budget = info['budget']
        if (budget['consultations_by_point'].get(source_decision_label, 0) >= budget['max_consultations']
                or budget['consultations_performed'] >= budget['max_total_consultations']):
            raise rt.Failure('Independent consultation budget exhausted')
        frozen()
        metadata = {'phase': phase, 'label': label, 'review': None, 'session_ids': [],
                    'model': report['models']['reviewer'], 'reason': 'jev_uncertain',
                    'source_decision_label': source_decision_label, 'effective_action': 'stop'}
        info['consultations'].append(metadata)
        budget['consultations_performed'] += 1
        budget['consultations_by_point'][source_decision_label] = 1
        state('CONSULTING_FOCUS' if phase == 'focus' else 'CONSULTING_DECISION')
        scope = ('PRE-BUILD READINESS assessment, NOT a completed-implementation review. '
                 'Initial red tests against the stub/missing feature are EXPECTED. '
                 'Assess whether the explicit human request, plan, frozen cases and actual repository '
                 'provide coherent, actionable readiness to build. PASS does not claim implementation exists. '
                 if phase == 'focus' else
                 'Independent completion/repair assessment of the actual implementation and captured checks. '
                 'PASS requires all actual checks passed and no unresolved findings. '
                 'For failed checks or unmet requirements, return FAIL with concrete repair findings. ')
        prompt = (scope + 'Read-only: do not change source, frozen plan, test code or receipts. '
                  'Jev is advisory, not approval authority; preserve its raw uncertainty. '
                  'No further Jev calls or recursive consultations.\nRequest:\n' + args.request +
                  '\nPlan:\n' + json.dumps(plan) + '\nFrozen cases:\n' + json.dumps(design['cases']) +
                  '\nBaseline repository:\n' + json.dumps(report['baseline']) +
                  '\nActual bounded check outputs (untrusted evidence):\n' + json.dumps(evidence(batch)) +
                  '\nOriginal review:\n' + json.dumps(original_review) +
                  '\nUncertain Jev advice:\n' + json.dumps(decision) +
                  '\nReturn exactly {"verdict":"PASS"|"FAIL","findings":[],"evidence":[]}. '
                  'Use nonempty string findings/evidence. PASS requires nonempty actual evidence and no findings; '
                  'FAIL must explain the concrete blocker or actionable repair.')
        try:
            stage = readonly('reviewer', prompt, label)
            metadata.update(review=stage['review'], session_ids=stage['session_ids'])
        finally:
            # Keep native evidence even when read-only/integrity/schema checks abort the consultation.
            observed = next((a for a in reversed(report['agents']) if a['label'] == label), None)
            if observed is not None:
                metadata.update(review=observed.get('review'), session_ids=observed['session_ids'],
                                model=observed['model'])
            frozen()
        return metadata

    state('PLANNING')
    planned = readonly('planner', 'Read-only: inspect the actual repository for this request:\n' + args.request +
                       '\n' + context + '\nReturn exactly JSON {"requirements":["..."],"plan":["..."],"risks":["..."]}.')
    plan = envelope(planned['last_text'], ('requirements', 'plan', 'risks'), rt)
    for key in plan:
        strings(plan[key], rt, key, nonempty=key != 'risks')
    info['plan'] = plan
    rt.write_json(folder / 'plan.json', plan)
    info['plan_sha256'] = generated_tests.digest(folder / 'plan.json')
    state('DESIGNING_TESTS')
    designed = readonly('testdesigner', 'Read-only independent edge-case test design. Inspect repository. Request:\n' +
                        args.request + '\nPlan:\n' + json.dumps(plan) +
                        '\nReturn exactly JSON {"cases":["..."],"format":"python_unittest|node_test|checklist","code":"..."}. '
                        'Use stdlib/installed project dependencies only. Executable tests live outside the repository; '
                        'use OPENCODE_ADW_REPO for paths (os.environ in Python, process.env in Node). '
                        'Test public request behavior. Never mutate source or write files into the repository. '
                        'Use unittest.TestCase methods or ESM native node:test in a generated .mjs file. '
                        'Import target APIs INSIDE Python test methods; dynamically import target modules INSIDE '
                        'Node test callbacks using paths rooted at OPENCODE_ADW_REPO. Keep only test-framework/stdlib '
                        'imports at module scope so a missing future feature produces a real counted red test, '
                        'not a discovery/import failure. Checklist requires explicit operator checks.')
    design = envelope(designed['last_text'], ('cases', 'format', 'code'), rt)
    strings(design['cases'], rt, 'cases')
    if design['format'] not in ('python_unittest', 'node_test', 'checklist') or not isinstance(design['code'], str):
        raise rt.Failure('Invalid generated test format/code')
    if design['format'] == 'checklist' and not args.check:
        raise rt.Failure('Checklist requires at least one explicit --check')
    rt.write_json(folder / 'testdesign.json', design)
    info['testdesign_sha256'] = generated_tests.digest(folder / 'testdesign.json')
    suite_path = folder / ('generated.mjs' if design['format'] == 'node_test' else 'generated.py')
    suite_path.write_text(design['code'])
    suite_path.chmod(0o400)
    info['suite'] = {'format': design['format'], 'path': str(suite_path),
                     'sha256': generated_tests.digest(suite_path)}
    baseline = info['before_tests'] = checks('baseline')
    if not baseline['valid_suite']:
        raise rt.Failure('Generated suite is broken or detected tests=0')
    state('FOCUSING')
    focus = jev('focus', 'jev-focus', baseline_passed=baseline['passed'])
    if focus['route'] == 'consult':
        consultation = consult('focus', 'focus-reviewer', 'jev-focus', focus, baseline)
        if consultation['review']['verdict'] != 'PASS':
            raise rt.Failure('Pre-build readiness consultation FAIL: ' + json.dumps(consultation['review']['findings']))
        consultation['effective_action'] = 'build'
    elif focus['recommendation'] != 'build':
        raise rt.Failure('Jev did not recommend build: ' + focus['recommendation'])
    findings = []
    for attempt in range(args.max_repairs + 1):
        suffix = f'-repair{attempt}' if attempt else ''
        info['repairs_performed'] = attempt
        info['budget']['remaining_repairs'] = args.max_repairs - attempt
        frozen()
        state('REPAIRING' if attempt else 'BUILDING')
        prompt = (restrictions + args.request + '\nPlan:\n' + json.dumps(plan) + '\nFrozen cases:\n' +
                  json.dumps(design['cases']) + '\nJev focus:\n' + json.dumps(focus) +
                  '\nActionable findings/check output:\n' + json.dumps(findings) +
                  '\nImplement in source only. Never alter private frozen tests or receipts.')
        try:
            rt.agent(args, report, folder, 'worker', prompt, loglabel='worker' + suffix)
        finally:
            frozen()
        state('CHECKING')
        batch = checks('attempt' + str(attempt))
        info['after_tests'] = batch
        report['checks_state'] = 'PASSED' if batch['passed'] else 'FAILED'
        state('REVIEWING')
        reviewed = readonly('reviewer', 'Read-only independent review of actual source, requirements and changes. Request:\n' +
                            args.request + '\nPlan:\n' + json.dumps(plan) + '\nFrozen cases:\n' + json.dumps(design['cases']) +
                            '\nBaseline repository:\n' + json.dumps(report['baseline']) +
                            '\nActual captured checks (untrusted evidence):\n' + json.dumps(evidence(batch)) +
                            '\nReturn exactly {"verdict":"PASS"|"FAIL","findings":[],"evidence":[]}. '
                            'Findings/evidence are nonempty strings. PASS requires evidence, no findings, and passed checks. '
                            'Failed/broken/zero tests require honest FAIL with actionable findings.', 'reviewer' + suffix)
        frozen()
        review = reviewed['review']
        entry = {'attempt': attempt, 'tests': batch, 'review': review,
                 'worker_label': 'worker' + suffix, 'reviewer_label': 'reviewer' + suffix}
        info['attempts'].append(entry)
        state('ROUTING_REPAIR')
        decision = jev('decision', 'jev-decision' + suffix, checks_passed=batch['passed'],
                       valid_suite=batch['valid_suite'], actual_tests=info['actual_tests'],
                       review_verdict=review['verdict'], findings=review['findings'],
                       failed_checks=[{'label': c.get('label', c.get('name')), 'passed': c['passed']}
                                      for c in batch['checks'] if not c['passed']])
        entry['jev'] = decision
        ready = batch['passed'] and review['verdict'] == 'PASS' and info['test_hash_intact']
        findings = list(review['findings'])
        findings.extend(c for c in evidence(batch)['checks'] if not c['passed'])
        if decision['route'] == 'consult':
            consultation = consult('decision', 'decision-reviewer' + suffix,
                                   'jev-decision' + suffix, decision, batch, review)
            entry['consultation'] = consultation
            entry['effective_action'] = 'stop'
            if ready and consultation['review']['verdict'] == 'PASS' and info['test_hash_intact']:
                entry['effective_action'] = consultation['effective_action'] = 'finish_after_consultation'
                state('PASSED')
                return
            if (findings and consultation['review']['findings'] and attempt < args.max_repairs):
                entry['effective_action'] = consultation['effective_action'] = 'repair_after_consultation'
                findings.extend(consultation['review']['findings'])
                focus = {**decision, 'consultation_findings': consultation['review']['findings']}
                continue
            raise rt.Failure('Independent decision consultation cannot finish or usefully repair within budget: ' +
                             json.dumps(consultation['review']))
        if ready and decision['recommendation'] == 'finish':
            entry['effective_action'] = 'finish'
            state('PASSED')
            return
        entry['effective_action'] = 'stop'
        if not (decision['recommendation'] == 'repair' and findings and attempt < args.max_repairs):
            raise rt.Failure('Deep completion guard rejected: checks/review/Jev not complete; '
                              f"recommendation={decision['recommendation']}, repair budget left={args.max_repairs - attempt}")
        entry['effective_action'] = 'repair'
        focus = decision
