"""Original in-memory marketplace subset. No network, publication, or vendor API."""
from dataclasses import dataclass, asdict
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
import math


def url(value):
    if not isinstance(value, str) or any(ord(c) <= 32 or ord(c) == 127 for c in value):
        raise ValueError('invalid_url')
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.port not in (None, 443):
        raise ValueError('https_url_required')
    decoded = unquote(parsed.path)
    if '\\' in decoded or any(part in ('.', '..') for part in decoded.split('/')):
        raise ValueError('unsafe_path')
    return parsed


def in_scope(candidate, area):
    candidate, area = url(candidate), url(area)
    prefix = unquote(area.path).rstrip('/')
    path = unquote(candidate.path)
    return candidate.hostname.rstrip('.') == area.hostname.rstrip('.') and (not prefix or path == prefix or path.startswith(prefix + '/'))


@dataclass
class Profile:
    id: str
    target: str
    area: str
    dr: int
    review: str = 'pending'


@dataclass
class Assignment:
    id: str
    source: str
    target: str
    created: int
    deadline: int
    status: str = 'pending'
    reason: str = ''
    reported_url: str = ''


class LinkParser(HTMLParser):
    def __init__(self, target):
        super().__init__()
        self.target = target
        self.valid = False
    def handle_starttag(self, tag, attrs):
        # Duplicate critical attributes are ambiguous across HTML consumers.
        if any(sum(key == name for key, _ in attrs) > 1 for name in ('href', 'rel')):
            return
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href') == self.target:
            self.valid = self.valid or 'nofollow' in (attrs.get('rel') or '').lower().split()


class Marketplace:
    def __init__(self, gap=10):
        if type(gap) is not int or not 0 <= gap <= 100:
            raise ValueError('invalid_gap')
        self.gap = gap
        self.profiles = {}
        self.assignments = {}

    def register(self, profile):
        if not isinstance(profile, Profile) or not isinstance(profile.id, str) or not profile.id or profile.id in self.profiles:
            raise ValueError('invalid_or_duplicate_profile')
        target, area = url(profile.target), url(profile.area)
        if target.hostname.rstrip('.') != area.hostname.rstrip('.'):
            raise ValueError('profile_domains_differ')
        if type(profile.dr) is not int or not 0 <= profile.dr <= 100:
            raise ValueError('invalid_dr')
        if not isinstance(profile.review, str) or profile.review not in {'pending', 'approved', 'rejected'}:
            raise ValueError('invalid_review')
        self.profiles[profile.id] = Profile(**asdict(profile))

    def expire(self, now):
        if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
            raise ValueError('invalid_time')
        for assignment in self.assignments.values():
            if assignment.status == 'pending' and now >= assignment.deadline:
                assignment.status = 'expired'

    def check_in(self, profile_id, now):
        if not isinstance(profile_id, str) or profile_id not in self.profiles:
            raise ValueError('invalid_profile_id')
        self.expire(now)
        source = self.profiles[profile_id]
        if source.review != 'approved':
            return {'status': 'profile_' + source.review, 'assignment': None}
        for a in self.assignments.values():
            if a.source == profile_id and a.status == 'pending':
                return {'status': 'assigned', 'assignment': asdict(a)}
        candidates = []
        for target in self.profiles.values():
            if target.id == source.id or target.review != 'approved':
                continue
            if url(target.target).hostname.rstrip('.') == url(source.target).hostname.rstrip('.') or abs(target.dr - source.dr) > self.gap:
                continue
            pair = {source.id, target.id}
            if any({a.source, a.target} == pair and a.status in {'pending', 'reported_local'} for a in self.assignments.values()):
                continue
            candidates.append(target)
        if not candidates:
            return {'status': 'no_assignment', 'assignment': None}
        target = min(candidates, key=lambda p: (abs(p.dr - source.dr), p.id))
        next_id = len(self.assignments) + 1
        while 'local-' + str(next_id) in self.assignments:
            next_id += 1
        a = Assignment('local-' + str(next_id), source.id, target.id, now, now + 7 * 86400)
        self.assignments[a.id] = a
        return {'status': 'assigned', 'assignment': asdict(a)}

    def _assignment(self, assignment_id):
        if not isinstance(assignment_id, str) or assignment_id not in self.assignments:
            raise ValueError('invalid_assignment_id')
        return self.assignments[assignment_id]

    def reject(self, assignment_id, reason):
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('rejection_reason_required')
        a = self._assignment(assignment_id)
        if a.status == 'reported_local':
            raise ValueError('already_reported')
        a.status, a.reason = 'rejected', reason
        return asdict(a)

    def report_local(self, assignment_id, page_url, html, approved=False):
        if approved is not True:
            raise ValueError('owner_approval_required')
        a = self._assignment(assignment_id)
        if not in_scope(page_url, self.profiles[a.source].area):
            raise ValueError('page_outside_scope')
        if not isinstance(html, str) or len(html) > 100000:
            raise ValueError('invalid_html')
        parser = LinkParser(self.profiles[a.target].target)
        parser.feed(html)
        if not parser.valid:
            raise ValueError('matching_nofollow_link_required')
        a.status, a.reported_url = 'reported_local', page_url
        return {'assignment': asdict(a), 'published': False, 'live_verified': False,
                'scope': 'Synthetic local HTML only, not a production completion report'}

    def link_html(self, assignment_id, anchor):
        if not isinstance(anchor, str) or not anchor.strip() or len(anchor) > 1000:
            raise ValueError('invalid_anchor')
        target = self.profiles[self._assignment(assignment_id).target].target
        return '<a href="' + escape(target, quote=True) + '" rel="nofollow">' + escape(anchor) + '</a>'
