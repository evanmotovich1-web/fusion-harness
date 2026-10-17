#!/usr/bin/env python3
"""Install only this workflow's native agents and commands; preserve other config."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import sys


def install(destination, runtime=None, workspace_root=None, *, check=False, opencode=None):
    source = Path(__file__).resolve().parent
    runtime = (runtime or source / 'runtime.py').resolve()
    opencode = str((opencode or Path.home() / '.opencode/bin/opencode').expanduser().absolute())
    if not runtime.is_file():
        raise ValueError(f'Runtime missing: {runtime}')
    destination = destination.expanduser().resolve()
    manifest = destination / 'opencode-adw-install.json'
    old = json.loads(manifest.read_text()) if manifest.exists() else {'files': {}}
    planned = []
    assets = [p for p in (source / 'assets').glob('*/*') if p.is_file() and
              ((p.parent.name in ('agents', 'commands') and p.suffix == '.md') or
               (p.parent.name == 'plugins' and p.suffix == '.js'))]
    for asset in sorted(assets):
        target = destination / asset.relative_to(source / 'assets')
        data = (asset.read_text().replace('@RUNTIME_JSON@', json.dumps(str(runtime)))
                .replace('@PYTHON_JSON@', json.dumps(sys.executable))
                .replace('@OPENCODE_JSON@', json.dumps(opencode))
                .replace('@RUNTIME@', shlex.quote(str(runtime)))
                .replace('@PYTHON@', shlex.quote(sys.executable))).encode()
        if target.exists():
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            if digest != old.get('files', {}).get(str(target)) and target.read_bytes() != data:
                raise ValueError(f'Locally modified or unowned asset; preserved: {target}')
        planned.append((target, data))
    if check:
        return {'runtime': str(runtime), 'planned': [str(target) for target, _ in planned],
                'opencode': opencode, 'plugin_protocol': 'v2',
                'writes': False, 'compatibility_verified': False}
    hashes = {}
    for target, data in planned:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + '.opencode-adw-tmp')
        tmp.write_bytes(data)
        tmp.replace(target)
        hashes[str(target)] = hashlib.sha256(data).hexdigest()
    workspace = str(workspace_root.expanduser().resolve()) if workspace_root else old.get('workspace_root')
    manifest.write_text(json.dumps({'runtime': str(runtime), 'workspace_root': workspace, 'files': hashes,
        'opencode': opencode, 'plugin_protocol': 'v2', 'compatibility_verified': False,
        'health_check': None,
        'health_check_template': [sys.executable, str(source / 'doctor.py'), '--opencode', opencode,
                                  '--project', '<PROJECT_1>', '--project', '<PROJECT_2>'],
        'health_check_required_arguments': 'Incomplete template: replace PROJECT_1 and PROJECT_2 with at least two distinct existing project directories.'}, indent=2) + '\n')
    return {'runtime': str(runtime), 'workspace_root': workspace, 'installed': list(hashes),
            'opencode': opencode, 'plugin_protocol': 'v2', 'compatibility_verified': False,
            'restart_required': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-dir', type=Path, default=Path.home() / '.config/opencode')
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--workspace-root', type=Path)
    parser.add_argument('--opencode', type=Path, help='Real V2 executable; never a bootstrap PATH wrapper')
    parser.add_argument('--check', action='store_true', help='Preflight ownership only; no writes or compatibility claim')
    args = parser.parse_args()
    print(json.dumps(install(args.config_dir, args.runtime, args.workspace_root,
                             check=args.check, opencode=args.opencode), indent=2))
