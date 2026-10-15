"""Required native custom-agent inventory; no inference or home writes."""
from pathlib import Path
import unittest

PACKAGE = Path(__file__).resolve().parents[2]

class PackageInventoryTests(unittest.TestCase):
    def test_required_inference_only_native_agent_is_packaged(self):
        agent = PACKAGE / 'agents/host-model-bridge.md'
        self.assertTrue(agent.is_file(), 'Required --agent host-model-bridge definition is missing from the package')
        text = agent.read_text(encoding='utf-8')
        self.assertTrue(text.startswith('---\n'))
        front = text.split('---', 2)[1]
        fields = dict(line.split(':', 1) for line in front.strip().splitlines())
        self.assertEqual(fields['name'].strip(), 'host-model-bridge')
        self.assertEqual(fields['kind'].strip(), 'local')
        self.assertEqual(fields['model'].strip(), 'inherit')
        self.assertEqual(fields['tools'].strip(), '[]')
        self.assertIn('Do not invent tool results.', text)
        self.assertIn('Never substitute a different model or account.', text)

if __name__ == '__main__':
    unittest.main()
