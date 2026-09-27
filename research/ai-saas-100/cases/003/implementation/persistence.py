"""Synthetic local CRM persistence. Structured commands only, no model or network.

Approval is a boundary between API operations, not user authentication. The local
operator and storage directory are trusted. This is not a production CRM service.
"""
import argparse
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import uuid

from workflow import preview

CASE = Path(__file__).resolve().parents[1]
STORAGE_ROOT = CASE / 'synthetic-storage'


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError('invalid_json_value') from exc


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def same(left, right):
    # JSON equality must distinguish booleans from integer revisions.
    return canonical(left) == canonical(right)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


class SyntheticStore:
    def __init__(self, name):
        require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name),
                'invalid_store_name')
        require(not STORAGE_ROOT.is_symlink(), 'unsafe_storage_root')
        STORAGE_ROOT.mkdir(exist_ok=True, mode=0o700)
        self.root = STORAGE_ROOT / name
        require(not self.root.is_symlink(), 'unsafe_store_path')
        self.root.mkdir(exist_ok=True, mode=0o700)
        self.path = self.root / 'state.json'
        self.lock_path = self.root / 'store.lock'

    @contextmanager
    def _locked(self):
        require(not self.root.is_symlink() and not STORAGE_ROOT.is_symlink(), 'unsafe_store_path')
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'unsafe_lock_file')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError('store_busy') from exc
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def _load(self):
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'r') as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'unsafe_state_file')
            state = json.load(stream)
        require(isinstance(state, dict) and state.get('schema_version') == 1, 'invalid_store')
        require(isinstance(state.get('store_id'), str) and bool(state['store_id']), 'invalid_store')
        require(type(state.get('revision')) is int and state['revision'] > 0, 'invalid_revision')
        require(isinstance(state.get('proposals'), dict), 'invalid_store')
        preview({'action': 'dedupe', 'contacts': state.get('contacts')})
        canonical(state)
        return state

    def _save(self, state):
        # One replacement commits contacts, revision and consumed approval together.
        require(not self.path.is_symlink(), 'unsafe_state_file')
        if self.path.exists():
            require(self.path.stat().st_nlink == 1, 'unsafe_state_file')
        data = canonical(state)
        fd, filename = tempfile.mkstemp(prefix='.state-', suffix='.tmp', dir=self.root)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(data + '\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(filename, self.path)
            directory = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(filename):
                os.unlink(filename)

    def initialize(self, contacts):
        canonical(contacts)
        preview({'action': 'dedupe', 'contacts': contacts})
        with self._locked():
            require(not self.path.exists() and not self.path.is_symlink(), 'store_already_initialized')
            self._save({'schema_version': 1, 'store_id': uuid.uuid4().hex, 'revision': 1,
                        'contacts': deepcopy(contacts), 'proposals': {}})
            return self._public(self._load())

    @staticmethod
    def _public(state):
        return deepcopy({key: state[key] for key in ('store_id', 'revision', 'contacts')})

    def read(self):
        with self._locked():
            return self._public(self._load())

    def propose(self, request):
        require(isinstance(request, dict) and set(request) <= {'action', 'patch'},
                'structured_action_required')
        canonical(request)
        with self._locked():
            state = self._load()
            result = preview(dict(deepcopy(request), contacts=deepcopy(state['contacts'])))
            before = deepcopy(state['contacts'])
            after = deepcopy(before)
            changes = []
            for operation in result['operations']:
                if operation['operation'] == 'merge_preview':
                    duplicates = set(operation['duplicate_ids'])
                    for contact in before:
                        if contact['id'] in duplicates:
                            changes.append({'operation': 'delete', 'id': contact['id'],
                                            'retain_id': operation['retain_id'],
                                            'before': deepcopy(contact), 'after': None})
                    after = [c for c in after if c['id'] not in duplicates]
                elif not same(operation['before'], operation['after']):
                    identifier = operation['before']['id']
                    changes.append({'operation': 'update', 'id': identifier,
                                    'before': deepcopy(operation['before']),
                                    'after': deepcopy(operation['after'])})
                    after = [deepcopy(operation['after']) if c['id'] == identifier else c for c in after]
            proposal = {'schema_version': 1, 'proposal_id': uuid.uuid4().hex,
                        'store_id': state['store_id'], 'source_revision': state['revision'],
                        'source_contacts_sha256': digest(before), 'before': before,
                        'after': after, 'changes': changes, 'no_op': same(before, after)}
            state['proposals'][proposal['proposal_id']] = {
                'proposal': deepcopy(proposal), 'status': 'pending', 'approval': None,
            }
            self._save(state)
            return proposal

    @staticmethod
    def _entry(state, proposal):
        require(isinstance(proposal, dict) and isinstance(proposal.get('proposal_id'), str),
                'invalid_proposal')
        entry = state['proposals'].get(proposal['proposal_id'])
        require(entry is not None, 'unknown_proposal')
        require(same(proposal, entry['proposal']), 'proposal_altered')
        return entry

    @staticmethod
    def _fresh(state, proposal):
        require(state['store_id'] == proposal['store_id'] and
                state['revision'] == proposal['source_revision'] and
                digest(state['contacts']) == proposal['source_contacts_sha256'], 'stale_proposal')

    def decide(self, proposal, approved):
        require(type(approved) is bool, 'explicit_boolean_decision_required')
        with self._locked():
            state = self._load()
            entry = self._entry(state, proposal)
            require(entry['status'] == 'pending', 'proposal_already_decided')
            self._fresh(state, proposal)
            if not approved:
                entry['status'] = 'denied'
                self._save(state)
                return {'status': 'denied', 'proposal_id': proposal['proposal_id']}
            approval = {'approval_id': uuid.uuid4().hex, 'proposal_id': proposal['proposal_id'],
                        'store_id': proposal['store_id'], 'source_revision': proposal['source_revision'],
                        'proposal_sha256': digest(proposal)}
            entry['status'], entry['approval'] = 'approved', deepcopy(approval)
            self._save(state)
            return approval

    def apply(self, proposal, approval):
        with self._locked():
            state = self._load()
            entry = self._entry(state, proposal)
            require(entry['status'] != 'applied', 'proposal_replayed')
            require(entry['status'] != 'denied', 'proposal_denied')
            require(entry['status'] == 'approved', 'proposal_unapproved')
            require(isinstance(approval, dict) and same(approval, entry['approval']), 'approval_mismatch')
            self._fresh(state, proposal)
            state['contacts'] = deepcopy(proposal['after'])
            # No-op applications also advance revision and consume approval once.
            state['revision'] += 1
            entry['status'] = 'applied'
            entry['applied_revision'] = state['revision']
            self._save(state)
            readback = self._load()
            require(same(readback, state), 'readback_mismatch')
            return {'status': 'applied_noop' if proposal['no_op'] else 'applied',
                    'store': self._public(readback), 'readback_verified': True,
                    'synthetic_store_written': True, 'real_crm_written': False,
                    'messages_sent': 0, 'inference_executed': False,
                    'central_workflow_status': 'blocked_natural_language_unavailable'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', required=True, help='Local store name, not a filesystem path')
    parser.add_argument('operation', choices=['init', 'read', 'propose', 'decide', 'apply'])
    args = parser.parse_args()
    try:
        store = SyntheticStore(args.store)
        payload = None if args.operation == 'read' else json.load(sys.stdin)
        if args.operation == 'read':
            result = store.read()
        elif args.operation == 'init':
            require(isinstance(payload, dict) and set(payload) == {'contacts'}, 'invalid_init')
            result = store.initialize(payload['contacts'])
        elif args.operation == 'propose':
            result = store.propose(payload)
        else:
            require(isinstance(payload, dict), 'invalid_request')
            if args.operation == 'decide':
                require(set(payload) == {'proposal', 'approved'}, 'invalid_decision')
                result = store.decide(payload['proposal'], payload['approved'])
            else:
                require(set(payload) == {'proposal', 'approval'}, 'invalid_application')
                result = store.apply(payload['proposal'], payload['approval'])
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        uncertain = isinstance(exc, OSError) or str(exc) == 'readback_mismatch'
        print(json.dumps({'status': 'storage_error_reconcile' if uncertain else 'rejected',
                          'error': str(exc), 'inference_executed': False,
                          'synthetic_commit_status': 'read_store_to_determine' if uncertain else 'not_applied',
                          'real_crm_written': False, 'messages_sent': 0}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
