"""Independent output checks and a tiny exhaustive occupancy oracle. No solver imports."""
import itertools


def minute(value):
    h, m = value.split(':')
    return int(h) * 60 + int(m)


def verify(request, result):
    assert result['status'] in {'scheduled', 'partial', 'search_limited'}
    tasks = {t['id']: t for t in request['tasks']}
    start, end = map(minute, request['working_hours'])
    buffer = request['buffer_minutes']
    spans = []
    totals = {key: 0 for key in tasks}
    counts = {key: 0 for key in tasks}
    for row in result['scheduled']:
        assert row['task_id'] in tasks, 'invented_task'
        a, b = minute(row['start']), minute(row['end'])
        assert start <= a < b <= end, 'outside_working_hours'
        assert b <= minute(tasks[row['task_id']]['deadline']), 'deadline'
        totals[row['task_id']] += b - a
        counts[row['task_id']] += 1
        spans.append((a, b, row['task_id']))
        for meeting in request['meetings']:
            x, y = minute(meeting['start']), minute(meeting['end'])
            assert b + buffer <= x or y + buffer <= a, 'meeting_overlap_or_buffer'
    spans.sort()
    for left, right in zip(spans, spans[1:]):
        assert left[1] + buffer <= right[0], 'task_overlap_or_buffer'
    unscheduled = {}
    for row in result['unscheduled']:
        id = row['task_id']
        assert id in tasks and id not in unscheduled, 'invalid_unscheduled_id'
        assert isinstance(row['reason'], str) and row['reason'], 'missing_reason'
        assert type(row['minutes']) is int and row['minutes'] == tasks[id]['minutes']
        unscheduled[id] = row
    for id, task in tasks.items():
        if id in unscheduled:
            assert totals[id] == 0, 'partial_completion_not_supported'
        else:
            assert totals[id] == task['minutes'], 'missing_or_duplicated_work'
            if not task['splittable']:
                assert counts[id] == 1, 'unsplittable_fragmented'
    assert sum(totals.values()) + sum(r['minutes'] for r in unscheduled.values()) == sum(t['minutes'] for t in tasks.values())
    assert result['calendar_writes'] == 0
    assert (result['status'] == 'scheduled') == (not unscheduled)
    assert result['solver']['complete'] == (result['status'] != 'search_limited')
    return sorted(id for id, n in totals.items() if n)


def tiny_optimum(request):
    """Enumerate minute subsets, not chronological interval search. Horizon <=8."""
    begin, end = map(minute, request['working_hours'])
    n = end - begin
    assert 0 < n <= 8
    gap = request['buffer_minutes']
    ordered = sorted(request['tasks'], key=lambda t: (-t['priority'], minute(t['deadline']), t['id']))
    possibilities = []
    for task in ordered:
        candidates = []
        for cells in itertools.combinations(range(n), task['minutes']):
            if not cells or begin + cells[-1] + 1 > minute(task['deadline']):
                continue
            runs = []
            a = b = cells[0]
            for cell in cells[1:]:
                if cell == b + 1:
                    b = cell
                else:
                    runs.append((begin + a, begin + b + 1)); a = b = cell
            runs.append((begin + a, begin + b + 1))
            if not task['splittable'] and len(runs) != 1:
                continue
            if any(x[1] + gap > y[0] for x, y in zip(runs, runs[1:])):
                continue
            if any(not (b + gap <= minute(m['start']) or minute(m['end']) + gap <= a)
                   for a, b in runs for m in request['meetings']):
                continue
            candidates.append(runs)
        possibilities.append(candidates)
    best = tuple(0 for _ in ordered)
    def visit(i, occupied, score):
        nonlocal best
        if i == len(ordered):
            best = max(best, tuple(score)); return
        for runs in possibilities[i]:
            if all(b + gap <= x or y + gap <= a for a, b in runs for x, y in occupied):
                visit(i + 1, occupied + runs, score + [1])
        visit(i + 1, occupied, score + [0])
    visit(0, [], [])
    return sorted(task['id'] for task, selected in zip(ordered, best) if selected)
