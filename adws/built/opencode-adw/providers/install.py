#!/usr/bin/env python3
"""Connect OpenCode to existing Pi model credentials through the local transport."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import urllib.request


NAMES = {'deepseek': ('pi-deepseek', 'DeepSeek'), 'zai-coding-cn': ('pi-glm', 'GLM'),
         'xai': ('pi-grok', 'Grok'), 'google-gemini-cli': ('pi-gemini', 'Gemini')}


def prepare(state):
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    state.chmod(0o700)
    token = state / 'token'
    if not token.exists():
        fd = os.open(token, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as handle:
            handle.write(secrets.token_urlsafe(48))
    token.chmod(0o600)
    return token


def install(config_dir, state, base_url='http://127.0.0.1:4198'):
    if base_url != 'http://127.0.0.1:4198':
        raise ValueError('Installer supports only the owned loopback bridge at port 4198')
    token = prepare(state)
    req = urllib.request.Request(base_url + '/v1/models', headers={
        'Authorization': 'Bearer ' + token.read_text().strip()})
    with urllib.request.urlopen(req, timeout=10) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('Catalog exceeds size limit')
    models = json.loads(raw)['data']
    if not isinstance(models, list) or not models:
        raise ValueError('No models with existing credentials were discovered')
    providers = {}
    for entry in models:
        source = entry['provider']
        if source not in NAMES:
            raise ValueError('Unexpected provider in catalog')
        provider_id, display = NAMES[source]
        provider = providers.setdefault(provider_id, {
            'npm': '@ai-sdk/openai-compatible', 'name': display + ' · existing connection',
            'options': {'baseURL': base_url + '/v1', 'apiKey': '{file:' + str(token) + '}'},
            'models': {}, 'whitelist': [],
        })
        model_id = entry['modelId']
        provider['models'][model_id] = {
            'id': entry['id'], 'name': entry.get('name') or model_id,
            'limit': {'context': entry['context'], 'output': entry['maxTokens']},
            'tool_call': True, 'reasoning': bool(entry.get('reasoning')),
            'modalities': {'input': ['text'], 'output': ['text']},
        }
        provider['whitelist'].append(model_id)
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / 'opencode.json'
    before = path.read_bytes() if path.exists() else b'{}'
    config = json.loads(before)
    manifest_path = state / 'install.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {'providers': {}}
    current = config.setdefault('provider', {})
    for key, provider in providers.items():
        if key in current and current[key] != manifest.get('providers', {}).get(key) and current[key] != provider:
            raise ValueError(f'Unowned or locally modified provider preserved: {key}')
    config.setdefault('$schema', 'https://opencode.ai/config.json')
    current.update(providers)
    if path.exists() and path.read_bytes() != before:
        raise ValueError('OpenCode configuration changed during installation; retry')
    digest = hashlib.sha256(before).hexdigest()[:12]
    backup = state / ('opencode-before-' + digest + '.json')
    if not backup.exists():
        backup.write_bytes(before)
        backup.chmod(0o600)
    temporary = path.with_suffix('.json.provider-tmp')
    temporary.write_text(json.dumps(config, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)
    manifest_path.write_text(json.dumps({'providers': providers, 'config': str(path), 'backup': str(backup)}, indent=2) + '\n')
    manifest_path.chmod(0o600)
    return {'providers': {key: len(value['models']) for key, value in providers.items()},
            'config': str(path), 'restart_required': True,
            'credential_source': 'existing Pi auth for DeepSeek/GLM/Grok; official Gemini CLI login; no copied provider tokens'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-dir', type=Path, default=Path.home() / '.config/opencode')
    parser.add_argument('--state-dir', type=Path, default=Path.home() / '.local/share/opencode-adw/provider-bridge')
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    if args.prepare:
        print(json.dumps({'token_file': str(prepare(args.state_dir)), 'token_value': 'not displayed'}))
    else:
        print(json.dumps(install(args.config_dir, args.state_dir), indent=2))
