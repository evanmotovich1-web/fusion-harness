"""Source parser regressions only: no executable, model, Git or capture calls."""
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock


spec = importlib.util.spec_from_file_location('cli_event_runtime', Path(__file__).resolve().parents[1] / 'runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class CLIEventTests(unittest.TestCase):
    def parse(self, events, *, fails=False, prior=(), role='worker'):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            raw = ''.join(json.dumps(event) + '\n' for event in events)
            stdout = folder / 'stdout'
            stdout.write_text(raw)
            receipt = {'stdout': str(stdout), 'exit_code': 0}
            report = {'models': {role: 'openai/gpt-6.1-sol'}, 'agents': list(prior)}
            args = types.SimpleNamespace(repo=folder, timeout=1)
            with mock.patch.object(runtime, 'execute', return_value=receipt):
                if fails:
                    with self.assertRaises(runtime.Failure):
                        runtime._agent(args, report, folder, role, 'unused')
                else:
                    runtime._agent(args, report, folder, role, 'unused')
            self.assertEqual((folder / (role + '.events.jsonl')).read_text(), raw)
            return report['agents'][-1]

    def text(self, sid='ses_test'):
        return {'type': 'text', 'sessionID': sid, 'part': {'type': 'text', 'text': 'answer'}}

    def reasoning(self, sid='ses_test'):
        return {'type': 'reasoning', 'sessionID': sid,
                'part': {'type': 'reasoning', 'text': 'private reasoning evidence'}}

    def test_mixed_reasoning_and_text_retains_only_answer_text(self):
        for events in ([self.reasoning(), self.text()], [self.text(), self.reasoning()]):
            with self.subTest(events=events):
                stage = self.parse(events)
                self.assertEqual(stage['errors'], [])
                self.assertEqual(stage['session_ids'], ['ses_test'])
                self.assertEqual(stage['text'], 'answer')
                self.assertEqual(stage['last_text'], 'answer')
                report = {'agents': [stage], 'state': 'PASSED'}
                self.assertNotIn('private reasoning evidence', json.dumps(runtime.result_summary(report, Path('.'))))
                self.assertNotIn('private reasoning evidence', json.dumps(runtime.status_summary(report, Path('report.json'))))

    def test_malformed_reasoning_fails_alongside_valid_text(self):
        for part in (None, [], False, {}, {'text': None}, {'text': 4}, {'text': []}):
            event = dict(self.reasoning(), part=part)
            with self.subTest(part=part):
                stage = self.parse([self.text(), event], fails=True)
                self.assertTrue(stage['errors'])
        event = self.reasoning()
        del event['part']
        self.parse([self.text(), event], fails=True)

    def test_reasoning_preserves_session_and_error_guards(self):
        for sid in (None, '', ' ', 12, 'ses_other'):
            with self.subTest(sid=sid):
                self.parse([self.text(), self.reasoning(sid)], fails=True)
        self.parse([self.text(), dict(self.reasoning(), error={'message': 'provider error'})], fails=True)
        self.parse([self.text(), dict(self.reasoning(), part={
            'text': 'tool error', 'type': 'tool', 'state': {'status': 'error'}})], fails=True)

    def test_reasoning_is_not_answer_or_reviewer_json(self):
        self.parse([self.reasoning()], fails=True)
        review = json.dumps({'verdict': 'PASS', 'findings': [], 'evidence': ['inspected']})
        reasoning = self.reasoning()
        reasoning['part']['text'] = review
        self.parse([reasoning, self.text()], role='reviewer', fails=True)
        event = self.text()
        event['part']['text'] = review
        stage = self.parse([event, self.reasoning()], role='reviewer')
        self.assertEqual(stage['review']['verdict'], 'PASS')
        self.parse([event, self.reasoning()], role='reviewer',
                   prior=[{'session_ids': ['ses_test']}], fails=True)

    def test_mixed_unknown_envelopes_fail_and_retain_entire_unknown_event(self):
        for kind in ('future_event', None, [], {}):
            unknown = {'type': kind, 'sessionID': 'ses_test', 'payload': {'unknown': [1, 2]}}
            for events in ([unknown, self.text()], [self.text(), unknown]):
                with self.subTest(kind=kind, events=events):
                    stage = self.parse(events, fails=True)
                    self.assertEqual(stage['text'], 'answer')
                    self.assertIn({'error': 'Unsupported event type', 'event': unknown}, stage['errors'])
        unknown = {'sessionID': 'ses_test', 'payload': 'missing type'}
        self.parse([self.text(), unknown], fails=True)

    def test_malformed_known_envelopes_cannot_hide_behind_valid_text(self):
        malformed = [
            {'type': 'text'}, {'type': 'text', 'part': {}},
            {'type': 'text', 'part': {'text': 4}},
            {'type': 'text', 'part': []}, {'type': 'text', 'part': None},
            {'type': 'step_start'}, {'type': 'step_start', 'part': False},
            {'type': 'step_finish', 'part': {}},
            {'type': 'step_finish', 'part': {'tokens': []}},
            {'type': 'tool_use', 'part': {}},
            {'type': 'tool_use', 'part': {'state': []}},
            {'type': 'tool_use', 'part': {'state': {'status': 'running'}}},
            {'type': 'start', 'part': None}, {'type': 'finish', 'part': []},
        ]
        for event in malformed:
            event = dict(event, sessionID='ses_test')
            with self.subTest(event=event):
                self.assertTrue(self.parse([self.text(), event], fails=True)['errors'])

    def test_v2_start_finish_envelopes_are_supported_without_parts(self):
        stage = self.parse([{'type': 'start', 'sessionID': 'ses_test'}, self.text(),
                            {'type': 'finish', 'sessionID': 'ses_test'}])
        self.assertEqual(stage['errors'], [])
        self.assertEqual(stage['session_ids'], ['ses_test'])
        self.assertEqual(stage['text'], 'answer')

    def test_normalized_steps_tools_and_usage_remain_supported(self):
        tool = {'type': 'tool', 'state': {'status': 'completed'}}
        stage = self.parse([
            {'type': 'step_start', 'sessionID': 'ses_test', 'part': {'type': 'step-start'}},
            {'type': 'tool_use', 'sessionID': 'ses_test', 'part': tool}, self.text(),
            {'type': 'step_finish', 'sessionID': 'ses_test',
             'part': {'tokens': {'input': 2, 'output': 3}, 'cost': 0.1}},
        ])
        self.assertEqual(stage['tools'], [tool])
        self.assertEqual(stage['usage'], [{'tokens': {'input': 2, 'output': 3}, 'cost': 0.1}])

    def test_error_and_tool_errors_remain_fatal_with_valid_text(self):
        for event in (
            {'type': 'error', 'error': {'message': 'provider error'}},
            {'type': 'finish', 'error': {'message': 'provider error'}},
            {'type': 'tool_use', 'part': {'state': {'status': 'error'}}},
            {'type': 'tool_use', 'part': {'state': {'status': 'completed', 'error': 'failed'}}},
            {'type': 'text', 'part': {'text': 'tool error', 'type': 'tool',
                                     'state': {'status': 'error'}}},
        ):
            with self.subTest(event=event):
                self.parse([self.text(), dict(event, sessionID='ses_test')], fails=True)

    def test_lifecycle_does_not_replace_required_text(self):
        self.parse([{'type': 'start', 'sessionID': 'ses_test'},
                    {'type': 'finish', 'sessionID': 'ses_test'}], fails=True)

    def test_lifecycle_does_not_weaken_session_validation(self):
        for sid in (None, '', ' ', 12, 'ses_other'):
            with self.subTest(sid=sid):
                self.parse([self.text(), {'type': 'finish', 'sessionID': sid}], fails=True)

    def test_reviewer_still_requires_independent_session(self):
        event = self.text()
        event['part']['text'] = json.dumps({'verdict': 'PASS', 'findings': [], 'evidence': ['inspected']})
        self.parse([{'type': 'start', 'sessionID': 'ses_test'}, event,
                    {'type': 'finish', 'sessionID': 'ses_test'}], role='reviewer',
                   prior=[{'session_ids': ['ses_test']}], fails=True)


if __name__ == '__main__':
    unittest.main()
