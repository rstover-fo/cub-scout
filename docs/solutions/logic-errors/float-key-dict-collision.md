---
title: Float dict keys cause silent data loss in segment mapping
category: logic-errors
tags: [python, dict, floating-point, data-loss, code-review]
module: film_parser
symptoms:
  - OCR data silently missing from some plays in JSON output
  - Segment-to-OCR mapping drops entries without error
  - Works on most films but fails on edge cases with rapid scene cuts
severity: critical
date_resolved: 2026-02-16
---

# Float Dict Keys Cause Silent Data Loss in Segment Mapping

## Problem

Using `float` values as dictionary keys to map video segments to their OCR data
caused silent data loss when two segments shared the same `start_time` (possible
with zero-duration scenes or floating-point rounding from PySceneDetect).

## Symptoms

- Some plays in the JSON catalog have `situation_data: null` despite OCR succeeding
- No error or warning logged — data is silently overwritten
- Intermittent: depends on scene boundary detection precision

## Root Cause

```python
# BAD: float keys can collide
segment_index_map: dict[float, int] = {}
for idx, seg in enumerate(classified):
    segment_index_map[seg.start_time] = idx  # second segment at same time overwrites first
```

If two segments have `start_time = 10.033333`, the second overwrites the first in
the dict. The OCR data for the earlier segment is permanently lost with no error.

## Solution

Use `(start_time, end_time)` tuples as keys. Two segments can share a start time
but not both start and end time.

```python
# GOOD: tuple keys are unique per segment
segment_index_map: dict[tuple[float, float], int] = {}
for idx, seg in enumerate(classified):
    segment_index_map[(seg.start_time, seg.end_time)] = idx

# Lookup uses both fields
key = (play.situation.start_time, play.situation.end_time)
if key in segment_index_map:
    seg_idx = segment_index_map[key]
```

## Prevention

- Never use bare `float` as dict keys when uniqueness matters
- Prefer integer indices or composite tuple keys for segment/timestamp lookups
- When mapping between parallel lists (segments, OCR results), use list index directly
- Code review should flag `dict[float, ...]` as a potential collision risk

## General Rule

**If your dict key is a measurement (float), it's probably wrong.** Measurements
have precision limits. Use identifiers (int index, tuple, or string) instead.

## Related

- Python docs on `__hash__` and float equality
- PySceneDetect FrameTimecode precision
