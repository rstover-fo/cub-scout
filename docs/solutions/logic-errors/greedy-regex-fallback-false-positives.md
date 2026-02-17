---
title: Greedy regex fallback misidentifies OCR tokens
category: logic-errors
tags: [regex, ocr, parsing, false-positive, data-quality]
module: film_parser
symptoms:
  - Play numbers in JSON output don't match actual play numbers on screen
  - Down/distance or yard-line numbers appear as play_number field
  - OCR extraction looks correct in raw_ocr_text but parsed fields are wrong
severity: critical
date_resolved: 2026-02-16
---

# Greedy Regex Fallback Misidentifies OCR Tokens

## Problem

A "catch-all" regex fallback for play number extraction matched ANY bare 1-3 digit
number in OCR text, causing down numbers, distances, yard lines, and clock minutes
to be misidentified as play numbers.

## Symptoms

- `play_number: 7` when actual play is #42 (7 was the distance: "3rd & 7")
- `play_number: 40` when actual play is #15 (40 was the yard line: "OPP 40")
- Only occurs when OCR text lacks a labeled `PLAY #N` pattern

## Root Cause

```python
# Labeled pattern (good) — matches "PLAY #15" or "PLAY 15"
_PLAY_NUMBER_LABELED = re.compile(r"(?:PLAY|#)\s*(\d+)", re.IGNORECASE)

# Standalone fallback (bad) — matches ANY bare number
_PLAY_NUMBER_STANDALONE = re.compile(r"^(\d{1,3})$")

def _parse_play_number(text: str) -> int | None:
    m = _PLAY_NUMBER_LABELED.search(text)
    if m:
        return int(m.group(1))
    # Fallback: scan tokens for bare numbers
    for token in text.split():
        m = _PLAY_NUMBER_STANDALONE.match(token.strip())
        if m:
            return int(m.group(1))  # <-- grabs first number it finds
    return None
```

Given OCR text `"Q2 3RD & 7 12:30 OPP 40"`, the fallback finds `7` first (the
distance) and returns it as the play number.

## Solution

Remove the standalone fallback entirely. If there's no labeled pattern, return
`None`. Missing data is better than wrong data.

```python
def _parse_play_number(text: str) -> int | None:
    m = _PLAY_NUMBER_LABELED.search(text)
    if m:
        return int(m.group(1))
    return None  # No fallback — missing > wrong
```

## Prevention

- **Never add "catch-all" regex fallbacks** for structured data extraction
- Each regex pattern should match ONE specific format, not "anything that looks numeric"
- If you must have fallbacks, run them AFTER removing tokens consumed by other parsers
  (quarter, down/distance, clock, yard-line) so they only match genuinely unclassified tokens
- Test regex parsers against realistic OCR output containing multiple numeric fields
- Apply the principle: **missing data > wrong data** for downstream consumers

## General Rule

When parsing structured text with multiple numeric fields, extraction order matters.
Each parser should either:
1. Match a labeled pattern (e.g., `PLAY #15`), or
2. Run after all other parsers have claimed their tokens

A greedy fallback that runs early will steal tokens from later, more specific parsers.

## Related

- Catapult situation frame OCR layout
- PaddleOCR text detection ordering
