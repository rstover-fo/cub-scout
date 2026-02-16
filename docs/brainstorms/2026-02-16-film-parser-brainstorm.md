# All-22 Film Parser — Brainstorm

**Date:** 2026-02-16
**Status:** Ready for planning
**Author:** Rob Stover

## What We're Building

A standalone Python CLI module (`src/film_parser/`) that parses All-22 college football film (MP4 files) into structured play catalogs. The module detects scene boundaries, classifies segments (situation frame / sideline clip / end zone clip), extracts game metadata via OCR, and groups everything into play triplets with timestamps.

This is the foundational layer for downstream CV pipelines (formation detection, player tracking, tendency analysis) and the CFB Team 360 application.

## Film Source Details

- **Provider:** Catapult (Prozone)
- **Format:** Clean triplets — strictly `[Situation Frame] -> [Sideline Clip] -> [End Zone Clip]`, repeating. No replays, telestrations, or extra segments.
- **Situation frames:** 2-5 seconds, static graphic with game metadata. Consistent layout across all Catapult exports.
- **Filename convention:** `{TEAM} {O|D} VS. {OPPONENT} {O|D}.mp4`
  - Example: `MICHIGAN O VS. OKLAHOMA D.mp4` = Michigan's offensive plays
  - Inverse: `OKLAHOMA O VS. MICHIGAN D.mp4` = Oklahoma's offensive plays
  - First team + side is the featured perspective
- **Pilot set:** 10-50 files, all from Catapult. Single provider = single regex layout profile.
- **Sample file available:** Yes — enables iterative build-and-test development.
- **Hardware:** M4 Max MacBook Pro, 36GB RAM

## Why This Approach

### Standalone module, not integrated into cfb-scout pipeline

The film parser lives at `src/film_parser/` with its own CLI entry point (`cfb-parse`) rather than being integrated into `scripts/run_pipeline.py`. Reasons:

1. **Dependency isolation** — OpenCV, PaddleOCR, PySceneDetect are heavy dependencies that the existing crawl/API stack doesn't need. Keeping them in optional dependency groups avoids bloating the core install.
2. **Different execution model** — Film parsing is CPU-bound local file processing, not async network I/O like the existing pipeline. The patterns diverge enough that forcing them into the same orchestrator adds complexity.
3. **Independent lifecycle** — Film parsing can be developed, tested, and iterated without touching the existing 172-test suite or API surface.

### Local-only output (JSON files, no database)

v1 outputs JSON play catalogs to the filesystem. No Supabase integration. Reasons:

1. **Focus on the hard problem** — Scene detection, classification, and OCR accuracy need calibration before worrying about storage.
2. **Schema isn't settled** — Downstream CV analysis will add fields (formation labels, personnel, play result). Better to iterate on the JSON schema locally before committing to a database migration.
3. **Scale is modest for now** — Pilot set of 10-50 files. A filesystem manifest is sufficient.

### PaddleOCR for situation frame metadata extraction

Using PaddleOCR (local) rather than Claude Vision for reading situation frames. Trade-offs accepted:

- **Pro:** Zero marginal cost, fully offline, fast on M4 Max (36GB RAM)
- **Con:** Requires regex pattern sets per film provider layout
- **Mitigation:** Only one provider (Catapult) in v1. Design regex parsing as swappable "layout profiles" for future providers.

Claude Vision was considered and would handle layout variability better, but local processing keeps this module self-contained and cost-free at scale.

### Typer + Rich for CLI

Using Typer (type-hint-based CLI framework) instead of matching cfb-scout's argparse convention. Since this is a standalone module with its own entry point, modern tooling makes sense. Rich provides progress bars and formatted output for long-running video processing.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Module placement** | `src/film_parser/` (standalone) | Isolates video deps from crawl/API stack |
| **Data storage** | Local JSON files only | No DB in v1; iterate on schema first |
| **OCR engine** | PaddleOCR (local) | Zero cost, offline, fast on Apple Silicon |
| **CLI framework** | Typer + Rich | Modern, type-safe, good UX for video processing |
| **Batch processing** | Deferred to v2 | Pilot set is 10-50 files; single-file processing first |
| **Scene detection** | PySceneDetect ContentDetector | Hard cuts in All-22 film; tune threshold per source |
| **Sideline vs endzone** | Structural (triplet pattern) | Position-based after situation frame; more reliable than visual |
| **Clip extraction** | Optional (`--extract-clips`) | Default is JSON catalog with timestamps only |
| **Video codec** | FFmpeg stream copy (`-c copy`) only | Never re-encode; speed and quality preservation |
| **Film provider** | Catapult (Prozone) only in v1 | Single provider = single layout profile |
| **Filename parsing** | Auto-extract from `{TEAM} {O|D} VS. {OPPONENT} {O|D}.mp4` | CLI flags as override, not primary input |
| **Development approach** | Build-and-test against real sample file | Iterative calibration, not build-then-tune |

## Scope for v1 (Sprint 8)

### In scope
- Scene boundary detection (PySceneDetect)
- Frame classification (situation vs game action via heuristics)
- OCR extraction from situation frames (PaddleOCR + Catapult regex profile)
- Play triplet assembly (state machine)
- JSON play catalog output
- Single-file CLI (`cfb-parse`) with Typer
- Filename parser for Catapult naming convention
- Situation frame image extraction (`--extract-frames`)
- Clip extraction via FFmpeg stream copy (`--extract-clips`)
- Calibration workflow (`--dry-run --verbose`)
- Quality metrics reporting (segments, triplets, OCR field rates, timing)

### Out of scope (future sprints)
- Batch processing / multiprocessing
- Database storage (Supabase or DuckDB)
- API endpoints for film data
- Pre-snap formation detection
- Player tracking / object detection
- Integration with cfb-scout pipeline
- Additional film providers (Hudl, DVSport, XOS)
- Audio-based play boundary detection
- Claude Vision OCR fallback

## Open Questions (Resolved)

| Question | Resolution |
|----------|-----------|
| Film source consistency | Single provider (Catapult). One regex layout profile for v1. |
| Filename conventions | `{TEAM} {O|D} VS. {OPPONENT} {O|D}.mp4` — auto-parseable |
| Missing segments | Clean triplets; no incomplete plays expected from Catapult |
| Sample file availability | Available for iterative development |

## Remaining Open Questions

1. **Season year** — The filename doesn't include season year. Should we require it as a CLI flag, or infer from file modification date?
2. **Audio track** — Do the Catapult MP4s include audio? Whistle detection could be a future play boundary signal.

## Next Steps

Run `/workflows:plan` to break this into a sprint plan with atomic tasks and acceptance criteria.
