# Layout Tags Module — Plan

## Goal

- LLM-cleaned text may include layout annotations (e.g. "Article 1 title", "Article 1 paragraph", "Article 1 author").
- **Strip** those tags from the text used for mapping so alignment is done on plain text.
- **Preserve** the tags and attach them to each word: store on each LLM token and write to each `<String>` in the aligned XML so downstream tools can use them.

**Why "LAYOUT"?** The attribute identifies what Tesseract has segmented as multiple blocks (e.g. each phrase in its own TextBlock) as actually one layout element — e.g. one title. So LAYOUT labels which logical layout unit a word belongs to, allowing viewers or scripts to regroup over-segmented blocks without changing the ALTO hierarchy.

Nesting/restructuring of TextBlocks is out of scope: we only add attributes; we do not merge blocks or change hierarchy.

---

## 1. Extract LLM token logic into its own module

**Rationale:** The logic that builds LLMTokens (tokenization, and now layout parsing + tag assignment) is a clear unit. Putting it in its own module makes it easier to handle untagged LLM output and to see what's happening in isolation.

### New module: `llm_tokens.py`

- **`LLMToken`** dataclass (moved from `map_up_text.py`), with new field:
  - `layout_tag: Optional[str] = None` (e.g. `"article_1_title"`)
- **`create_LLM_element_list(plain_text: str) -> List[LLMToken]`** (moved from `map_up_text.py`): splits on whitespace, builds list with `word`, `word_normalized`, `w_before`, `w_after`. No layout logic here.
- **`prepare_llm_elements(raw_clean_text: str) -> Tuple[str, List[LLMToken]]`** — single entry point used by the pipeline:
  1. Call `layout_tags.parse_layout_tags(raw_clean_text)` → `(plain_text, layout_tags_by_index)`.
  2. Call `create_LLM_element_list(plain_text)` → `llm_elements`.
  3. Assign `llm_elements[i].layout_tag = layout_tags_by_index[i]` when `i < len(layout_tags_by_index)`; otherwise leave `None`.
  4. Return `(plain_text, llm_elements)`.

**When the LLM output has no tags:** `parse_layout_tags` still returns `(plain_text, [])` or a list of `None`s. `prepare_llm_elements` then produces the same token list as today, with every `layout_tag` left `None`. No special branch needed in the mapping pipeline; the writer simply omits the LAYOUT attribute when `layout_tag` is `None`.

### Changes in `map_up_text.py`

- Remove `LLMToken` and `create_LLM_element_list`.
- Add: `from llm_tokens import LLMToken, prepare_llm_elements`.
- Re-export `LLMToken` so existing imports elsewhere stay valid:  
  `from llm_tokens import LLMToken` at top level (or explicit `__all__` / re-export).
- At run time: replace reading clean text and calling `create_LLM_element_list(clean_text)` with:
  - `plain_text, llm_elements = prepare_llm_elements(clean_text)`
  - Use `plain_text` for building `clean_vocab` (and any other use of the raw string).
  - Use `llm_elements` as the list of LLM tokens for the rest of the pipeline.

No other pipeline logic changes; `chosen_LLM_token` (and thus `layout_tag`) already flows through to the writer.

### Other files that import from `map_up_text`

- **hyphen_linking, context_matching, fuzzy_matching, word_merges, paragraph_reordering, weak_fuzzy_matching, proximity_scoring, visualize_matching** today import `LLMToken` (and sometimes `TokenHypotheses`, `TokenCandidate`) from `map_up_text`.
- Keep **re-exports in `map_up_text`**: continue to export `LLMToken` from `map_up_text` (by importing it from `llm_tokens`). Then these files do not need to change imports.
- Optional later: have them import `LLMToken` directly from `llm_tokens` for a clearer dependency.

---

## 2. New module: `layout_tags.py`

**Responsibilities:**

- **Parse tagged clean text.**  
  Input: full cleaned text (with optional tag lines).  
  Output:
  - **Plain text for mapping:** content with tag lines removed, so tokenization sees only words.
  - **Per-token layout:** a list of layout strings in the same order as the token list produced from that plain text (`layout_tags_by_index`).

- **API:**
  - `parse_layout_tags(raw_clean_text: str) -> Tuple[str, List[Optional[str]]]`  
    Returns `(plain_text_for_mapping, layout_tags_by_token_index)`. If a token has no tag, use `None`.

**Tag format (block markers):**

- A line that is only a tag starts a segment; everything after it until the next tag line gets that tag.
- Example:
  ```text
  [ARTICLE 1 TITLE]
  Gaglardi 'Delighted' Bennett Plans To Take House Seat

  [ARTICLE 1 AUTHOR]
  By Michael Maclear HANOI (AP)

  [ARTICLE 1 PARAGRAPH]
  I witnessed the attack which destroyed ...
  ```
- **Tag syntax:** `[ROLE]` or `[ARTICLE N ROLE]` with ROLE e.g. `TITLE`, `PARAGRAPH`, `AUTHOR`, `HEADLINE`. Parser normalizes to a single string per token, e.g. `article_1_title`, `article_1_author`, `article_1_paragraph` (lowercase, one underscore between parts). Lines with no preceding tag get `None`.
- **Tokenization:** use the same rule as `create_LLM_element_list` (e.g. `line.split()`) so token count matches `llm_elements` and indices align 1:1.

---

## 3. Changes in `write_aligned_alto.py`

- **`_build_line_outputs`:**  
  Extend each item from `(content, hpos, vpos, width, height, wc)` to include layout, e.g. `(content, hpos, vpos, width, height, wc, layout_tag)`. When building from `hyp.chosen_LLM_token`, set `layout_tag = hyp.chosen_LLM_token.layout_tag if hyp.chosen_LLM_token else None`.
- **`_make_string_el`:**  
  Add optional parameter `layout_tag: Optional[str] = None`. If present, set it on the String element as a single ALTO extension attribute, e.g. `LAYOUT="article_1_title"`. When `layout_tag` is `None`, do not write the attribute.
- **Call site:** when building `new_children`, pass the 7th value from each item into `_make_string_el`.

---

## 4. ALTO output shape (per String)

Current:

```xml
<String ID="WORD_043_001_001" HPOS="510" VPOS="1751" WIDTH="272" HEIGHT="72" CONTENT="Gaglardi" WC="56" />
```

With layout (example):

```xml
<String ID="WORD_043_001_001" HPOS="510" VPOS="1751" WIDTH="272" HEIGHT="72" CONTENT="Gaglardi" WC="56" LAYOUT="article_1_title" />
```

Words without a layout tag have no `LAYOUT` attribute. Downstream tools can group Strings by `LAYOUT` to recover the intended layout (e.g. one title spanning several Tesseract blocks) without changing TextBlock/TextLine structure.

---

## 5. Optional: LLM prompt guidance

If the LLM that produces cleaned text is in-repo (e.g. `llm_cleaning/prompts.py`), add a short note or optional prompt snippet for block markers (e.g. `[ARTICLE N TITLE]` on its own line). Document the schema in `layout_tags.py` (or this plan) so the format is defined in one place.

---

## 6. Files to add or touch

| Action | File |
|--------|------|
| **Add** | `llm_tokens.py` — `LLMToken`, `create_LLM_element_list`, `prepare_llm_elements` (imports `layout_tags`) |
| **Add** | `layout_tags.py` — `parse_layout_tags()`, tag normalization, schema doc |
| **Edit** | `map_up_text.py` — remove token dataclass/creation; import and re-export `LLMToken`, call `prepare_llm_elements` |
| **Edit** | `write_aligned_alto.py` — extend line_outputs item tuple, `_make_string_el(layout_tag=...)`, write `LAYOUT` on String when set |

No change to `xml_obj.py` or to ALTO block/line hierarchy.

---

## 7. Tokenization alignment

`create_LLM_element_list` uses `plain_text.split()`. The layout parser must tokenize content with the same rule so `len(layout_tags_by_index)` equals `len(llm_elements)` and `layout_tags_by_index[i]` corresponds to `llm_elements[i]`. If you later change tokenization (e.g. for hyphenation), use the same rule in both `layout_tags` and `llm_tokens`.
