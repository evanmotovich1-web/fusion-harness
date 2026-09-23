def merge(intervals):
    pairs = [tuple(pair) for pair in intervals]
    for start, end in pairs:
        if start > end:
            raise ValueError(f"start > end: {(start, end)}")
    out = []
    for start, end in sorted(pairs):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def free_slots(busy, day_start, day_end):
    if day_start > day_end:
        raise ValueError("day_start > day_end")
    gaps, cursor = [], day_start
    for start, end in merge(busy):
        start, end = max(start, day_start), min(end, day_end)
        if end < day_start or start > day_end:
            continue
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < day_end:
        gaps.append((cursor, day_end))
    return gaps
