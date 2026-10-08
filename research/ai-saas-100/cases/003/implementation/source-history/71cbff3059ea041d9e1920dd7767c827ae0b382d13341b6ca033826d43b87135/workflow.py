"""Partial local CRM operation layer. No AI parsing, network, or persisted writes."""
from copy import deepcopy
import json
import sys


def preview(request):
    if not isinstance(request, dict) or request.get('action') not in {'dedupe', 'update'}:
        raise ValueError('unsupported_action')
    contacts = request.get('contacts')
    if not isinstance(contacts, list) or len(contacts) > 1000:
        raise ValueError('invalid_contacts')
    ids = set()
    for contact in contacts:
        if not isinstance(contact, dict) or not isinstance(contact.get('id'), str) or not contact['id'].strip() or contact['id'] in ids:
            raise ValueError('invalid_or_duplicate_id')
        ids.add(contact['id'])
        email = contact.get('email')
        if not isinstance(email, str) or email.count('@') != 1 or not all(email.strip().split('@')):
            raise ValueError('invalid_email')
    operations = []
    if request['action'] == 'dedupe':
        groups = {}
        for contact in contacts:
            groups.setdefault(contact['email'].strip().casefold(), []).append(contact['id'])
        operations = [{'operation': 'merge_preview', 'retain_id': group[0], 'duplicate_ids': group[1:]}
                      for group in groups.values() if len(group) > 1]
    else:
        patch = request.get('patch')
        if not isinstance(patch, dict) or not {'id'} < set(patch) or not set(patch) <= {'id', 'status', 'note'}:
            raise ValueError('invalid_patch_fields')
        if patch['id'] not in ids:
            raise ValueError('contact_missing')
        if 'status' in patch and patch['status'] not in {'new', 'qualified', 'disqualified'}:
            raise ValueError('invalid_status')
        if 'note' in patch and (not isinstance(patch['note'], str) or len(patch['note']) > 5000):
            raise ValueError('invalid_note')
        before = next(c for c in contacts if c['id'] == patch['id'])
        after = deepcopy(before)
        after.update(patch)
        operations = [{'operation': 'update_preview', 'before': deepcopy(before), 'after': after}]
    return {'status': 'local_preview', 'operations': operations, 'input_mutated': False,
            'inference_executed': False, 'crm_written': False, 'messages_sent': 0,
            'central_workflow_status': 'blocked',
            'blockers': ['Natural-language model not available', 'No authorized real CRM integration or persistence acceptance']}


def run(request):
    try:
        return preview(request)
    except ValueError as exc:
        return {'status': 'invalid_input', 'error': str(exc), 'inference_executed': False,
                'crm_written': False, 'messages_sent': 0}


if __name__ == '__main__':
    result = run(json.load(sys.stdin))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['status'] == 'local_preview' else 2)
