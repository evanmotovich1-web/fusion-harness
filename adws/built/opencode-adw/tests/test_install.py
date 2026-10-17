import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('oc_install', ROOT / 'install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def test_health_check_is_explicitly_incomplete_and_replaces_legacy_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'config'
            installer.install(config)
            manifest = config / 'opencode-adw-install.json'
            old = json.loads(manifest.read_text())
            old['health_check'] = ['python3', 'doctor.py', '--opencode', '/old/opencode']
            manifest.write_text(json.dumps(old))
            binary = Path(tmp) / 'binary with spaces' / 'opencode'
            installer.install(config, workspace_root=Path(tmp), opencode=binary)
            recorded = json.loads(manifest.read_text())
            self.assertIsNone(recorded['health_check'])
            self.assertEqual(recorded['health_check_template'], [
                installer.sys.executable, str(ROOT / 'doctor.py'), '--opencode', str(binary),
                '--project', '<PROJECT_1>', '--project', '<PROJECT_2>'])
            self.assertIn('Incomplete template', recorded['health_check_required_arguments'])
            self.assertIn('two distinct existing project directories',
                          recorded['health_check_required_arguments'])
            self.assertFalse(recorded['compatibility_verified'])

    def test_completed_health_check_template_satisfies_doctor_arguments(self):
        doctor_spec = importlib.util.spec_from_file_location('oc_doctor', ROOT / 'doctor.py')
        doctor = importlib.util.module_from_spec(doctor_spec)
        doctor_spec.loader.exec_module(doctor)
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'config'
            projects = [Path(tmp) / 'project one', Path(tmp) / 'project two']
            for project in projects:
                project.mkdir()
            installer.install(config)
            recorded = json.loads((config / 'opencode-adw-install.json').read_text())
            replacements = dict(zip(('<PROJECT_1>', '<PROJECT_2>'), map(str, projects)))
            argv = [replacements.get(arg, arg) for arg in recorded['health_check_template']]
            with patch.object(doctor, 'inspect', return_value={'state': 'PROBES_PASSED'}) as inspect, \
                    patch('builtins.print'):
                self.assertEqual(doctor.main(argv[2:]), 0)
            inspect.assert_called_once_with(recorded['opencode'], [p.resolve() for p in projects])

    def test_discovery_assets_render_and_reinstall_preserves_other_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'config with spaces'
            config.mkdir()
            existing = config / 'opencode.json'
            existing.write_text('{"mcp":{"existing":{"enabled":true}}}')
            before = existing.read_bytes()
            first = installer.install(config)
            self.assertEqual(len(first['installed']), 14)
            self.assertTrue(first['restart_required'])
            self.assertEqual(existing.read_bytes(), before)
            self.assertIn('mode: primary', (config / 'agents/opencode-adw.md').read_text())
            command = (config / 'commands/oc-build.md').read_text()
            self.assertNotIn('@RUNTIME@', command)
            self.assertIn(str(ROOT / 'runtime.py'), command)
            self.assertEqual(first, installer.install(config))
            self.assertEqual(json.loads((config / 'opencode-adw-install.json').read_text())['runtime'], str(ROOT / 'runtime.py'))

    def test_unowned_collision_prevents_partial_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            (config / 'agents').mkdir()
            other = config / 'agents/opencode-worker.md'
            other.write_text('user owned content')
            with self.assertRaisesRegex(ValueError, 'preserved'):
                installer.install(config)
            self.assertEqual(other.read_text(), 'user owned content')
            self.assertFalse((config / 'agents/opencode-adw.md').exists())
            self.assertFalse((config / 'opencode-adw-install.json').exists())

    def test_locally_modified_managed_asset_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            installer.install(config)
            changed = config / 'commands/oc-review.md'
            changed.write_text('local correction')
            with self.assertRaisesRegex(ValueError, 'preserved'):
                installer.install(config)
            self.assertEqual(changed.read_text(), 'local correction')


if __name__ == '__main__':
    unittest.main()
