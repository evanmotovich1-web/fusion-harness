"""Execute frozen, external tests and keep native counts; no model/network calls."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import traceback
import unittest


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def python_record(load_error=None):
    return {'testsRun': 0, 'errors': [], 'failures': [], 'skipped': [],
            'expected_failures': 0, 'unexpected_successes': 0, 'load_error': load_error}


def validate_python_record(record):
    if not isinstance(record, dict):
        raise ValueError('expected an object')
    for name in ('testsRun', 'expected_failures', 'unexpected_successes'):
        if name not in record or type(record[name]) is not int or record[name] < 0:
            raise ValueError(name + ' must be a nonnegative integer (not bool)')
    for name in ('errors', 'failures', 'skipped'):
        if name not in record or type(record[name]) is not list:
            raise ValueError(name + ' must be a list')
    if 'load_error' not in record or (record['load_error'] is not None and not isinstance(record['load_error'], str)):
        raise ValueError('load_error must be null or a string')


def python_suite(path, repo, receipt_path):
    """Child entrypoint. Keep discovery/import errors separate from genuine red tests."""
    os.environ['OPENCODE_ADW_REPO'] = str(repo)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(repo))
    record = python_record()
    module_name = 'adw_frozen_tests'
    absent = object()
    previous = sys.modules.get(module_name, absent)
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromModule(module)
        if loader.errors:
            raise ValueError('\n'.join(loader.errors))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        record.update(testsRun=result.testsRun,
                      errors=[{'test': str(test), 'traceback': text} for test, text in result.errors],
                      failures=[{'test': str(test), 'traceback': text} for test, text in result.failures],
                      skipped=[{'test': str(test), 'reason': reason} for test, reason in result.skipped],
                      expected_failures=len(result.expectedFailures),
                      unexpected_successes=len(result.unexpectedSuccesses))
    except BaseException:
        record['load_error'] = traceback.format_exc()
        traceback.print_exc()
    finally:
        if previous is absent:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous
    Path(receipt_path).write_text(json.dumps(record, indent=2) + '\n')
    meaningful = record['testsRun'] - len(record.get('skipped', [])) - record.get('expected_failures', 0)
    return 0 if (meaningful > 0 and not record['load_error'] and not record['errors']
                 and not record['failures'] and not record.get('unexpected_successes')) else 1


def execute_suite(rt, args, suite, folder, label):
    path = Path(suite['path'])
    prefix = folder / label
    if suite['format'] == 'python_unittest':
        result_path = folder / (label + '.unittest.json')
        process = rt.execute([sys.executable, str(Path(__file__).resolve()), str(path),
                              str(args.repo), str(result_path)], args.repo, args.timeout, prefix)
        try:
            record = json.loads(result_path.read_text())
            validate_python_record(record)
        except (OSError, ValueError) as exc:
            record = python_record('Invalid unittest receipt: ' + str(exc))
        count = record['testsRun']
        valid = count > 0 and record['load_error'] is None
        meaningful = count - len(record['skipped']) - record['expected_failures']
        successful = not record['errors'] and not record['failures'] and not record['unexpected_successes']
    else:
        # Set the environment only in a dedicated child, not in the runner's global state.
        launcher = ('import os,sys; os.environ["OPENCODE_ADW_REPO"]=sys.argv[1]; '
                    'os.execvp("node", ["node", "--test", "--test-reporter=tap", sys.argv[2]])')
        process = rt.execute([sys.executable, '-c', launcher, str(args.repo), str(path)],
                             args.repo, args.timeout, prefix)
        text = Path(process['stdout']).read_text(errors='replace')
        def counter(name):
            found = re.findall(r'^# ' + name + r' (\d+)\s*$', text, re.M)
            return int(found[-1]) if len(found) == 1 else None
        count = counter('tests')
        record = {name: counter(name) for name in ('tests', 'pass', 'fail', 'cancelled', 'skipped', 'todo')}
        file_failure = bool(re.search(r'^# Subtest: ' + re.escape(str(path)) + r'\s*$', text, re.M))
        valid = count is not None and count > 0 and not file_failure
        meaningful = (record['pass'] or 0) + (record['fail'] or 0)
        successful = True  # Native Node exit status owns TAP failure handling.
        if not valid:
            record['load_error'] = 'Missing/empty native TAP counts or file-level test failure'
    return {'kind': 'generated', 'label': label, 'format': suite['format'], 'process': process,
            'actual_tests': count or 0, 'valid_suite': bool(valid), 'result': record,
            'passed': bool(valid and meaningful > 0 and successful
                           and not process.get('error') and process['exit_code'] == 0)}


if __name__ == '__main__':
    sys.exit(python_suite(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])))
