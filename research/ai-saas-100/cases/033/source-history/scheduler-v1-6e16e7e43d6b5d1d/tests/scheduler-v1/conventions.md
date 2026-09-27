# Case 033 scheduling conventions v1

These conventions are recorded before implementation. The original specification and freeze remain unchanged. The retained evaluator report `/tmp/fusion-harness-plXwRt/collaborate/reports/1.d-glm.md`, section E6, informs the additional exposed tests. These are independent local scheduling choices, not claims about Reclaim's production algorithm.

C1. Scope: one supplied UTC calendar day, with integer-minute `HH:MM` intervals. `24:00` is allowed only for interval ends and deadlines. Other timezones are explicitly unsupported in this version. All work is local calculation. Requests to write calendars or perform external actions are rejected. No input or output paths are accepted or opened.

C2. Priority: higher integer priority wins. Ties use earlier deadline, then task ID. The selected complete-task set is lexicographically maximal in that order when search completes. Each admission attempt may reschedule all previously admitted tasks. Priority determines admission, not chronological placement. This clarifies an ordering absent from the frozen research fixture, rather than changing any recorded expected answer.

C3. Time: intervals are half-open. Work may finish exactly at its deadline or working-day end. Meetings are immutable and can overlap each other. Their occupied union is unavailable. Meetings outside working hours affect work only through their overlap or buffers.

C4. Buffers: require at least buffer_minutes between a task interval and any meeting, and between separate task intervals, including split fragments. Contiguous fragments of the same task are merged. No buffer is required outside working-day boundaries. Existing meetings are never moved to establish a buffer between meetings. Expanding meeting intervals and clipping to working hours enforces task-to-meeting separation.

C5. Splitting: an unsplittable task is assigned exactly one interval. A splittable task may use multiple positive whole-minute intervals. A task is admitted in full or listed once as unscheduled with all its required minutes. Partial task completion is deliberately not supported. Every valid request accounts for every input task minute exactly once as scheduled or unscheduled.

C6. Feasibility: search over chronological task intervals, integer start minutes, and split lengths. Reconsider order and placement rather than treating one greedy failure as a proof. Necessary capacity/deadline/contiguity bounds may prune impossible states. Exhaustion means infeasible with already admitted higher-priority tasks, not necessarily infeasible in isolation. Results identify that context.

C7. Limits: at most 12 tasks, 128 meetings, a 1440-minute day, and 200000 configurable search steps (default 50000) per request. Search depth is capped at 64 intervals. A reached budget/depth limit is reported as `search_limit`, never as proven infeasibility. Retain the last valid admitted schedule and leave the unresolved task plus all lower-priority tasks unscheduled. Do not claim global optimality or complete search in that result.

C8. Validation: reject booleans as durations/priorities/buffers, invalid or duplicate IDs within a collection, missing or malformed fields, nonpositive durations, invalid dates/times, non-boolean splitting flags, non-immutable meetings, unsupported fields, path parameters, and external-write requests. Valid deadlines before work begins produce unscheduled work rather than fabricated success. Source notes and additional evidence are inert metadata and cannot change scheduling. The input object must remain unchanged.

C9. Output: `schedule(request, node_limit=50000)` returns structured `status`, `scheduled`, `unscheduled`, `constraints_checked`, `solver`, and zero calendar writes. Invalid requests return `status=invalid_input`, an error code/field, and empty result lists. Start/end values use HH:MM. `constraints_checked` is diagnostic only: tests recompute all constraints and task accounting independently from actual intervals.

C10. Evidence limits: existing and added fixtures are builder-visible, including the retained evaluator report. This is algorithm evidence, not hidden evaluation, a generic-model comparison, original-product parity, calendar integration, commercial validation, or product acceptance.
