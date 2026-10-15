import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('oc_install', ROOT / 'install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def test_discovery_assets_render_and_reinstall_preserves_other_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'config with spaces'
            config.mkdir()
            existing = config / 'opencode.json'
            existing.write_text('{"mcp":{"existing":{"enabled":true}}}')
            before = existing.read_bytes()
            first = installer.install(config)
            self.assertEqual(len(first['installed']), 7)
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
