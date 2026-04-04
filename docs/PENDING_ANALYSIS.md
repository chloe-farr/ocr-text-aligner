# Analysis of PENDING Words Issues

## Key Findings from Debug Output

### Issue 1: Token Object Mismatch (Duplicate Words)
**Problem**: Words match by string, but they're different token instances in the clean text.

**Examples**:
- `Hyp[260] 'the'` expects `'but'` → finds `'but'` in `Hyp[259]` but it's a different instance
- `Hyp[281] 'this'` expects `'but'` → linked to `'but'` in `Hyp[280]` but wrong instance

**Root Cause**: The clean text has multiple instances of the same word (e.g., "but" appears twice). The ALTO words matched to different instances, so when linking, the token objects don't match even though the words do.

**Impact**: These are correctly identified as PENDING because linking different instances would break the sequence.

---

### Issue 2: Paragraph/Column Boundary Breaks
**Problem**: ALTO spatial neighbors don't match the logical sequence in clean text due to paragraph/column boundaries.

**Examples**:
- `Hyp[358] 'injuries.'` expects `'A'` → but spatial ALTO neighbor is `'will."'` (Hyp[377])
- `Hyp[359] 'Another'` expects `'far."'` → but spatial ALTO neighbor is `'injuries.'` (Hyp[358])
- `Hyp[378] 'A'` expects `'injuries.'` → but spatial ALTO neighbor is `'will."'` (Hyp[377])

**Root Cause**: 
- The clean text sequence is: `"...injuries. A..."` and later `"...will." @..."`
- But in ALTO, these are in different paragraphs/sections
- ALTO's `before_word`/`after_word` only points to immediate spatial neighbors (same paragraph/line)
- So `'injuries.'` can't see `'A'` as its spatial neighbor - they're in different paragraphs

**Current Behavior**: The linking function (`link_hypothesis_objects_by_context`) only checks immediate spatial neighbors via `anchor.before_word`/`after_word`. It can't link across paragraph boundaries.

**Why This Happens**: 
1. Fuzzy/context matching assigned LLM tokens based on word similarity and context
2. But context matching used ALTO spatial neighbors, which may not reflect the clean text sequence
3. When words are matched, they expect LLM neighbors, but those neighbors aren't immediate ALTO spatial neighbors

---

### Issue 3: Missing Spatial Neighbors
**Problem**: Some words have no `before_word`/`after_word` defined in ALTO (paragraph starts/ends).

**Examples**:
- `Hyp[167] 'from''` expects `'the'` but has no spatial right neighbor shown
- `Hyp[377] 'will."'` expects `'@'` but has no spatial right neighbor shown
- `Hyp[388] 'far."'` expects `'Another'` but has no spatial right neighbor shown

**Root Cause**: These are likely at paragraph/column boundaries where ALTO doesn't define `after_word`, or the neighbor was merged/split and the reference is broken.

---

## Solutions Needed

### Solution 1: Handle Token Object Mismatches
**Current**: Linking correctly rejects different token instances even if words match.
**Needed**: These should remain PENDING until we can resolve which instance is correct (via longer-distance context or manual review).

### Solution 2: Search Beyond Immediate Spatial Neighbors
**Current**: Only checks immediate ALTO spatial neighbors (`before_word`/`after_word`).
**Needed**: When immediate neighbor doesn't match, search nearby hypotheses (within same paragraph/block) for the expected LLM token.

**Implementation**:
- When immediate spatial neighbor doesn't match expected token
- Search within reading order distance (same paragraph/block)
- Link if found and token matches
- Still respect paragraph boundaries (don't link across paragraphs)

### Solution 3: Fix Broken Spatial References
**Current**: Some words have missing `before_word`/`after_word` references.
**Needed**: Reconstruct these references based on reading order and position.

---

## Immediate Next Steps

1. **Enhance linking to search nearby hypotheses** (not just immediate spatial neighbors)
2. **Add paragraph/block boundary detection** to prevent cross-paragraph linking
3. **Add a "long-distance linking" pass** that searches within the same block/paragraph for expected neighbors

The core insight: **ALTO spatial structure ≠ Clean text logical sequence**. We need to bridge this gap.
