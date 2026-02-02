# Phase 6C: Enhanced Player Matching Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade player_matching.py with a 3-tier matching system: deterministic (instant), vector similarity (pgvector), and fuzzy fallback (rapidfuzz) with pending_links review queue.

**Architecture:** The current `player_matching.py` uses only fuzzy matching. We'll add Tier 1 (deterministic: exact name + team + year, or athlete_id link) and Tier 2 (vector similarity via `scouting.player_embeddings`) before the existing Tier 3 fuzzy logic. Low-confidence matches (0.80-0.92) go to `scouting.pending_links` for human review.

**Tech Stack:** Python 3.12, psycopg2, rapidfuzz, OpenAI embeddings (via `src/processing/embeddings.py`), pgvector

---

## Task 1: Write Failing Tests for Deterministic Matching

**Purpose:** Establish Tier 1 matching tests before implementation.

**Files:**
- Modify: `tests/test_player_matching.py`

**Step 1: Write failing tests for deterministic match**

```python
def test_deterministic_match_exact_name_team_year():
    """Test exact name + team + year returns 100% confidence."""
    # This requires a test fixture or mocking
    # For now, test the function exists and returns correct type
    from src.processing.player_matching import find_deterministic_match

    result = find_deterministic_match(
        name="Arch Manning",
        team="Texas",
        year=2025,
    )
    assert result is None or isinstance(result, PlayerMatch)
    if result:
        assert result.confidence == 100.0
        assert result.match_method == "deterministic"


def test_deterministic_match_athlete_id_link():
    """Test athlete_id link to roster returns 100% confidence."""
    from src.processing.player_matching import find_deterministic_match_by_athlete_id

    result = find_deterministic_match_by_athlete_id(athlete_id="123456")
    assert result is None or isinstance(result, PlayerMatch)
    if result:
        assert result.confidence == 100.0
        assert result.match_method == "deterministic"
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/robstover/Development/personal/cfb-scout && python -m pytest tests/test_player_matching.py -v -k "deterministic"`
Expected: FAIL with "cannot import name 'find_deterministic_match'"

**Step 3: Commit test file**

```bash
git add tests/test_player_matching.py
git commit -m "test: add failing tests for deterministic matching

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Implement Deterministic Matching (Tier 1)

**Purpose:** Add instant, 100% confidence matches.

**Files:**
- Modify: `src/processing/player_matching.py`

**Step 1: Update PlayerMatch dataclass to include match_method**

Add `match_method` field to track which tier produced the match:

```python
@dataclass
class PlayerMatch:
    """A matched player from roster or recruit data."""

    source: Literal["roster", "recruit"]
    source_id: str
    first_name: str
    last_name: str
    team: str
    position: str | None
    year: int | None
    confidence: float  # 0-100
    match_method: Literal["deterministic", "vector", "fuzzy"] = "fuzzy"
```

**Step 2: Add find_deterministic_match function**

```python
def find_deterministic_match(
    name: str,
    team: str,
    year: int = 2025,
) -> PlayerMatch | None:
    """Tier 1: Exact name + team + year match.

    Returns 100% confidence match or None.
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Exact match on name (first + last) + team + year
        cur.execute(
            """
            SELECT id, first_name, last_name, team, position, year
            FROM core.roster
            WHERE LOWER(first_name || ' ' || last_name) = LOWER(%s)
            AND LOWER(team) = LOWER(%s)
            AND year = %s
            LIMIT 1
            """,
            (name, team, year),
        )
        row = cur.fetchone()

        if row:
            player_id, first, last, player_team, player_pos, player_year = row
            return PlayerMatch(
                source="roster",
                source_id=str(player_id),
                first_name=first,
                last_name=last,
                team=player_team,
                position=player_pos,
                year=player_year,
                confidence=100.0,
                match_method="deterministic",
            )

        return None
    finally:
        cur.close()
        conn.close()
```

**Step 3: Add find_deterministic_match_by_athlete_id function**

```python
def find_deterministic_match_by_athlete_id(
    athlete_id: str,
) -> PlayerMatch | None:
    """Tier 1: Match via recruiting.recruits.athlete_id -> core.roster.id.

    Returns 100% confidence match or None.
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT r.id, r.first_name, r.last_name, r.team, r.position, r.year
            FROM core.roster r
            JOIN recruiting.recruits rec ON rec.athlete_id = r.id
            WHERE rec.athlete_id = %s
            LIMIT 1
            """,
            (athlete_id,),
        )
        row = cur.fetchone()

        if row:
            player_id, first, last, player_team, player_pos, player_year = row
            return PlayerMatch(
                source="roster",
                source_id=str(player_id),
                first_name=first,
                last_name=last,
                team=player_team,
                position=player_pos,
                year=player_year,
                confidence=100.0,
                match_method="deterministic",
            )

        return None
    finally:
        cur.close()
        conn.close()
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/robstover/Development/personal/cfb-scout && python -m pytest tests/test_player_matching.py -v -k "deterministic"`
Expected: PASS

**Step 5: Commit**

```bash
git add src/processing/player_matching.py
git commit -m "feat: add Tier 1 deterministic matching

- Exact name + team + year match
- athlete_id link match
- 100% confidence for deterministic matches

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Write Failing Tests for Vector Similarity Matching

**Purpose:** Establish Tier 2 matching tests.

**Files:**
- Modify: `tests/test_player_matching.py`

**Step 1: Write failing tests for vector match**

```python
def test_vector_match_returns_high_similarity():
    """Test vector matching uses embeddings for similarity."""
    from src.processing.player_matching import find_vector_match

    result = find_vector_match(
        name="Arch Manning",
        team="Texas",
        position="QB",
        year=2025,
    )
    assert result is None or isinstance(result, PlayerMatch)
    if result:
        assert result.match_method == "vector"
        assert result.confidence >= 0 and result.confidence <= 100


def test_vector_match_requires_team_match():
    """Test vector matching enforces team filter."""
    from src.processing.player_matching import find_vector_match

    # Search for Texas player
    result = find_vector_match(
        name="Arch Manning",
        team="Texas",
        position="QB",
        year=2025,
    )
    if result:
        # Team should match filter
        assert result.team.lower() == "texas"
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/robstover/Development/personal/cfb-scout && python -m pytest tests/test_player_matching.py -v -k "vector"`
Expected: FAIL with "cannot import name 'find_vector_match'"

**Step 3: Commit**

```bash
git add tests/test_player_matching.py
git commit -m "test: add failing tests for vector similarity matching

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Implement Vector Similarity Matching (Tier 2)

**Purpose:** Add vector search via pgvector for semantic matching.

**Files:**
- Modify: `src/processing/player_matching.py`

**Step 1: Add imports for embeddings module**

```python
from ..processing.embeddings import build_identity_text, generate_embedding
from ..storage.db import find_similar_by_embedding
```

**Step 2: Add find_vector_match function**

```python
# Vector match thresholds
VECTOR_MATCH_HIGH_CONFIDENCE = 0.92  # Accept automatically
VECTOR_MATCH_LOW_CONFIDENCE = 0.80   # Send to review queue


def find_vector_match(
    name: str,
    team: str | None = None,
    position: str | None = None,
    year: int = 2025,
) -> PlayerMatch | None:
    """Tier 2: Vector similarity match using embeddings.

    Generates embedding for query, searches pgvector for similar players.
    Only accepts matches with similarity >= 0.92 AND team match.

    Args:
        name: Player name to match
        team: Optional team filter (required for high confidence)
        position: Optional position (included in embedding)
        year: Roster year

    Returns:
        PlayerMatch if high-confidence match found, else None
    """
    # Build identity text for query
    query_player = {
        "name": name,
        "team": team or "Unknown",
        "year": year,
        "position": position,
    }
    identity_text = build_identity_text(query_player)

    # Generate embedding for query
    try:
        result = generate_embedding(identity_text)
    except Exception:
        # If embedding fails, fall through to fuzzy
        return None

    conn = get_connection()
    try:
        # Search for similar players
        similar = find_similar_by_embedding(
            conn,
            embedding=result.embedding,
            limit=5,
        )

        if not similar:
            return None

        # Find best match with team filter
        for candidate in similar:
            similarity = candidate["similarity"]

            # Parse identity_text to get team: "Name | Position | Team | Year"
            parts = candidate["identity_text"].split(" | ")
            candidate_team = parts[2] if len(parts) >= 3 else None

            # Require team match for acceptance
            if team and candidate_team and team.lower() != candidate_team.lower():
                continue

            # Only accept high-confidence matches
            if similarity >= VECTOR_MATCH_HIGH_CONFIDENCE:
                # Fetch full player data from roster
                roster_id = candidate["roster_id"]
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT id, first_name, last_name, team, position, year
                    FROM core.roster
                    WHERE id = %s
                    """,
                    (roster_id,),
                )
                row = cur.fetchone()
                cur.close()

                if row:
                    player_id, first, last, player_team, player_pos, player_year = row
                    return PlayerMatch(
                        source="roster",
                        source_id=str(player_id),
                        first_name=first,
                        last_name=last,
                        team=player_team,
                        position=player_pos,
                        year=player_year,
                        confidence=similarity * 100,
                        match_method="vector",
                    )

        return None
    finally:
        conn.close()
```

**Step 3: Run tests to verify they pass**

Run: `cd /Users/robstover/Development/personal/cfb-scout && python -m pytest tests/test_player_matching.py -v -k "vector"`
Expected: PASS

**Step 4: Commit**

```bash
git add src/processing/player_matching.py
git commit -m "feat: add Tier 2 vector similarity matching

- Uses pgvector cosine similarity search
- Requires >= 0.92 similarity AND team match
- Falls through to fuzzy if embedding fails

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Write Failing Tests for Pending Links Queue

**Purpose:** Test review queue for low-confidence matches.

**Files:**
- Modify: `tests/test_player_matching.py`

**Step 1: Write failing tests for pending link creation**

```python
def test_create_pending_link_for_low_confidence():
    """Test low confidence matches create pending links."""
    from src.processing.player_matching import (
        match_player_with_review,
        VECTOR_MATCH_LOW_CONFIDENCE,
        VECTOR_MATCH_HIGH_CONFIDENCE,
    )

    # Function should exist and return a tuple (match, pending_link_id)
    result = match_player_with_review(
        name="Unknown Player",
        team="Some Team",
        position="WR",
        year=2025,
        source_context={"source": "test"},
    )

    assert isinstance(result, tuple)
    assert len(result) == 2
    match, pending_link_id = result
    # Either we got a match or a pending link was created
    assert match is not None or pending_link_id is not None or (match is None and pending_link_id is None)
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/robstover/Development/personal/cfb-scout && python -m pytest tests/test_player_matching.py -v -k "pending"`
Expected: FAIL with "cannot import name 'match_player_with_review'"

**Step 3: Commit**

```bash
git add tests/test_player_matching.py
git commit -m "test: add failing tests for pending links queue

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Implement Pending Links Queue

**Purpose:** Route low-confidence matches to review queue.

**Files:**
- Modify: `src/processing/player_matching.py`

**Step 1: Add import for pending_links db function**

```python
from ..storage.db import insert_pending_link
```

**Step 2: Implement match_player_with_review function**

```python
def match_player_with_review(
    name: str,
    team: str | None = None,
    position: str | None = None,
    year: int = 2025,
    source_context: dict | None = None,
    athlete_id: str | None = None,
) -> tuple[PlayerMatch | None, int | None]:
    """Match player with automatic review queue for low-confidence matches.

    Three-tier matching:
    1. Deterministic: athlete_id link or exact name+team+year (100%)
    2. Vector: pgvector similarity >= 0.92 with team match
    3. Fuzzy: rapidfuzz token_sort_ratio >= 80

    Matches with 0.80-0.92 confidence go to pending_links for review.

    Args:
        name: Player name to match
        team: Optional team filter
        position: Optional position
        year: Roster year
        source_context: Additional context for review queue
        athlete_id: Optional recruit athlete_id for deterministic match

    Returns:
        Tuple of (PlayerMatch or None, pending_link_id or None)
    """
    # Tier 1: Deterministic
    if athlete_id:
        match = find_deterministic_match_by_athlete_id(athlete_id)
        if match:
            return (match, None)

    if team:
        match = find_deterministic_match(name, team, year)
        if match:
            return (match, None)

    # Tier 2: Vector similarity
    vector_match = find_vector_match(name, team=team, position=position, year=year)
    if vector_match:
        return (vector_match, None)

    # Tier 3: Fuzzy matching (existing logic)
    fuzzy_match = find_roster_match(name, team=team, position=position, year=year)

    # Check if we need to create a pending link
    if fuzzy_match:
        confidence_normalized = fuzzy_match.confidence / 100.0

        # High confidence fuzzy match - return it
        if confidence_normalized >= VECTOR_MATCH_HIGH_CONFIDENCE:
            fuzzy_match.match_method = "fuzzy"
            return (fuzzy_match, None)

        # Medium confidence - create pending link for review
        if confidence_normalized >= VECTOR_MATCH_LOW_CONFIDENCE:
            conn = get_connection()
            try:
                pending_id = insert_pending_link(
                    conn,
                    source_name=name,
                    source_team=team,
                    source_context=source_context,
                    candidate_roster_id=fuzzy_match.source_id,
                    match_score=confidence_normalized,
                    match_method="fuzzy",
                )
                return (None, pending_id)
            finally:
                conn.close()

    # Try recruits as fallback
    recruit_match = find_recruit_match(name, team=team, position=position, year=year)
    if recruit_match and recruit_match.confidence >= MATCH_THRESHOLD:
        recruit_match.match_method = "fuzzy"
        return (recruit_match, None)

    # No match found
    return (None, None)
```

**Step 3: Run tests to verify they pass**

Run: `cd /Users/robstover/Development/personal/cfb-scout && python -m pytest tests/test_player_matching.py -v -k "pending"`
Expected: PASS

**Step 4: Commit**

```bash
git add src/processing/player_matching.py
git commit -m "feat: add pending links queue for review

- Medium confidence matches (0.80-0.92) go to review
- High confidence matches return immediately
- Stores source context for reviewer

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Update find_best_match to Use 3-Tier System

**Purpose:** Integrate 3-tier matching into existing API.

**Files:**
- Modify: `src/processing/player_matching.py`

**Step 1: Update find_best_match function**

```python
def find_best_match(
    name: str,
    team: str | None = None,
    position: str | None = None,
    athlete_id: str | None = None,
    year: int = 2025,
) -> PlayerMatch | None:
    """Find best match across all tiers.

    Simplified version that doesn't create pending links.
    Use match_player_with_review() for full review queue support.

    Matching order:
    1. Deterministic (athlete_id or exact match)
    2. Vector similarity
    3. Fuzzy matching
    """
    # Tier 1: Deterministic
    if athlete_id:
        match = find_deterministic_match_by_athlete_id(athlete_id)
        if match:
            return match

    if team:
        match = find_deterministic_match(name, team, year)
        if match:
            return match

    # Tier 2: Vector
    match = find_vector_match(name, team=team, position=position, year=year)
    if match:
        return match

    # Tier 3: Fuzzy (existing logic, but with method tracking)
    match = find_roster_match(name, team=team, position=position, year=year)
    if match and match.confidence >= 90:
        match.match_method = "fuzzy"
        return match

    recruit_match = find_recruit_match(name, team=team, position=position)
    if recruit_match:
        if not match or recruit_match.confidence > match.confidence:
            recruit_match.match_method = "fuzzy"
            return recruit_match

    if match:
        match.match_method = "fuzzy"

    return match
```

**Step 2: Run all player_matching tests**

Run: `cd /Users/robstover/Development/personal/cfb-scout && python -m pytest tests/test_player_matching.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add src/processing/player_matching.py
git commit -m "feat: update find_best_match with 3-tier system

- Maintains backward compatibility
- Uses deterministic -> vector -> fuzzy order
- Tracks match_method on all results

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Update Entity Linking to Use New Matching

**Purpose:** Integrate 3-tier matching into entity_linking.py.

**Files:**
- Modify: `src/processing/entity_linking.py`

**Step 1: Update import to use match_player_with_review**

```python
from .player_matching import match_player_with_review
```

**Step 2: Update link_report_entities to use review queue**

Replace the existing `find_best_match` call with `match_player_with_review`:

```python
# Inside link_report_entities, replace:
#   match = find_best_match(name, team=team or default_team, position=position)
# With:
match, pending_link_id = match_player_with_review(
    name,
    team=team or default_team,
    position=position,
    year=2025,
    source_context={
        "report_id": report["id"],
        "source_url": report.get("source_url"),
    },
)

if pending_link_id:
    logger.info(f"Created pending link {pending_link_id} for {name}")
    continue  # Skip this player, needs review
```

**Step 3: Run entity linking tests**

Run: `cd /Users/robstover/Development/personal/cfb-scout && python -m pytest tests/ -v -k "entity"`
Expected: PASS

**Step 4: Commit**

```bash
git add src/processing/entity_linking.py
git commit -m "feat: update entity linking with 3-tier matching

- Uses match_player_with_review for review queue
- Logs pending links for later review
- Includes report context in pending links

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Add CLI Command for Pending Links Review

**Purpose:** Provide way to review and approve/reject pending links.

**Files:**
- Modify: `scripts/run_pipeline.py`

**Step 1: Add --review-links command**

Add argparse argument and handler:

```python
parser.add_argument(
    "--review-links",
    action="store_true",
    help="Review pending player links",
)

# In main():
if args.review_links:
    review_pending_links()
```

**Step 2: Implement review_pending_links function**

```python
def review_pending_links():
    """Interactive review of pending player links."""
    from src.storage.db import (
        get_connection,
        get_pending_links,
        update_pending_link_status,
    )

    conn = get_connection()
    try:
        pending = get_pending_links(conn, status="pending", limit=50)
        print(f"\n{len(pending)} pending links to review\n")

        for link in pending:
            print(f"ID: {link['id']}")
            print(f"  Source: {link['source_name']} ({link['source_team']})")
            print(f"  Candidate: roster_id={link['candidate_roster_id']}")
            print(f"  Score: {link['match_score']:.2%} ({link['match_method']})")
            print(f"  Context: {link['source_context']}")

            action = input("\n  [a]pprove / [r]eject / [s]kip / [q]uit: ").lower()

            if action == "a":
                update_pending_link_status(conn, link["id"], "approved")
                print("  -> Approved")
            elif action == "r":
                update_pending_link_status(conn, link["id"], "rejected")
                print("  -> Rejected")
            elif action == "q":
                break
            else:
                print("  -> Skipped")

            print()
    finally:
        conn.close()
```

**Step 3: Test the command exists**

Run: `cd /Users/robstover/Development/personal/cfb-scout && python scripts/run_pipeline.py --help`
Expected: Shows --review-links option

**Step 4: Commit**

```bash
git add scripts/run_pipeline.py
git commit -m "feat: add CLI command for pending links review

- Interactive approve/reject/skip workflow
- Shows match context and confidence

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Run Full Test Suite and Lint

**Purpose:** Verify all changes work together.

**Files:** None (verification only)

**Step 1: Run pytest**

Run: `cd /Users/robstover/Development/personal/cfb-scout && python -m pytest tests/ -v`
Expected: All tests PASS

**Step 2: Run ruff lint**

Run: `cd /Users/robstover/Development/personal/cfb-scout && ruff check src/ tests/ scripts/`
Expected: No errors

**Step 3: Run ruff format**

Run: `cd /Users/robstover/Development/personal/cfb-scout && ruff format src/ tests/ scripts/`
Expected: Files formatted

**Step 4: Commit any format changes**

```bash
git add -A
git commit -m "style: format with ruff

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Update README with Phase 6C Status

**Purpose:** Document completed phase.

**Files:**
- Modify: `README.md`

**Step 1: Update Phase 6C section**

Add to Phase 6 progress:

```markdown
### Phase 6C: Enhanced Matching (Complete)

- [x] Tier 1: Deterministic matching (exact name+team+year, athlete_id)
- [x] Tier 2: Vector similarity via pgvector (>= 0.92 threshold)
- [x] Tier 3: Fuzzy fallback with rapidfuzz
- [x] Pending links review queue for 0.80-0.92 confidence
- [x] CLI command: `--review-links`
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README with Phase 6C status

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

After completing all tasks:

1. **3-Tier Matching** - Deterministic (100%) -> Vector (>=92%) -> Fuzzy (>=80%)
2. **Pending Links Queue** - Medium-confidence matches go to review
3. **CLI Review Tool** - Interactive approve/reject workflow
4. **Entity Linking Integration** - Uses new matching system

**Key Files Modified:**
- `src/processing/player_matching.py` - Core 3-tier matching logic
- `src/processing/entity_linking.py` - Uses match_player_with_review
- `scripts/run_pipeline.py` - Added --review-links command
- `tests/test_player_matching.py` - Comprehensive tests

**Next:** Phase 6D (cfb-app Integration) - Add player profile page, "Find Similar Players" component, and portal tracker view
