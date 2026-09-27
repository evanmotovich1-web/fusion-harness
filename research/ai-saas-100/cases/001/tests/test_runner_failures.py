"""Real short local child failures with persistent receipts; no mocked subprocess calls."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location('pilot_runner', HERE / 'execute_pilots.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
import validate

BASE = 'cases/001/tests/runner-failures-v1'
ATTEMPTS = []


def job(mode):
    child = BASE + '/child.py'
    command = [sys.executable, '-B', str(ROOT / child), mode, str(ROOT / BASE / 'suite.json')]
    if mode == 'launch_error':
        command = [str(ROOT / BASE / 'deliberately-nonexistent-executable')]
    return {'case_id': '001', 'command': command, 'runner': child, 'suite': BASE + '/suite.json',
            'implementation': child, 'input_bundle': BASE + '/suite.json',
            'input_bundle_scope': 'Synthetic runner validation only', 'test_only': True,
            'receipt_directory': BASE + '/receipts'}


class RunnerTests(unittest.TestCase):
    def receipt(self, summary):
        ATTEMPTS.append(summary)
        receipt = json.loads((ROOT / summary['receipt_path']).read_text())
        validate.receipt(receipt, ROOT)
        self.assertFalse(receipt['product_acceptance'])
        self.assertFalse(receipt['inference_executed'])
        for reference in receipt['outputs']:
            data = (ROOT / reference['path']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), reference['sha256'])
        return receipt

    def failure_then_success(self, mode, expected_kind):
        results = runner.run_batch([job(mode), job('success')], timeout=0.25)
        first, second = [self.receipt(result) for result in results]
        self.assertFalse(results[0]['successful'])
        self.assertEqual(first['failure_kind'], expected_kind)
        self.assertTrue(first['errors'])
        self.assertTrue(results[1]['successful'])
        self.assertEqual(second['status'], 'completed')
        self.assertEqual(results[1]['passed_local_regressions'], 3)
        self.assertEqual(results[1]['expected_local_regressions'], 3)
        return first

    def test_timeout_preserves_partial_output_and_reaps_child(self):
        receipt = self.failure_then_success('timeout', 'timeout')
        self.assertEqual(receipt['status'], 'failed')
        self.assertIsInstance(receipt['exit_status'], int)
        self.assertNotEqual(receipt['exit_status'], 0)
        self.assertTrue(receipt['timeouts'])
        self.assertIn(b'partial stdout', (ROOT / receipt['outputs'][0]['path']).read_bytes())
        self.assertIn(b'partial stderr', (ROOT / receipt['outputs'][1]['path']).read_bytes())

    def test_launch_failure_has_no_fabricated_process_exit(self):
        receipt = self.failure_then_success('launch_error', 'launch_error')
        self.assertEqual(receipt['status'], 'blocked')
        self.assertIsNone(receipt['started_at'])
        self.assertIsNone(receipt['ended_at'])
        self.assertIsNone(receipt['exit_status'])
        self.assertFalse(receipt['process_started'])
        self.assertIsNotNone(receipt['attempt_started_at'])

    def test_nonzero_exit_with_valid_json(self):
        receipt = self.failure_then_success('nonzero_exit', 'nonzero_exit')
        self.assertEqual(receipt['exit_status'], 7)
        self.assertEqual(len(receipt['test_results']), 3)

    def test_malformed_json_and_raw_bytes(self):
        for mode in ['malformed_json', 'invalid_utf8']:
            with self.subTest(mode=mode):
                self.failure_then_success(mode, 'malformed_json')

    def test_malformed_result_schemas(self):
        for mode in ['root_array', 'null_results', 'row_array', 'missing_key', 'bad_outcome_type',
                     'bad_outcome', 'duplicate_id', 'missing_result', 'unexpected_id']:
            with self.subTest(mode=mode):
                self.failure_then_success(mode, 'malformed_result_schema')

    def test_failed_and_blocked_assertions_are_unsuccessful(self):
        for mode in ['assertion_failed', 'assertion_blocked']:
            with self.subTest(mode=mode):
                self.failure_then_success(mode, 'unsuccessful_results')

    def test_preflight_failure_also_continues(self):
        invalid = job('success')
        invalid['suite'] = BASE + '/absent-suite.json'
        results = runner.run_batch([invalid, job('success')], timeout=0.25)
        failed, succeeded = [self.receipt(result) for result in results]
        self.assertEqual(failed['failure_kind'], 'preflight_error')
        self.assertEqual(succeeded['status'], 'completed')


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RunnerTests))
    summary = {'schema_version': 1, 'recorded_at': runner.now(), 'test_only': True,
               'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
               'attempts': ATTEMPTS, 'product_acceptance': False}
    destination = ROOT / BASE / ('validation-' + runner.uuid.uuid4().hex + '.json')
    with destination.open('x') as f:
        json.dump(summary, f, indent=2)
    print('Validation report: ' + str(destination.relative_to(ROOT)))
    raise SystemExit(0 if result.wasSuccessful() else 1)
