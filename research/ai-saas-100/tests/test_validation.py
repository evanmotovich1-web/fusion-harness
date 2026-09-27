import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import validate as v
from receipt import receipt_template, unknown_metric


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ref = self.save('fixture.txt', 'synthetic test artifact')
        self.row = {'id': '001', 'name': 'Synthetic', 'canonical_url': 'https://synthetic.invalid/',
                    'case_path': 'cases/001', 'identity_evidence_ids': ['e1'],
                    'stage_statuses': {s: 'not_started' for s in v.STAGES}}
        self.reg = {'schema_version': 1, 'products': [self.row], 'accepted_products': 0,
                    'deliverables_complete': False}

    def save(self, path, contents):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contents)
        return {'path': path, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}

    def run_record(self):
        r = receipt_template('001', 'synthetic-run')
        r.update(status='completed', started_at='2026-01-01T00:00:00Z',
                 ended_at='2026-01-01T00:00:01Z', command=['python3', 'synthetic.py'],
                 cwd='synthetic-test-only', implementation=self.ref, fixtures=self.ref,
                 input_bundle=self.ref, outputs=[self.ref], runtime={'python': 'test'},
                 configuration={'test_only': True}, exit_status=0, execution_kind='real',
                 test_results=[{'test_id': 'synthetic', 'outcome': 'passed'}])
        return r

    def case(self):
        d = {'schema_version': 1, 'record_status': 'unknown', 'claims': [],
             'research': {t: {'claim_ids': [], 'value': None, 'unknown_reason': 'Not researched'} for t in v.TOPICS}}
        for section, names in v.FIELDS.items():
            d[section] = {n: None for n in names.split()}
        d['identity'].update(id='001', identity_status='unknown', identity_evidence_ids=[],
                             name='Synthetic', canonical_url='https://synthetic.invalid/')
        d['selection']['eligibility_evidence_ids'] = []
        d['assessment'].update(stage_statuses={s: 'not_started' for s in v.STAGES}, receipt_paths=[])
        return d

    def test_registry_valid_incomplete(self):
        self.assertEqual(v.registry(self.reg, {'e1'}, self.root)['accepted_products'], 0)

    def test_duplicate_ids(self):
        self.reg['products'].append(copy.deepcopy(self.row))
        with self.assertRaisesRegex(ValueError, 'duplicate id'):
            v.registry(self.reg, {'e1'}, self.root)

    def test_duplicate_domains(self):
        row = copy.deepcopy(self.row)
        row.update(id='002', canonical_url='https://www.synthetic.invalid/another')
        self.reg['products'].append(row)
        with self.assertRaisesRegex(ValueError, 'duplicate canonical'):
            v.registry(self.reg, {'e1'}, self.root)

    def test_bad_ids(self):
        for value in ['000', '101', '1', 1, None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                v.case_id(value)

    def test_broken_evidence(self):
        with self.assertRaisesRegex(ValueError, 'broken evidence'):
            v.registry(self.reg, set(), self.root)

    def test_missing_required_field(self):
        del self.reg['products'][0]['case_path']
        with self.assertRaisesRegex(ValueError, 'missing field'):
            v.registry(self.reg, {'e1'}, self.root)

    def test_counts_not_trusted(self):
        self.reg['accepted_products'] = 1
        with self.assertRaisesRegex(ValueError, 'incorrect accepted count'):
            v.registry(self.reg, {'e1'}, self.root)

    def test_false_completion(self):
        self.reg['deliverables_complete'] = True
        with self.assertRaisesRegex(ValueError, 'incorrect completion'):
            v.registry(self.reg, {'e1'}, self.root)

    def test_receipt_template_does_not_claim_execution(self):
        r = receipt_template('001', 'pending')
        v.receipt(r, self.root)
        self.assertIsNone(r['started_at'])
        self.assertEqual(r['status'], 'not_started')

    def test_completed_receipt_requires_execution_fields(self):
        r = receipt_template('001', 'pending')
        r['status'] = 'completed'
        with self.assertRaises(ValueError):
            v.receipt(r, self.root)

    def test_synthetic_receipt_roundtrip(self):
        v.receipt(json.loads(json.dumps(self.run_record())), self.root)

    def test_nonzero_exit_not_completed(self):
        r = self.run_record()
        r['exit_status'] = 1
        with self.assertRaisesRegex(ValueError, 'nonzero exit'):
            v.receipt(r, self.root)

    def test_unknown_cost_not_zero(self):
        m = unknown_metric('USD')
        m['value'] = 0
        with self.assertRaisesRegex(ValueError, 'unknown metric'):
            v.metric(m)

    def test_estimate_requires_assumptions(self):
        m = unknown_metric('USD')
        m.update(value=0.1, classification='estimated', category='usage_derived_estimate')
        with self.assertRaisesRegex(ValueError, 'assumptions'):
            v.metric(m)
        m['assumptions'] = ['Synthetic unit-test price']
        v.metric(m)
        m['classification'] = 'measured'
        with self.assertRaisesRegex(ValueError, 'classification mismatch'):
            v.metric(m)

    def test_nonfinite_and_boolean_metric(self):
        for val in [float('nan'), float('inf'), True, -1]:
            m = unknown_metric('seconds')
            m.update(value=val, classification='measured', category='latency')
            with self.subTest(value=val), self.assertRaises(ValueError):
                v.metric(m)

    def test_hash_changes_invalidate(self):
        (self.root / self.ref['path']).write_text('changed')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            v.artifact(self.root, self.ref)

    def test_path_escape(self):
        for path in ['../escape', '/etc/passwd']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                v.local(self.root, path)

    def test_unknown_dossier_is_valid_not_accepted(self):
        self.assertFalse(v.dossier(self.case(), set(), self.root))

    def test_stage_dependencies(self):
        state = {s: 'not_started' for s in v.STAGES}
        state['execution'] = 'passed'
        with self.assertRaisesRegex(ValueError, 'prerequisite'):
            v.stages(state)

    def test_required_stage_not_applicable_rejected(self):
        state = {s: 'not_started' for s in v.STAGES}
        state['identity'] = 'not_applicable'
        with self.assertRaises(ValueError):
            v.stages(state)

    def test_milestone_not_merely_label(self):
        d = self.case()
        for label in ['researched', 'implemented', 'tested', 'blocked']:
            d['record_status'] = label
            with self.subTest(label=label), self.assertRaises(ValueError):
                v.dossier(d, set(), self.root)

    def test_mock_implementation_rejected(self):
        d = self.case()
        d['identity'].update(identity_status='verified', identity_evidence_ids=['e1'])
        for s in v.STAGES[:3]:
            d['assessment']['stage_statuses'][s] = 'passed'
        d['implementation'].update(kind='mock', setup_instructions='synthetic')
        with self.assertRaisesRegex(ValueError, 'stub/mock'):
            v.dossier(d, {'e1'}, self.root)

    def test_mock_run_cannot_pass_execution(self):
        d = self.case()
        d['identity'].update(identity_status='verified', identity_evidence_ids=['e1'])
        for s in v.STAGES[:4]:
            d['assessment']['stage_statuses'][s] = 'passed'
        d['implementation'].update(kind='independent', setup_instructions='synthetic',
                                   source_path=self.ref['path'], sha256=self.ref['sha256'], requires_inference=False)
        d['tests'].update(specification_path=self.ref['path'], sha256=self.ref['sha256'], fixed_at='2025-12-31T00:00:00Z', acceptance_criteria=['synthetic'], baseline_specification='synthetic')
        r = self.run_record()
        r['execution_kind'] = 'mock'
        self.save('run.json', json.dumps(r))
        d['assessment']['receipt_paths'] = ['run.json']
        with self.assertRaisesRegex(ValueError, 'no real passing'):
            v.dossier(d, {'e1'}, self.root)

    def accepted_case(self):
        d = self.case()
        d['record_status'] = 'tested'
        d['identity'].update(identity_status='verified', identity_evidence_ids=['e1'])
        d['assessment']['stage_statuses'] = {s: 'passed' for s in v.STAGES}
        d['implementation'].update(kind='independent', setup_instructions='synthetic', requires_inference=True,
                                   source_path=self.ref['path'], sha256=self.ref['sha256'])
        d['tests'].update(specification_path=self.ref['path'], sha256=self.ref['sha256'],
                          fixed_at='2025-12-31T00:00:00Z', acceptance_criteria=['synthetic'], baseline_specification='synthetic')
        r = self.run_record()
        r['inference_executed'] = True
        self.save('prototype.json', json.dumps(r))
        r.update(system='B1', run_id='baseline')
        self.save('baseline.json', json.dumps(r))
        d['assessment']['receipt_paths'] = ['prototype.json', 'baseline.json']
        verdict = {name: 'synthetic' for name in ('thesis', 'technical_assessment', 'commercial_assessment',
                   'next_falsification_test', 'reviewer')}
        verdict.update(recommendation='insufficient_evidence', supporting_claim_ids=[], counterevidence_claim_ids=[],
                       uncertainties=['synthetic'], reviewed_at='2026-01-02T00:00:00Z')
        self.save('verdict.json', json.dumps(verdict))
        d['assessment'].update(verdict_path='verdict.json', review={'reviewer': 'synthetic-independent',
                               'independent': True, 'accepted': True, 'unresolved_material_objections': [], 'artifact': self.ref})
        return d

    def test_structurally_accepted_synthetic_case(self):
        self.assertTrue(v.dossier(self.accepted_case(), {'e1'}, self.root))

    def test_missing_baseline_rejected(self):
        d = self.accepted_case()
        d['assessment']['receipt_paths'] = ['prototype.json']
        with self.assertRaisesRegex(ValueError, 'baseline not executed'):
            v.dossier(d, {'e1'}, self.root)

    def test_unresolved_review_rejected(self):
        d = self.accepted_case()
        d['assessment']['review']['unresolved_material_objections'] = ['Missing coverage']
        with self.assertRaisesRegex(ValueError, 'review not accepted'):
            v.dossier(d, {'e1'}, self.root)

    def test_central_inference_required(self):
        d = self.accepted_case()
        r = json.loads((self.root / 'prototype.json').read_text())
        r['inference_executed'] = False
        self.save('prototype.json', json.dumps(r))
        with self.assertRaisesRegex(ValueError, 'central inference'):
            v.dossier(d, {'e1'}, self.root)

    def test_empty_capture_is_not_claim_evidence(self):
        source = {'evidence_id': 'empty', 'source_url': 'https://synthetic.invalid/',
                  'publisher': None, 'retrieved_at': '2026-01-01T00:00:00Z', 'published_at': None,
                  'source_type': 'test', 'access_method': 'test', 'scope_limitations': 'test',
                  'excerpts': [], 'capture_path': self.ref['path'], 'capture_sha256': self.ref['sha256']}
        self.assertEqual(v.evidence({'schema_version': 1, 'sources': [source]}, self.root), set())

    def test_active_duration_uses_union(self):
        intervals = [{'started_at': '2026-01-01T00:00:00Z', 'ended_at': '2026-01-01T00:00:10Z', 'evidence': self.ref},
                     {'started_at': '2026-01-01T00:00:05Z', 'ended_at': '2026-01-01T00:00:15Z', 'evidence': self.ref}]
        self.assertEqual(v.active_seconds(intervals, self.root), 15)

    def test_unsupported_duration_rejected(self):
        self.reg.update(active_intervals=[], observed_active_campaign_seconds=86400,
                        duration_fulfilled=True, request_complete=False)
        with self.assertRaisesRegex(ValueError, 'unsupported active duration'):
            v.registry(self.reg, {'e1'}, self.root)

    def test_timestamp_validation(self):
        for value in ['2026-01-01', '2026-01-01T01:00:00+01:00', '2999-01-01T00:00:00Z', 'invalid']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                v.timestamp(value)


if __name__ == '__main__':
    unittest.main()
