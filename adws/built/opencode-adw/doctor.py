#!/usr/bin/env python3
"""Read-only, version-aware update health check. Never upgrade, reload or repair.

Exit 0 means only the listed probes passed, not native tool execution. Exit 1
requires operator investigation. Recovery is bounded to ownership preflight and
an operator-run installer; there is no AI rewrite or automatic retry loop.
"""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import urllib.parse


def v2_contract(document):
    """Check the required public API shapes, not merely a version string."""
    try:
        paths = document['paths']
        create = paths['/api/session']['post']
        props = create['requestBody']['content']['application/json']['schema']['properties']
        prompt = paths['/api/session/{sessionID}/prompt']['post']
        prompt_schema = prompt['requestBody']['content']['application/json']['schema']
        return (all(k in props for k in ('parentID', 'location', 'agent', 'model')) and
                prompt_schema['required'] == ['text'] and 'resume' in prompt_schema['properties'] and
                all('204' in paths['/api/session/{sessionID}/' + action]['post']['responses']
                    for action in ('move', 'agent', 'model')) and
                '200' in paths['/api/session/{sessionID}/interrupt']['post']['responses'] and
                '200' in paths['/api/session/{sessionID}/context']['get']['responses'])
    except (KeyError, TypeError):
        return False


def probe(binary, args, cwd):
    try:
        # 2.0.32 can exit before draining large piped CLI output (observed
        # OpenAPI truncation at 262144 bytes). A private, unlinked regular-file
        # sink avoids that race; no config or durable diagnostic file is written.
        temporary_root = Path(tempfile.gettempdir()) / 'opencode'
        with tempfile.TemporaryFile(dir=temporary_root if temporary_root.is_dir() else None) as output:
            result = subprocess.run([binary, *args], cwd=cwd, stdout=output,
                                    stderr=subprocess.DEVNULL, timeout=15)
            if result.returncode:
                return None
            output.seek(0)
            raw = output.read(16 * 1024 * 1024 + 1)
            return raw.decode() if len(raw) <= 16 * 1024 * 1024 else None
    except (OSError, UnicodeError, subprocess.SubprocessError):
        return None


def inspect(binary, projects, runner=probe):
    version = runner(binary, ['--version'], projects[0])
    match = re.fullmatch(r'(?:opencode\s+)?v?(\d+)\.(\d+)\.(\d+)\s*', version or '')
    parsed = tuple(map(int, match.groups())) if match else None
    # Only the locally observed V2 release has evidence. Other versions are not
    # assumed compatible, including later patches and prereleases.
    known = parsed == (2, 0, 32)
    help_text = runner(binary, ['run', '--help'], projects[0]) or ''
    cli_ok = all(flag in help_text for flag in ('--format', '--agent', '--model'))
    try:
        contract_ok = known and v2_contract(json.loads(
            runner(binary, ['api', 'get', '/openapi.json'], projects[0]) or 'null'))
    except (ValueError, TypeError):
        contract_ok = False
    locations = []
    for project in projects:
        query = urllib.parse.urlencode({'location[directory]': str(project)})
        raw = runner(binary, ['api', 'get', '/api/plugin?' + query], project) if known else None
        try:
            value = json.loads(raw or '')
            rows = value.get('data') if isinstance(value, dict) else None
            location = value.get('location', {}).get('directory') if isinstance(value, dict) else None
            rows = rows if isinstance(rows, list) else []
            matches = [row for row in rows if isinstance(row, dict) and (
                row.get('id') == 'opencode-team' or
                isinstance(row.get('source'), dict) and
                str(row['source'].get('path', '')).endswith('/opencode-team.js'))]
            states = [row.get('state', {}).get('status') for row in matches
                      if isinstance(row.get('state'), dict)]
            states = [state if state in ('active', 'failed', 'disabled') else 'unknown'
                      for state in states]
            # Do not echo loader exceptions: arbitrary plugin errors can contain secrets.
            loaded = len(matches) == 1 and states == ['active'] and location == str(project)
        except (ValueError, TypeError, AttributeError):
            loaded, states, location = False, [], None
        locations.append({'project': str(project), 'location_matches': location == str(project),
                          'plugin_states': states, 'plugin_loaded': loaded})
    healthy = known and cli_ok and contract_ok and bool(locations) and all(row['plugin_loaded'] for row in locations)
    source = Path(__file__).resolve().parent
    return {'state': 'PROBES_PASSED' if healthy else 'BLOCKED',
            'version': '.'.join(map(str, parsed)) if parsed else None,
            'version_evidence': 'observed' if known else 'unverified',
            'cli_flags_present': cli_ok, 'api_contract_matches': bool(contract_ok),
            'cwd_transport': True, 'locations': locations,
            'tool_discovery_verified': False, 'status_tool_call_verified': False,
            'native_v2_transport_verified': False,
            'recovery': {'automatic_writes': False, 'max_automatic_retries': 0,
                         'ownership_preflight': shlex.join([sys.executable, str(source / 'install.py'), '--check']),
                         'activation': 'Blocked pending real V2 discovery and native status execution; do not reinstall yet.'}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--opencode', required=True, help='Explicit real executable, not a bootstrap wrapper')
    parser.add_argument('--project', type=Path, action='append', required=True)
    args = parser.parse_args(argv)
    projects = [project.expanduser().resolve() for project in args.project]
    if len(set(projects)) < 2 or any(not project.is_dir() for project in projects):
        parser.error('provide at least two distinct existing project locations')
    result = inspect(args.opencode, projects)
    print(json.dumps(result, indent=2))
    return 0 if result['state'] == 'PROBES_PASSED' else 1


if __name__ == '__main__':
    sys.exit(main())
