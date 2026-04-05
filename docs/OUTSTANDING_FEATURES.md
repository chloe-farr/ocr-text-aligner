# Outstanding features (backlog)

Planned pipeline improvements that are not covered by [PENDING word analysis](PENDING_ANALYSIS.md) (which focuses on linking and layout order).

---

## Unicode-aware normalization for matching (German, i18n)

**Problem.** Fuzzy matching uses [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz), which is language-agnostic. Token comparison is preceded by `text_utils.normalize_for_matching()`, which currently keeps only ASCII `a–z`, digits, and hyphen-like characters. Letters such as **ä, ö, ü, ß** (German), other Latin extensions, and non-Latin scripts are **stripped**, so vocabulary keys and OCR text no longer align.

**Scope.** Change normalization only (and tests); keep existing RapidFuzz call sites unless a new optional scorer is explicitly requested.

**Suggested implementation directions.**

- Keep “letters + numbers + hyphen variants” but define “letter” and “number” with **Unicode categories** (e.g. `unicodedata.category(ch)` with `L*` and `N*`), or an equivalent that does not drop non-ASCII letters.
- Decide policy for **compatibility equivalents** (e.g. OCR outputs `ae` vs clean text `ä`): optional configurable folding (German `ä↔ae`, etc.) vs strict Unicode equality—document the choice.
- Consider **Unicode normalization** (NFC vs NFKC) consistently for both ALTO-decoded strings and clean-text tokens.
- **Edge cases:** Turkish dotted/dotless I if using `.lower()` without locale; combining characters; soft hyphen `U+00AD`.

**Files to touch.** Primary: [`text_utils.py`](../text_utils.py) (`normalize_for_matching`). Secondary: callers are widespread (`map_up_text.py`, `context_matching.py`, `hyphen_linking.py`, `weak_fuzzy_matching.py`, `llm_tokens.py`, etc.)—behavior change should be centralized in `normalize_for_matching` plus tests.

---

### Copy-paste prompt for an LLM / implementer

```text
Implement Unicode-aware token normalization for the ocr-text-aligner repo.

Context: Matching uses RapidFuzz on strings after text_utils.normalize_for_matching(). That function currently uses re.sub(r"[^0-9a-z\-–—]", "", word.lower()), which strips German umlauts (ä ö ü) and ß, breaking alignment.

Requirements:
1. Replace ASCII-only filtering with preservation of all Unicode letters (Unicode general category L*) and numbers (N*), plus the existing hyphen/dash characters already allowed (plain hyphen, en dash, em dash) and any behavior the docstring promises for line-wrap hyphens.
2. Keep the public API and name normalize_for_matching; update the docstring and doctests to reflect Unicode (add examples with ä, ö, ü, ß).
3. Do not switch fuzzy libraries; RapidFuzz stays as-is.
4. Add unit tests (e.g. tests/) covering: German words with umlauts/ß; a word that previously became empty or wrong under ASCII-only rules; hyphen-preservation cases already in the docstring.
5. Optionally (if minimal): add a short note in README or ALGORITHM.md that matching is Unicode-aware after this change.

Out of scope unless asked: locale-specific lowercasing (tr_TR), ae/oe/ue folding for OCR tolerance, or non-Latin script–specific tokenization.
```
