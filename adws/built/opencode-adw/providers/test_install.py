import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('provider_install', Path(__file__).with_name('install.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def catalog():
    return {'data': [{'provider': provider, 'modelId': 'test-model', 'id': provider + '/test-model',
                      'name': 'Test', 'context': 128000, 'maxTokens': 4096, 'reasoning': True}
                     for provider in module.NAMES]}


class ProviderInstallTests(unittest.TestCase):
    def test_merge_preserves_existing_mcp_and_openai_without_provider_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / 'config'
            config.mkdir()
            original = {'mcp': {'existing': {'enabled': True}}, 'provider': {'openai': {'name': 'Existing'}}}
            path = config / 'opencode.json'
            path.write_text(json.dumps(original))
            state = root / 'private'
            with patch.object(module.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(catalog()).encode())):
                result = module.install(config, state)
            installed = json.loads(path.read_text())
            self.assertEqual(installed['mcp'], original['mcp'])
            self.assertEqual(installed['provider']['openai'], original['provider']['openai'])
            self.assertEqual(len(result['providers']), 4)
            self.assertEqual((state / 'token').stat().st_mode & 0o777, 0o600)
            self.assertNotIn((state / 'token').read_text(), path.read_text())
            for provider in module.NAMES.values():
                definition = installed['provider'][provider[0]]
                self.assertEqual(definition['options']['apiKey'], '{file:' + str(state / 'token') + '}')
                self.assertEqual(definition['models']['test-model']['modalities']['input'], ['text'])

    def test_modified_provider_conflict_preserves_entire_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / 'config'
            config.mkdir()
            path = config / 'opencode.json'
            path.write_text(json.dumps({'provider': {'pi-grok': {'name': 'User version'}}}))
            before = path.read_bytes()
            with patch.object(module.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(catalog()).encode())):
                with self.assertRaisesRegex(ValueError, 'preserved'):
                    module.install(config, root / 'private')
            self.assertEqual(path.read_bytes(), before)

    def test_unknown_provider_and_nonlocal_endpoint_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = catalog()
            data['data'][0]['provider'] = 'unexpected'
            with patch.object(module.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(data).encode())):
                with self.assertRaisesRegex(ValueError, 'Unexpected provider'):
                    module.install(root / 'config', root / 'private')
            self.assertFalse((root / 'config/opencode.json').exists())
            with self.assertRaisesRegex(ValueError, 'loopback'):
                module.install(root / 'config', root / 'private', 'https://example.invalid')


if __name__ == '__main__':
    unittest.main()
