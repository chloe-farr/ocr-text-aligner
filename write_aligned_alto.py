"""
Write a new ALTO XML file from the alignment result (hypothesis_list + page).
Preserves layout; updates CONTENT to cleaned text; handles splits (1→3) and
merges (same-line: N→1 with merged bounds; cross-line: N Strings, first has word, rest "").
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple, Any

import text_utils

# ALTO 4 namespace (default in document)
ALTO_NS = "http://www.loc.gov/standards/alto/ns-v4#"


def _ns(tag: str) -> str:
    return f"{{{ALTO_NS}}}{tag}" if ALTO_NS else tag


def derive_block_line_id(word_id: str) -> Tuple[str, str]:
    """Derive block_id and line_id from String ID, e.g. WORD_036_001_001 -> (BLOCK_036, LINE_036_001)."""
    parts = word_id.split("_")
    if len(parts) >= 4:
        block_num = parts[1]
        line_num = parts[2]
        return (f"BLOCK_{block_num}", f"LINE_{block_num}_{line_num}")
    return ("", "")


def _merged_bounds_top_left(words: List[Any]) -> Tuple[int, int, int, int]:
    """Compute merged bounding box assuming HPOS/VPOS are top-left (ALTO spec)."""
    hpos = min(w.hpos for w in words)
    vpos = min(w.vpos for w in words)
    right = max(w.hpos + w.width for w in words)
    bottom = max(w.vpos + w.height for w in words)
    width = right - hpos
    height = bottom - vpos
    return (hpos, vpos, width, height)


def _build_id_to_hyps(
    hypothesis_list: List[Any],
) -> Dict[str, List[Any]]:
    """Map each original String id -> list of hypotheses (1 for 1:1/merge, 3 for split)."""
    id_to_hyps: Dict[str, List[Any]] = {}
    for hyp in hypothesis_list:
        if hyp.chosen and hyp.chosen.alto_words:
            for w in hyp.chosen.alto_words:
                wid = w.id
                if wid not in id_to_hyps:
                    id_to_hyps[wid] = []
                if hyp not in id_to_hyps[wid]:
                    id_to_hyps[wid].append(hyp)
        else:
            aid = hyp.anchor.id
            if aid not in id_to_hyps:
                id_to_hyps[aid] = []
            id_to_hyps[aid].append(hyp)
    return id_to_hyps


def _is_same_line_merge(hyp: Any) -> bool:
    if not hyp.chosen or len(hyp.chosen.alto_words) < 2:
        return False
    line_ids = {derive_block_line_id(w.id)[1] for w in hyp.chosen.alto_words}
    return len(line_ids) == 1


def _merge_first_id_same_line(hyp: Any, ordered_ids: List[str]) -> Optional[str]:
    """First id in document order among chosen.alto_words (for same-line merge)."""
    if not hyp.chosen or len(hyp.chosen.alto_words) < 2:
        return None
    ids = [w.id for w in hyp.chosen.alto_words]
    for oid in ordered_ids:
        if oid in ids:
            return oid
    return ids[0]


def _merge_first_id_cross_line(hyp: Any, ordered_ids: List[str]) -> Optional[str]:
    """First id in document order among chosen.alto_words (for cross-line merge)."""
    if not hyp.chosen or len(hyp.chosen.alto_words) < 2:
        return None
    ids = [w.id for w in hyp.chosen.alto_words]
    for oid in ordered_ids:
        if oid in ids:
            return oid
    return ids[0]


def _build_line_outputs(
    page: Any,
    hypothesis_list: List[Any],
    id_to_hyps: Dict[str, List[Any]],
    ordered_ids: List[str],
) -> Dict[Tuple[str, str, str], List[Tuple[str, int, int, int, int, int]]]:
    """
    Build per-line list of output items: (content, hpos, vpos, width, height, wc).
    Key: (page_id, block_id, line_id). Value: list of items in order (indices assigned at write time).
    """
    same_line_first: set = set()
    cross_line_first: set = set()
    for hyp in hypothesis_list:
        if not hyp.chosen or len(hyp.chosen.alto_words) < 2:
            continue
        first_id = _merge_first_id_same_line(hyp, ordered_ids)
        if first_id is not None and _is_same_line_merge(hyp):
            same_line_first.add(first_id)
        first_id_c = _merge_first_id_cross_line(hyp, ordered_ids)
        if first_id_c is not None and not _is_same_line_merge(hyp):
            cross_line_first.add(first_id_c)

    line_outputs: Dict[Tuple[str, str, str], List[Tuple[str, int, int, int, int, int]]] = {}
    seen_same_line_merge_ids: set = set()

    for block in page.content_elements:
        for line in block.content_elements:
            key = (page.id, block.id, line.id)
            items: List[Tuple[str, int, int, int, int, int]] = []
            for orig in line.content_elements:
                oid = orig.id
                if oid in seen_same_line_merge_ids:
                    continue
                hyps = id_to_hyps.get(oid, [])
                if len(hyps) == 3:
                    for h in hyps:
                        a = h.anchor
                        content = h.chosen_LLM_token.word if h.chosen_LLM_token else text_utils.decode_html_entities(orig.content)
                        items.append((content, a.hpos, a.vpos, a.width, a.height, a.wc))
                elif len(hyps) == 1:
                    hyp = hyps[0]
                    if hyp.chosen and len(hyp.chosen.alto_words) > 1:
                        if _is_same_line_merge(hyp) and oid in same_line_first:
                            words = hyp.chosen.alto_words
                            hpos, vpos, width, height = _merged_bounds_top_left(words)
                            content = hyp.chosen_LLM_token.word if hyp.chosen_LLM_token else text_utils.decode_html_entities(orig.content)
                            items.append((content, hpos, vpos, width, height, words[0].wc))
                            for w in words[1:]:
                                seen_same_line_merge_ids.add(w.id)
                        elif not _is_same_line_merge(hyp):
                            # Cross-line merge: first element gets merged word, rest get empty string (strip hyphenation fragment).
                            content = hyp.chosen_LLM_token.word if (hyp.chosen_LLM_token and oid in cross_line_first) else ""
                            items.append((content, orig.hpos, orig.vpos, orig.width, orig.height, orig.wc))
                        else:
                            continue
                    else:
                        content = hyp.chosen_LLM_token.word if hyp.chosen_LLM_token else text_utils.decode_html_entities(orig.content)
                        items.append((content, orig.hpos, orig.vpos, orig.width, orig.height, orig.wc))
                else:
                    content = text_utils.decode_html_entities(orig.content)
                    items.append((content, orig.hpos, orig.vpos, orig.width, orig.height, orig.wc))
            line_outputs[key] = items
    return line_outputs


def _make_string_el(
    word_id: str,
    content: str,
    hpos: int,
    vpos: int,
    width: int,
    height: int,
    wc: int,
    ns_tag: str,
) -> ET.Element:
    el = ET.Element(ns_tag)
    el.set("ID", word_id)
    el.set("HPOS", str(hpos))
    el.set("VPOS", str(vpos))
    el.set("WIDTH", str(width))
    el.set("HEIGHT", str(height))
    el.set("CONTENT", content)
    el.set("WC", str(wc))
    return el


def _word_id_from_parts(block_id: str, line_id: str, seq: int) -> str:
    """e.g. BLOCK_036, LINE_036_001, 1 -> WORD_036_001_001."""
    parts = line_id.replace("LINE_", "").split("_")
    block_num = parts[0] if parts else ""
    line_num = parts[1] if len(parts) > 1 else ""
    seq_str = f"{seq:03d}"
    return f"WORD_{block_num}_{line_num}_{seq_str}"


def write_aligned_alto(
    xml_path: str,
    page: Any,
    hypothesis_list: List[Any],
    output_path: str,
) -> None:
    """
    Write a new ALTO XML file with CONTENT updated from alignment.
    Handles splits (1→3, renumber following in line), same-line merge (N→1, merged bounds),
    cross-line merge (N Strings, first has word, rest "").
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    ns_tag = _ns("String")
    if hasattr(root, "nsmap") or None:
        for el in root.iter():
            if "String" in el.tag:
                ns_tag = el.tag
                break

    ordered_ids = [s.id for s in page.all_strings()]
    id_to_hyps = _build_id_to_hyps(hypothesis_list)
    line_outputs = _build_line_outputs(page, hypothesis_list, id_to_hyps, ordered_ids)

    NS = {"alto": ALTO_NS}
    page_el = root.find(f".//{{{ALTO_NS}}}Page")
    if page_el is None:
        page_el = root.find(".//alto:Page", namespaces=NS)
    if page_el is None:
        raise ValueError("No Page element found in ALTO file.")
    page_id = page_el.get("ID", "")

    for block_el in page_el.findall(f".//{{{ALTO_NS}}}TextBlock") or page_el.findall(".//*[local-name()='TextBlock']"):
        block_id = block_el.get("ID", "")
        for line_el in list(block_el):
            if "TextLine" not in line_el.tag:
                continue
            line_id = line_el.get("ID", "")
            key = (page_id, block_id, line_id)
            items = line_outputs.get(key, [])
            new_children = []
            for seq, (content, hpos, vpos, width, height, wc) in enumerate(items, start=1):
                word_id = _word_id_from_parts(block_id, line_id, seq)
                new_children.append(_make_string_el(word_id, content, hpos, vpos, width, height, wc, ns_tag))
            for c in list(line_el):
                line_el.remove(c)
            for el in new_children:
                line_el.append(el)

    # Pretty-print: each element on its own line with 2-space indentation (Python 3.9+).
    ET.indent(tree, space="  ", level=0)
    # Write without default_namespace to avoid "non-qualified names" error;
    # the tree already has qualified tags from the parsed ALTO.
    tree.write(
        output_path,
        encoding="utf-8",
        xml_declaration=True,
        method="xml",
    )
    # ElementTree emits ns0: prefix; convert to default namespace to match standard ALTO.
    with open(output_path, "r", encoding="utf-8") as f:
        text = f.read()
    text = text.replace("xmlns:ns0=", "xmlns=").replace("<ns0:", "<").replace("</ns0:", "</")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
