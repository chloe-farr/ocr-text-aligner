---
name: Aligned ALTO XML output
overview: "Add a pipeline step that writes a new ALTO XML file from the alignment result: same layout and structure as the input ALTO, with CONTENT updated to the LLM-cleaned text where matched, handling splits (1 original String → 3) and merges (2+ Strings → one cleaned word)."
todos: []
isProject: false
---

# Add step: create new ALTO XML from alignment

## Current state

- The pipeline in [map_up_text.py](map_up_text.py) aligns ALTO XML words to LLM-cleaned tokens and produces **only** PDFs, PNGs, and terminal output. There is no code that writes XML.
- Alignment is stored in `hypothesis_list`: each entry has an `anchor` ([xml_obj.StringWord](xml_obj.py)), optional `chosen_LLM_token` (cleaned word), and for merges `chosen.alto_words` (multiple ALTO words → one token).
- [xml_obj.py](xml_obj.py) already has `to_xml()` on `StringWord`, `TextLine`, `TextBlock`, and `Page`, but they create elements **without** the ALTO namespace; the full document (root `<alto>`, `Description`, `Layout`) is never written.
- **Splits** (e.g. "assignment-his" → "assignment", "-", "his"): [hyphen_linking.split_hyphenated_triplets](hyphen_linking.py) creates three synthetic StringWord anchors, all reusing the same `id`. In the **new XML only**: emit 3 String elements; first keeps original ID (e.g. WORD_126_001_001), second and third get next indices (002, 003); all **subsequent** words in that line have their word index **incremented by 2**. Splits stay in the same line/block.
- **Merges** come in two cases:
  - **Cross-line merge** (e.g. hyphenated across lines): Keep both String elements; same IDs. First gets the merged word, second (and any others) get empty string. No ID renumbering.
  - **Same-line merge** (e.g. "dams" + "aged" → "damaged" on one line): Collapse to **one** String element—bounds merge, one word. All **following** words in that line have their word index **decremented by 1** (inverse of splits).

## Goal

Produce a **new ALTO XML file** that:

- Preserves the input ALTO structure (Description, Layout, Page, TextBlock, TextLine) and coordinates.
- Replaces each String’s CONTENT with the aligned cleaned text when available; otherwise keeps original CONTENT.
- Handles **splits**: one String → three Strings; first keeps original ID, next two get sequential indices; subsequent words in that line get indices +2. Geometry from split anchors.
- Handles **merges**: **Cross-line**: keep all String elements, first gets merged word, rest get ""; IDs unchanged. **Same-line**: collapse to one String (merged bounds + word); subsequent words in that line get indices −1.

## Implementation approach

### 0. Add page_id to StringWord; derive block_id and line_id from String ID

- In typical ALTO, the String ID encodes hierarchy, e.g. `WORD_036_001_001` → block 036, line 001, word 001. So **block_id** and **line_id** can be derived from `anchor.id` (e.g. parse segments and format as `BLOCK_036`, `LINE_036_001`). No need to store them on `StringWord`.
- **Add only `page_id`** to [xml_obj.py](xml_obj.py) on `StringWord`: e.g. `page_id: Optional[str] = None`. The page ID is not part of the String ID, so it must be set when we have Page context.
- **Set page_id after load**: After building the page, run a single walk that sets `s.page_id = page.id` on every StringWord (e.g. `Page.set_string_page_ids()`). Call this in `map_up_text` right after `load_first_page`.
- **Synthetic anchors (splits)**: In [hyphen_linking.py](hyphen_linking.py), when creating `word1_anchor`, `hyphen_anchor`, `word2_anchor`, copy **only `page_id`** from `hyp.anchor`. Block and line are derived from the (unchanged) `anchor.id` when needed.
- **Writer**: When grouping the hypothesis list for output, derive `block_id` and `line_id` from each `anchor.id` via a small helper (e.g. `WORD_036_001_001` → `("BLOCK_036", "LINE_036_001")`). Group by `(page_id, block_id, line_id)` and sort by `hpos` within each line.

### 1. Build a mapping from original ALTO structure to aligned content

- Walk the **original** page (from `page.all_strings()` in document order: Block → Line → String). For each original `StringWord` we need:
  - **Normal (1:1)**: one hypothesis whose `anchor` is that word (or whose `chosen.alto_words` contains it). Use `chosen_LLM_token.word` if set, else keep original CONTENT.
  - **Split (1→3)**: hypotheses are **synthetic** and not in the page; they share the same `anchor.id` as the original. So group `hypothesis_list` by `anchor.id`; where a given original ID has three hypotheses, that original String is a split. Emit three String elements using each hypothesis’s anchor (hpos, width, height) and `chosen_LLM_token.word` (or original CONTENT).
  - **Merge**: one hypothesis has `chosen.alto_words = [w1, w2, ...]`. **Cross-line** (words from different lines): keep one output String per original; first gets merged word, rest get ""; IDs unchanged. **Same-line**: emit **one** String (merged bounds + word); subsequent words in that line get indices **decremented by 1**.
- Build a mapping keyed by **original String identity** (e.g. `id(alto_word)` from the page) or by stable ID, since after splits we have no original object in the hypothesis list for the two extra parts—we only have `anchor.id`. So the mapping should be: for each **original** String in the page (in document order), determine “replace with one String” or “replace with three Strings” and the CONTENT(s). Same-line vs cross-line merge: compare derived line_id from `anchor.id` for all `chosen.alto_words`; if same line → same-line merge (N→1 String, merged bounds; following indices −1); else cross-line (keep N Strings, first has word, rest "").

### 1b. Merged bounds for same-line merge

When emitting the single String for a same-line merge, compute its HPOS, VPOS, WIDTH, and HEIGHT from the N source StringWords. **If** the ALTO data uses HPOS/VPOS as the **center** of each object (not top-left):

- **Horizontal**: `obj1_leftEdge = obj1_hpos - (obj1_width/2)`, `obj2_rightEdge = obj2_hpos + (obj2_width/2)`, `newObj_width = obj2_rightEdge - obj1_leftEdge`, `newObj_hpos = obj1_leftEdge + (newObj_width/2)`.
- **Vertical**: `obj1_topEdge = obj1_vpos - (obj1_height/2)`, `obj1_bottomEdge = obj1_vpos + (obj1_height/2)`; same for obj2; `minTopEdge = min(obj1_topEdge, obj2_topEdge)`, `maxBottomEdge = max(obj1_bottomEdge, obj2_bottomEdge)`, `newObj_height = maxBottomEdge - minTopEdge`, `newObj_vpos = minTopEdge + (newObj_height/2)`.

For more than two words, extend by taking min of left/top edges and max of right/bottom edges across all objects, then center. **Note**: ALTO spec typically uses HPOS/VPOS as **top-left**; if the input ALTO is top-left–based, use instead: `newObj_hpos = min(hpos_i)`, `newObj_width = max(hpos_i + width_i) - newObj_hpos`, and similarly for VPOS/HEIGHT. The writer should follow one convention consistently (or make it configurable).

### 2. New module: `write_aligned_alto.py` (or similar)

- **Inputs**: path to original ALTO file, `page` (from `load_first_page`), `hypothesis_list` (after the full pipeline).
- **Logic**:
  - Parse the original file again with `ET.parse` to keep the full document (root, namespaces, Description, Layout).
  - Build the mapping above by:
    - Building `original_id_to_hypotheses`: for each hypothesis, record by `anchor.id` (and for merges, by each `id(w)` for `w in chosen.alto_words`).
    - Walking the original Page in document order (Block → Line → String). For each String element (we need to match by String’s XML ID to the page’s StringWord.id):
      - Look up hypotheses by that ID. If 3 hypotheses share this ID → split: replace this one String with 3 String elements (using each hypothesis’s anchor for geometry, and chosen_LLM_token.word for CONTENT). First keeps original ID; second/third get next sequential indices (002, 003); increment all following word indices in that line by 2.
      - **Merge** (same line: one String, merged bounds, following indices −1; cross-line: first gets word, rest ""): (from `chosen.alto_words`), use cleaned word; if it’s a **Same-line merge**: emit one String (merged bounds + word); decrement following word indices in that line by 1. **Cross-line**: first String gets cleaned word, rest get "".
      - Otherwise 1:1: use `chosen_LLM_token.word` if set, else keep current CONTENT.
  - Write the result: keep root and everything before/after the single Page; replace the Page’s subtree with a new tree built from the modified list of String elements. If StringWords have `line_id`/`block_id`/`page_id`, the writer can group the hypothesis list by `(page_id, block_id, line_id)` and sort by `hpos` within each line, then rebuild Block/Line/String structure (or merge into a cloned tree). Alternatively: **clone the original page structure** (Block/Line) and only replace or expand String nodes: when we have a split, replace the single String element with three; when we have a merge, only change CONTENT. That way Block/Line IDs and structure stay intact.

### 3. Namespace handling

- ALTO uses `xmlns="http://www.loc.gov/standards/alto/ns-v4#"`. The existing `to_xml()` in `xml_obj` does **not** set the namespace. Options:
  - **A)** When building the new Page subtree, create elements with the proper namespace (e.g. `ET.Element("{http://...}String")` or register a prefix and use it) so the written file is valid ALTO.
  - **B)** Build the new Page in memory using the existing `Page.to_xml()` and then fix namespaces when assembling the final tree (e.g. re-tag or replace default namespace on the Layout subtree).
- Recommendation: build the output by cloning the original ET tree and only modifying CONTENT and, for splits, replacing one element with three (and fixing IDs). That preserves the original namespace on all elements. New elements (the 2nd and 3rd String in a split) should be created with the same namespace as the original String (from the parsed file).

### 4. Integration point

- In [map_up_text.py](map_up_text.py), after the pipeline and after `visualize_cleaned_text_positions`, call the new writer, e.g.:
  - `write_aligned_alto(xml_filename, page, hypothesis_list, output_path=os.path.join("outputs", testpagename, f"{testpagename}_aligned.xml"))`
- Add a CLI flag (e.g. `--output-xml` or `--write-alto`) to enable writing the aligned ALTO; optionally the path can be derived from the input path (e.g. same dir, suffix `_aligned.xml`).

### 5. Edge cases

- **Unmatched words**: keep original CONTENT (already implied above).
- **Unique IDs**: for split parts, generate IDs that do not conflict (e.g. `WORD_039_001_008` → `WORD_039_001_008_a`, `_b`, `_c` or `_1`, `_2`, `_3`).
- **Single-page only**: current pipeline uses `load_first_page`; the writer should assume one page. Multi-page will be a later extension.

## Summary


| Item               | Action                                                                                                                                                                                                             |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| StringWord page_id | Add `page_id` (optional) to `StringWord`; set via post-load walk on Page; copy to synthetic anchors. Derive block_id and line_id from `anchor.id` (e.g. WORD_036_001_001 → BLOCK_036, LINE_036_001) in the writer. |
| New module         | Add `write_aligned_alto.py` (or integrate into a small `alto_io.py`) that takes original ALTO path, `page`, `hypothesis_list`, and output path.                                                                    |
| Mapping            | Build original-ID → hypotheses (for splits) and original String → “content to write” (for merges: first gets word, rest "").                                                                                       |
| Tree output        | Clone original ALTO document; walk Layout/Page/Block/Line/String; for each String, substitute CONTENT or replace with 3 String elements for splits; ensure namespace and unique IDs.                               |
| Hook               | Call writer at end of `map_up_text.main()`, gated by `--output-xml` or always-on with default path.                                                                                                                |
| Tests              | Optional: unit test with a minimal ALTO + mock hypothesis_list (one 1:1, one split, one merge).                                                                                                                    |


No changes to the alignment logic itself; this is a pure output step after the existing pipeline.