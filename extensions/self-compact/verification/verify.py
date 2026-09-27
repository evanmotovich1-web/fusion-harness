"""Focused checks only; all output stays beside this file. No paid provider calls."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

out = Path(__file__).resolve().parent
root = out.parents[2]
package = Path(os.environ['PI_AGENT_PACKAGE'])
tsc = os.environ['TSC_JS']
config = {'compilerOptions': {'target': 'ES2022', 'module': 'NodeNext',
    'moduleResolution': 'NodeNext', 'strict': True, 'skipLibCheck': True,
    'noEmit': True, 'allowImportingTsExtensions': True, 'types': ['node'],
    'typeRoots': [str(package / 'node_modules/@types')],
    'paths': {'@earendil-works/pi-coding-agent': [str(package / 'dist/index.d.ts')]}},
    'files': ['../self-compact.ts']}
(out / 'tsconfig.local.json').write_text(json.dumps(config, indent=2) + '\n')
variants = [[], ['compact-soft-at=20%', 'compact-at=50%', 'compact-buffer=10%'],
    ['compactions-soft-at=100k', 'compactions-at=200k', 'compact-buffer=50k'],
    ['compact-soft-at=250k', 'compact-at=35%', 'compact-buffer=50k'],
    ['compact-buffer=0'], ['compact-prompt=EXACT_LITERAL'], ['compact-soft-at=invalid'],
    ['compact-soft-at=10', 'compact-at=20', 'compact-buffer=10']]
checks = [('unit', ['bun', 'test', 'extensions/self-compact/self-compact.test.ts']),
    ('types', ['node', tsc, '-p', str(out / 'tsconfig.local.json')])]
checks += [(f'runtime-{i}', ['node', str(out / 'runtime-smoke.mjs'), *args])
           for i, args in enumerate(variants)]
checks += [('cli-help', ['pi', '--no-extensions', '--no-skills', '--no-prompt-templates',
    '--no-themes', '--no-context-files', '--no-session', '-e',
    str(root / 'extensions/self-compact/self-compact.ts'), '--help'])]
env = dict(os.environ, PI_CODING_AGENT_DIR=str(out / '.cli'))
results = []
for name, args in checks:
    # File output also avoids Pi's process-exit truncation when stdout is piped.
    with (out / f'{name}.txt').open('w') as log:
        result = subprocess.run(args, cwd=root, env=env, stdout=log,
            stderr=subprocess.STDOUT, timeout=20)
    results.append({'name': name, 'argv': args, 'exit': result.returncode})
    print(f'{name}: exit {result.returncode}', flush=True)
    assert result.returncode == 0, (out / f'{name}.txt').read_text()
help_text = (out / 'cli-help.txt').read_text()
for flag in ['compact-soft-at', 'compact-at', 'compact-buffer', 'compact-prompt',
             'compactions-soft-at', 'compactions-at']:
    assert flag in help_text, flag
files = [root / 'extensions/self-compact/self-compact.ts',
         root / 'extensions/self-compact/self-compact.test.ts',
         *sorted((root / '.pi/self-compact').glob('*.md'))]
(out / 'results.json').write_text(json.dumps({'checks': results,
    'sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}, indent=2) + '\n')
