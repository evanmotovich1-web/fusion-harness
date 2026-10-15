#!/usr/bin/env python3
"""Install only this workflow's native agents and commands; preserve other config."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import sys


def install(destination, runtime=None):
    source = Path(__file__).resolve().parent
    runtime = (runtime or source / 'runtime.py').resolve()
    if not runtime.is_file():
        raise ValueError(f'Runtime missing: {runtime}')
    destination = destination.expanduser().resolve()
    manifest = destination / 'opencode-adw-install.json'
    old = json.loads(manifest.read_text()) if manifest.exists() else {'files': {}}
    planned = []
    for asset in sorted((source / 'assets').glob('*/*.md')):
        target = destination / asset.relative_to(source / 'assets')
        data = asset.read_text().replace('@RUNTIME@', shlex.quote(str(runtime))).replace('@PYTHON@', shlex.quote(sys.executable)).encode()
        if target.exists():
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            if digest != old.get('files', {}).get(str(target)) and target.read_bytes() != data:
                raise ValueError(f'Locally modified or unowned asset; preserved: {target}')
        planned.append((target, data))
    hashes = {}
    for target, data in planned:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix('.md.opencode-adw-tmp')
        tmp.write_bytes(data)
        tmp.replace(target)
        hashes[str(target)] = hashlib.sha256(data).hexdigest()
    manifest.write_text(json.dumps({'runtime': str(runtime), 'files': hashes}, indent=2) + '\n')
    return {'runtime': str(runtime), 'installed': list(hashes), 'restart_required': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-dir', type=Path, default=Path.home() / '.config/opencode')
    parser.add_argument('--runtime', type=Path)
    args = parser.parse_args()
    print(json.dumps(install(args.config_dir, args.runtime), indent=2))
