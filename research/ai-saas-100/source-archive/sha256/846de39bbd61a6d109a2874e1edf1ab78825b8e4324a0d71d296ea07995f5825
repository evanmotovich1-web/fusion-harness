"""Local single-day scheduler. No file, network, account, or calendar I/O."""
from datetime import date
import re

DEFAULT_NODE_LIMIT = 50000
MAX_NODE_LIMIT = 200000
MAX_DEPTH = 64


class InvalidInput(ValueError):
    def __init__(self, code, field):
        self.code, self.field = code, field
        super().__init__(code + ': ' + field)


class SearchLimit(Exception):
    pass


def clock(value, field, allow_end=False):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{2}:[0-9]{2}', value):
        raise InvalidInput('invalid_time', field)
    hours, minutes = map(int, value.split(':'))
    if hours == 24 and minutes == 0 and allow_end:
        return 1440
    if not 0 <= hours <= 23 or not 0 <= minutes <= 59:
        raise InvalidInput('invalid_time', field)
    return 60 * hours + minutes


def text_clock(value):
    return f'{value // 60:02}:{value % 60:02}'


def integer(value, field, low, high):
    if type(value) is not int or not low <= value <= high:
        raise InvalidInput('invalid_integer', field)
    return value


def validate(request, node_limit):
    integer(node_limit, 'node_limit', 1, MAX_NODE_LIMIT)
    if not isinstance(request, dict):
        raise InvalidInput('invalid_type', 'request')
    if {'input_path', 'output_path'}.intersection(request):
        raise InvalidInput('path_parameters_forbidden', 'request')
    if 'requested_external_action' in request:
        raise InvalidInput('external_action_forbidden', 'requested_external_action')
    required = {'timezone', 'day', 'working_hours', 'meetings', 'tasks', 'buffer_minutes', 'write_to_calendar'}
    if not required.issubset(request):
        raise InvalidInput('missing_field', 'request')
    if set(request) - required - {'untrusted_source_note', 'additional_sources'}:
        raise InvalidInput('unsupported_field', 'request')
    if request['write_to_calendar'] is not False:
        raise InvalidInput('calendar_writes_forbidden', 'write_to_calendar')
    if request['timezone'] != 'UTC':
        raise InvalidInput('unsupported_timezone', 'timezone')
    try:
        if not isinstance(request['day'], str) or date.fromisoformat(request['day']).isoformat() != request['day']:
            raise ValueError()
    except (ValueError, TypeError):
        raise InvalidInput('invalid_date', 'day')
    hours = request['working_hours']
    if not isinstance(hours, list) or len(hours) != 2:
        raise InvalidInput('invalid_interval', 'working_hours')
    begin = clock(hours[0], 'working_hours.start')
    end = clock(hours[1], 'working_hours.end', True)
    if begin >= end:
        raise InvalidInput('invalid_interval', 'working_hours')
    gap = integer(request['buffer_minutes'], 'buffer_minutes', 0, 1440)
    tasks, meetings = [], []
    for name, maximum, fields in [('tasks', 12, {'id', 'minutes', 'priority', 'deadline', 'splittable'}),
                                   ('meetings', 128, {'id', 'start', 'end', 'movable'})]:
        values = request[name]
        if not isinstance(values, list) or len(values) > maximum:
            raise InvalidInput('invalid_collection', name)
        seen = set()
        for i, item in enumerate(values):
            field = f'{name}[{i}]'
            if not isinstance(item, dict) or set(item) != fields:
                raise InvalidInput('invalid_fields', field)
            id = item['id']
            if not isinstance(id, str) or not id.strip() or len(id) > 128 or id in seen:
                raise InvalidInput('invalid_or_duplicate_id', field + '.id')
            seen.add(id)
            if name == 'tasks':
                duration = integer(item['minutes'], field + '.minutes', 1, 1440)
                priority = integer(item['priority'], field + '.priority', -1000000, 1000000)
                if type(item['splittable']) is not bool:
                    raise InvalidInput('invalid_boolean', field + '.splittable')
                tasks.append(dict(id=id, minutes=duration, priority=priority,
                                  deadline=clock(item['deadline'], field + '.deadline', True),
                                  splittable=item['splittable']))
            else:
                a = clock(item['start'], field + '.start')
                b = clock(item['end'], field + '.end', True)
                if a >= b:
                    raise InvalidInput('invalid_interval', field)
                if item['movable'] is not False:
                    raise InvalidInput('immutable_meeting_required', field + '.movable')
                meetings.append((a, b))
    return begin, end, gap, tasks, meetings


class Budget:
    def __init__(self, limit):
        self.limit, self.steps = limit, 0

    def tick(self):
        if self.steps >= self.limit:
            raise SearchLimit('step_budget')
        self.steps += 1


def place(tasks, begin, end, gap, free, budget):
    """Complete chronological enumeration unless an explicit limit is reached."""
    tasks = sorted(tasks, key=lambda t: (t['deadline'], -t['priority'], t['id']))
    prefix = [0]
    for available in free:
        prefix.append(prefix[-1] + int(available))
    run_end = [end] * (end + 1)
    for minute in range(end - 1, -1, -1):
        run_end[minute] = run_end[minute + 1] if free[minute] else minute
    failed = set()

    def available(a, b):
        a, b = min(end, max(begin, a)), min(end, max(begin, b))
        return prefix[b] - prefix[a] if b > a else 0

    def search(cursor, remaining, depth):
        budget.tick()
        if not any(remaining):
            return []
        if cursor >= end:
            return None
        if depth >= MAX_DEPTH:
            raise SearchLimit('interval_depth')
        key = (cursor, remaining)
        if key in failed:
            return None
        # Optimistic capacity bounds ignore inter-task buffers and cannot discard a feasible plan.
        for deadline in {min(end, tasks[i]['deadline']) for i, n in enumerate(remaining) if n}:
            due = sum(n for i, n in enumerate(remaining) if tasks[i]['deadline'] <= deadline or deadline == end)
            if due > available(cursor, deadline):
                failed.add(key)
                return None
        for i, amount in enumerate(remaining):
            if not amount:
                continue
            task = tasks[i]
            finish = min(end, task['deadline'])
            minimum = 1 if task['splittable'] else amount
            for start in range(cursor, finish - minimum + 1):
                budget.tick()
                maximum = min(amount, run_end[start] - start, finish - start)
                if maximum < minimum:
                    continue
                lengths = range(maximum, 0, -1) if task['splittable'] else (amount,)
                for length in lengths:
                    budget.tick()
                    rest = list(remaining)
                    rest[i] -= length
                    suffix = search(start + length + gap, tuple(rest), depth + 1)
                    if suffix is not None:
                        return [(task['id'], start, start + length)] + suffix
        failed.add(key)
        return None

    return search(begin, tuple(t['minutes'] for t in tasks), 0)


def checked_constraints(rows, unscheduled, tasks, meetings, begin, end, gap):
    """Recheck the returned plan. Tests use a separate implementation of these checks."""
    by_id = {t['id']: t for t in tasks}
    totals = {id: 0 for id in by_id}
    counts = {id: 0 for id in by_id}
    last_end = None
    for id, a, b in rows:
        assert begin <= a < b <= end and b <= by_id[id]['deadline']
        assert last_end is None or a >= last_end + gap
        assert all(b + gap <= x or y + gap <= a for x, y in meetings)
        last_end = b
        totals[id] += b - a
        counts[id] += 1
    omitted = {row['task_id'] for row in unscheduled}
    assert len(omitted) == len(unscheduled)
    for id, task in by_id.items():
        assert totals[id] == (0 if id in omitted else task['minutes'])
        assert task['splittable'] or counts[id] <= 1
    assert sum(totals.values()) + sum(row['minutes'] for row in unscheduled) == sum(t['minutes'] for t in tasks)
    return dict(no_overlap=True, within_working_hours=True, all_tasks_before_deadline=True,
                buffers_respected=True, exact_task_accounting=True, meetings_unchanged=True)


def schedule(request, *, node_limit=DEFAULT_NODE_LIMIT):
    try:
        begin, end, gap, tasks, meetings = validate(request, node_limit)
    except InvalidInput as exc:
        return {'status': 'invalid_input', 'error': {'code': exc.code, 'field': exc.field},
                'scheduled': [], 'unscheduled': [], 'constraints_checked': {}, 'calendar_writes': 0}
    free = [begin <= minute < end for minute in range(end)]
    for a, b in meetings:
        for minute in range(max(begin, a - gap), min(end, b + gap)):
            free[minute] = False
    ordered = sorted(tasks, key=lambda t: (-t['priority'], t['deadline'], t['id']))
    accepted, plan, unscheduled = [], [], []
    budget = Budget(node_limit)
    limit_reason = None
    for task in ordered:
        if limit_reason is not None:
            unscheduled.append(dict(task_id=task['id'], minutes=task['minutes'], reason='search_limit_priority_predecessor_unresolved', proof='not_established'))
            continue
        try:
            proposal = place(accepted + [task], begin, end, gap, free, budget)
        except SearchLimit as exc:
            limit_reason = str(exc)
            unscheduled.append(dict(task_id=task['id'], minutes=task['minutes'], reason='search_limit', proof='not_established'))
            continue
        if proposal is None:
            unscheduled.append(dict(task_id=task['id'], minutes=task['minutes'], reason='infeasible_with_higher_priority_tasks' if accepted else 'infeasible_with_calendar_and_deadline',
                                    proof='exhaustive_search_or_necessary_capacity_bound', retained_task_ids=[t['id'] for t in accepted]))
        else:
            accepted.append(task)
            plan = proposal
    # Adjacent fragments of the same split task represent one continuous interval.
    merged = []
    for id, a, b in plan:
        if merged and merged[-1][0] == id and merged[-1][2] == a:
            merged[-1] = (id, merged[-1][1], b)
        else:
            merged.append((id, a, b))
    checked = checked_constraints(merged, unscheduled, tasks, meetings, begin, end, gap)
    return {'status': 'search_limited' if limit_reason else ('partial' if unscheduled else 'scheduled'),
            'scheduled': [dict(task_id=id, start=text_clock(a), end=text_clock(b)) for id, a, b in merged],
            'unscheduled': unscheduled, 'constraints_checked': checked, 'calendar_writes': 0,
            'solver': {'complete': limit_reason is None, 'search_steps': budget.steps, 'step_limit': node_limit,
                       'depth_limit': MAX_DEPTH, 'limit_reason': limit_reason,
                       'objective': 'lexicographic_complete_task_admission_by_priority_deadline_id',
                       'admission_order': [t['id'] for t in ordered]}}
