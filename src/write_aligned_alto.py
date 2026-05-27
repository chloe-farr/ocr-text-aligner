"""
Write a new ALTO XML file from the alignment result (hypothesis_list + page).
Preserves layout; updates CONTENT to cleaned text; handles splits (1→3) and
merges (same-line: N→1 with merged bounds; cross-line: N Strings, first has word, rest "").
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple, Any

import alignment_confidence
import text_utils

# ALTO v4 and v3 namespaces (Tesseract outputs v3)
ALTO_NS = "http://www.loc.gov/standards/alto/ns-v4#"
ALTO_NS_V3 = "http://www.loc.gov/standards/alto/ns-v3#"
NS = {"alto": ALTO_NS, "alto3": ALTO_NS_V3}


def _normalize_written_alto(text: str) -> str:
    """Convert ElementTree's ns0:, ns1:, ns2: etc. to default namespace so no unbound prefix."""
    # Make first xmlns:nsN= the default namespace
    text = re.sub(r'\bxmlns:(ns\d+)=', "xmlns=", text, count=1)
    # Remove any other xmlns:nsN= (unbound otherwise)
    text = re.sub(r'\s+xmlns:ns\d+="[^"]*"', "", text)
    # Drop prefix from element tags: </ns2:foo> -> </foo>, then <ns2:foo> -> <foo>
    text = re.sub(r"</ns\d+:", "</", text)
    text = re.sub(r"<ns\d+:", "<", text)
    return text


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
    """True only when all segments are on one line by both ID and geometry.
    When ALTO says one line but segments span two visual lines (different VPOS)
    or any segment ends with hyphen, we treat as cross-line to preserve each box."""
    if not hyp.chosen or len(hyp.chosen.alto_words) < 2:
        return False
    words = hyp.chosen.alto_words
    line_ids = {derive_block_line_id(w.id)[1] for w in words}
    if len(line_ids) > 1:
        return False
    # Hyphenation: if any segment ends with hyphen, often the continuation is on next line; treat as cross-line.
    if any((w.content or "").rstrip().endswith("-") for w in words):
        return False
    # Same line by ID. If VPOS differ, ALTO put both in one TextLine but they span two visual lines -> cross-line.
    vpos_set = {w.vpos for w in words}
    if len(vpos_set) > 1:
        return False
    return True


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
) -> Dict[Tuple[str, str, str], List[Tuple[str, int, int, int, int, int, Optional[str], int, Optional[int]]]]:
    """
    Build per-line list of output items:
    (content, hpos, vpos, width, height, wc, layout_tag, align_conf, clean_para_id).
    align_conf: alignment pipeline confidence 0–100 (see alignment_confidence.py).
    clean_para_id: 0-based paragraph index from clean text blank-line boundaries (llm_tokens.assign_clean_paragraph_ids).
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

    line_outputs: Dict[Tuple[str, str, str], List[Tuple[str, int, int, int, int, int, Optional[str], int, Optional[int]]]] = {}
    seen_same_line_merge_ids: set = set()

    for block in page.content_elements:
        for line in block.content_elements:
            key = (page.id, block.id, line.id)
            items: List[Tuple[str, int, int, int, int, int, Optional[str], int, Optional[int]]] = []
            for orig in line.content_elements:
                oid = orig.id
                if oid in seen_same_line_merge_ids:
                    continue
                hyps = id_to_hyps.get(oid, [])
                layout_tag: Optional[str] = None
                if len(hyps) == 3:
                    for h in hyps:
                        a = h.anchor
                        content = h.chosen_LLM_token.word if h.chosen_LLM_token else text_utils.decode_html_entities(orig.content)
                        layout_tag = h.chosen_LLM_token.layout_tag if h.chosen_LLM_token else None
                        ac = alignment_confidence.alignment_confidence(h)
                        cpid = h.chosen_LLM_token.clean_para_id if h.chosen_LLM_token else None
                        items.append((content, a.hpos, a.vpos, a.width, a.height, a.wc, layout_tag, ac, cpid))
                elif len(hyps) == 1:
                    hyp = hyps[0]
                    layout_tag = hyp.chosen_LLM_token.layout_tag if hyp.chosen_LLM_token else None
                    if hyp.chosen and len(hyp.chosen.alto_words) > 1:
                        if _is_same_line_merge(hyp) and oid in same_line_first:
                            words = hyp.chosen.alto_words
                            hpos, vpos, width, height = _merged_bounds_top_left(words)
                            content = hyp.chosen_LLM_token.word if hyp.chosen_LLM_token else text_utils.decode_html_entities(orig.content)
                            ac = alignment_confidence.alignment_confidence(hyp)
                            cpid = hyp.chosen_LLM_token.clean_para_id if hyp.chosen_LLM_token else None
                            items.append((content, hpos, vpos, width, height, words[0].wc, layout_tag, ac, cpid))
                            for w in words[1:]:
                                seen_same_line_merge_ids.add(w.id)
                        elif not _is_same_line_merge(hyp):
                            # Cross-line merge: first element gets merged word, rest get empty string (strip hyphenation fragment).
                            content = hyp.chosen_LLM_token.word if (hyp.chosen_LLM_token and oid in cross_line_first) else ""
                            ac = alignment_confidence.alignment_confidence(hyp)
                            cpid = hyp.chosen_LLM_token.clean_para_id if hyp.chosen_LLM_token else None
                            items.append((content, orig.hpos, orig.vpos, orig.width, orig.height, orig.wc, layout_tag, ac, cpid))
                        else:
                            continue
                    else:
                        content = hyp.chosen_LLM_token.word if hyp.chosen_LLM_token else text_utils.decode_html_entities(orig.content)
                        ac = alignment_confidence.alignment_confidence(hyp)
                        cpid = hyp.chosen_LLM_token.clean_para_id if hyp.chosen_LLM_token else None
                        items.append((content, orig.hpos, orig.vpos, orig.width, orig.height, orig.wc, layout_tag, ac, cpid))
                else:
                    content = text_utils.decode_html_entities(orig.content)
                    ac = max(0, min(100, int(round(orig.wc * 0.35))))
                    items.append((content, orig.hpos, orig.vpos, orig.width, orig.height, orig.wc, None, ac, None))
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
    layout_tag: Optional[str] = None,
    align_conf: int = 0,
    clean_para_id: Optional[int] = None,
) -> ET.Element:
    el = ET.Element(ns_tag)
    el.set("ID", word_id)
    el.set("HPOS", str(hpos))
    el.set("VPOS", str(vpos))
    el.set("WIDTH", str(width))
    el.set("HEIGHT", str(height))
    el.set("CONTENT", content)
    el.set("WC", str(wc))
    # Alignment QA score 0–100 (mapping + neighbor consistency); WC stays Tesseract OCR confidence.
    el.set("ALIGNCONF", str(max(0, min(100, int(align_conf)))))
    if clean_para_id is not None:
        el.set("CLEANPARA", str(int(clean_para_id)))
    if layout_tag is not None:
        el.set("LAYOUT", layout_tag)
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

    page_el = (
        root.find(f".//{{{ALTO_NS}}}Page")
        or root.find(f".//{{{ALTO_NS_V3}}}Page")
        or root.find(".//alto:Page", namespaces=NS)
        or root.find(".//alto3:Page", namespaces=NS)
    )
    if page_el is None:
        raise ValueError("No Page element found in ALTO file.")
    page_id = page_el.get("ID", "")

    for block_el in (
        page_el.findall(f".//{{{ALTO_NS}}}TextBlock")
        or page_el.findall(f".//{{{ALTO_NS_V3}}}TextBlock")
        or page_el.findall(".//*[local-name()='TextBlock']")
    ):
        block_id = block_el.get("ID", "")
        for line_el in list(block_el):
            if "TextLine" not in line_el.tag:
                continue
            line_id = line_el.get("ID", "")
            key = (page_id, block_id, line_id)
            items = line_outputs.get(key, [])
            new_children = []
            for seq, (content, hpos, vpos, width, height, wc, layout_tag, align_conf, clean_para_id) in enumerate(
                items, start=1
            ):
                word_id = _word_id_from_parts(block_id, line_id, seq)
                new_children.append(
                    _make_string_el(
                        word_id, content, hpos, vpos, width, height, wc, ns_tag, layout_tag, align_conf, clean_para_id
                    )
                )
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
    with open(output_path, "r", encoding="utf-8") as f:
        text = f.read()
    text = _normalize_written_alto(text)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)


def _update_one_page_in_tree(
    root: ET.Element,
    page: Any,
    hypothesis_list: List[Any],
    ns_tag: str,
) -> None:
    """Update a single Page element in the tree (by page.id). Modifies root in place."""
    ordered_ids = [s.id for s in page.all_strings()]
    id_to_hyps = _build_id_to_hyps(hypothesis_list)
    line_outputs = _build_line_outputs(page, hypothesis_list, id_to_hyps, ordered_ids)

    # Find the Page element with this page's ID
    page_el = None
    for el in root.iter():
        if "Page" in el.tag and el.get("ID") == page.id:
            page_el = el
            break
    if page_el is None:
        page_el = (
            root.find(f".//{{{ALTO_NS}}}Page")
            or root.find(f".//{{{ALTO_NS_V3}}}Page")
            or root.find(".//alto:Page", namespaces=NS)
            or root.find(".//alto3:Page", namespaces=NS)
        )
    if page_el is None:
        raise ValueError(f"No Page element found for page id {page.id}.")
    page_id = page_el.get("ID", "")

    for block_el in (
        page_el.findall(f".//{{{ALTO_NS}}}TextBlock")
        or page_el.findall(f".//{{{ALTO_NS_V3}}}TextBlock")
        or page_el.findall(".//*[local-name()='TextBlock']")
    ):
        block_id = block_el.get("ID", "")
        for line_el in list(block_el):
            if "TextLine" not in line_el.tag:
                continue
            line_id = line_el.get("ID", "")
            key = (page_id, block_id, line_id)
            items = line_outputs.get(key, [])
            new_children = []
            for seq, (content, hpos, vpos, width, height, wc, layout_tag, align_conf, clean_para_id) in enumerate(
                items, start=1
            ):
                word_id = _word_id_from_parts(block_id, line_id, seq)
                new_children.append(
                    _make_string_el(
                        word_id, content, hpos, vpos, width, height, wc, ns_tag, layout_tag, align_conf, clean_para_id
                    )
                )
            for c in list(line_el):
                line_el.remove(c)
            for el in new_children:
                line_el.append(el)


def write_aligned_alto_multi(
    xml_path: str,
    page_hypothesis_pairs: List[Tuple[Any, Any]],
    output_path: str,
) -> None:
    """
    Write a multi-page ALTO XML with CONTENT updated from alignment for each page.
    page_hypothesis_pairs: list of (page, hypothesis_list) in document order.
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    ns_tag = _ns("String")
    for el in root.iter():
        if "String" in el.tag:
            ns_tag = el.tag
            break

    for page, hypothesis_list in page_hypothesis_pairs:
        _update_one_page_in_tree(root, page, hypothesis_list, ns_tag)

    ET.indent(tree, space="  ", level=0)
    tree.write(output_path, encoding="utf-8", xml_declaration=True, method="xml")
    with open(output_path, "r", encoding="utf-8") as f:
        text = f.read()
    text = _normalize_written_alto(text)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)


def merge_alto_files(alto_paths: List[str], output_path: str) -> None:
    """
    Merge multiple single-page ALTO files into one ALTO file (first file's root + all Pages).
    alto_paths: paths to ALTO files, each containing one Page element.
    """
    if not alto_paths:
        raise ValueError("No ALTO paths to merge.")
    tree = ET.parse(alto_paths[0])
    root = tree.getroot()
    layout = (
        root.find(f".//{{{ALTO_NS}}}Layout")
        or root.find(f".//{{{ALTO_NS_V3}}}Layout")
        or root.find(".//alto:Layout", namespaces=NS)
        or root.find(".//alto3:Layout", namespaces=NS)
    )
    if layout is None:
        layout = root
    for path in alto_paths[1:]:
        other = ET.parse(path)
        other_root = other.getroot()
        page_el = (
            other_root.find(f".//{{{ALTO_NS}}}Page")
            or other_root.find(f".//{{{ALTO_NS_V3}}}Page")
            or other_root.find(".//alto:Page", namespaces=NS)
            or other_root.find(".//alto3:Page", namespaces=NS)
        )
        if page_el is not None:
            layout.append(page_el)
    ET.indent(tree, space="  ", level=0)
    tree.write(output_path, encoding="utf-8", xml_declaration=True, method="xml")
    with open(output_path, "r", encoding="utf-8") as f:
        text = f.read()
    text = _normalize_written_alto(text)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
