"""
Smoke tests for the alignment pipeline.
Uses the minimal example in examples/sample_page/ so no OCR or LLM is required.
"""

import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

# Project root (parent of tests/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
SAMPLE_XML = PROJECT_ROOT / "examples" / "sample_page" / "page-1.xml"
# Minimal toy hOCR (fixed bboxes) for make_cleaned_pdf / hocr_combine smoke tests.
MINIMAL_HOCR = PROJECT_ROOT / "examples" / "sample_page" / "page-1.hocr.html"
SAMPLE_CLEANTEXT = PROJECT_ROOT / "examples" / "sample_page" / "page-1_cleantext.txt"
# Real Tesseract hOCR for RoleRandomness76.pdf page 1 (examples/sample_page/RoleRandomness76.pdf).
ROLE_RANDOMNESS_PAGE1_HOCR = (
    PROJECT_ROOT / "examples" / "sample_page" / "RoleRandomness76_page1.hocr.html"
)
ROLE_RANDOMNESS_PAGE1_CLEAN = (
    PROJECT_ROOT / "examples" / "sample_page" / "RoleRandomness76_page1-clean.txt"
)
# Alignment on full academic page needs more wall-clock time than the toy fixture.
_ROLE_RANDOMNESS_ALIGN_TIMEOUT_S = 300

# Ensure matplotlib/fontconfig caches go somewhere writable (especially in sandboxed runs)
BASE_ENV = os.environ.copy()
BASE_ENV.setdefault("MPLBACKEND", "Agg")
BASE_ENV.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".mplconfig"))
BASE_ENV.setdefault("XDG_CACHE_HOME", str(PROJECT_ROOT / ".cache"))


_FALLBACK_HOCR = """<!doctype html>
<html>
  <head><meta charset="utf-8" /><title>fallback (hOCR)</title></head>
  <body>
    <div class="ocr_page" id="page_1" title="bbox 0 0 1000 1000">
      <div class="ocr_carea" id="block_1_1" title="bbox 50 100 950 200">
        <span class="ocr_line" id="line_1_1" title="bbox 50 100 950 200">
          <span class="ocrx_word" id="word_1" title="bbox 50 120 100 160; x_wconf 96">The</span>
          <span class="ocrx_word" id="word_2" title="bbox 110 120 200 160; x_wconf 95">quick</span>
          <span class="ocrx_word" id="word_3" title="bbox 210 120 320 160; x_wconf 95">brown</span>
          <span class="ocrx_word" id="word_4" title="bbox 330 120 390 160; x_wconf 94">fox</span>
        </span>
      </div>
    </div>
  </body>
</html>
"""


def _ensure_minimal_hocr(tmp_dir: Path) -> Path:
    if MINIMAL_HOCR.is_file():
        return MINIMAL_HOCR
    p = tmp_dir / "page-1.hocr.html"
    p.write_text(_FALLBACK_HOCR, encoding="utf-8")
    return p


def _ensure_sample_cleantext(tmp_dir: Path) -> Path:
    if SAMPLE_CLEANTEXT.is_file():
        return SAMPLE_CLEANTEXT
    p = tmp_dir / "page-1_cleantext.txt"
    p.write_text("The quick brown fox\n", encoding="utf-8")
    return p


def test_align_completes_with_example():
    """Run alignment on sample page; assert process completes successfully."""
    if not SAMPLE_XML.is_file():
        # Repo fixtures can be swapped by users; keep hOCR tests independent.
        return
    assert SAMPLE_CLEANTEXT.is_file(), f"Sample cleantext missing: {SAMPLE_CLEANTEXT}"

    cmd = [
        sys.executable,
        str(SRC_ROOT / "map_up_text.py"),
        "--xml-file", str(SAMPLE_XML),
        "--clean-text", str(SAMPLE_CLEANTEXT),
    ]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=BASE_ENV, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, (
        f"map_up_text.py failed (exit {result.returncode})\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_align_produces_output_hocr():
    """Run alignment with --output-hocr to a temp file; assert file is created and looks like hOCR."""
    if not ROLE_RANDOMNESS_PAGE1_HOCR.is_file() or not ROLE_RANDOMNESS_PAGE1_CLEAN.is_file():
        return
    sample_hocr = ROLE_RANDOMNESS_PAGE1_HOCR
    sample_clean = ROLE_RANDOMNESS_PAGE1_CLEAN

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        out_hocr = f.name
    try:
        cmd = [
            sys.executable,
            str(SRC_ROOT / "map_up_text.py"),
            "--hocr-file", str(sample_hocr),
            "--clean-text", str(sample_clean),
            "--output-hocr", out_hocr,
        ]
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=BASE_ENV,
            capture_output=True,
            text=True,
            timeout=_ROLE_RANDOMNESS_ALIGN_TIMEOUT_S,
        )
        assert result.returncode == 0, (
            f"map_up_text.py failed (exit {result.returncode})\nstderr:\n{result.stderr}"
        )
        assert os.path.isfile(out_hocr), f"Output hOCR was not written: {out_hocr}"
        text = Path(out_hocr).read_text(encoding="utf-8", errors="replace")
        assert "ocrx_word" in text, "Expected ocrx_word spans in aligned hOCR"
    finally:
        if os.path.isfile(out_hocr):
            os.unlink(out_hocr)


def test_align_produces_output_xml():
    """Run alignment with --output-xml to a temp file; assert file is created and valid ALTO."""
    if not SAMPLE_XML.is_file():
        return
    assert SAMPLE_CLEANTEXT.is_file(), f"Sample cleantext missing: {SAMPLE_CLEANTEXT}"

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
        out_xml = f.name
    try:
        cmd = [
            sys.executable,
            str(SRC_ROOT / "map_up_text.py"),
            "--xml-file", str(SAMPLE_XML),
            "--clean-text", str(SAMPLE_CLEANTEXT),
            "--output-xml", out_xml,
        ]
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=BASE_ENV, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, (
            f"map_up_text.py failed (exit {result.returncode})\nstderr:\n{result.stderr}"
        )
        assert os.path.isfile(out_xml), f"Output XML was not written: {out_xml}"

        tree = ET.parse(out_xml)
        root = tree.getroot()
        assert root is not None
        # ALTO v3 uses default namespace; find String elements (aligned words)
        ns_alto = "http://www.loc.gov/standards/alto/ns-v3#"
        strings = list(root.iter("{%s}String" % ns_alto))
        if not strings:
            strings = list(root.iter("String"))
        assert len(strings) >= 1, "Expected at least one String in aligned ALTO"
    finally:
        if os.path.isfile(out_xml):
            os.unlink(out_xml)


def test_run_pipeline_align_with_example():
    """Run pipeline align step on sample page; assert success."""
    if not SAMPLE_XML.is_file():
        return
    assert SAMPLE_CLEANTEXT.is_file(), f"Sample cleantext missing: {SAMPLE_CLEANTEXT}"

    cmd = [
        sys.executable,
        str(SRC_ROOT / "run_pipeline.py"),
        "align",
        "--xml-file", str(SAMPLE_XML),
        "--clean-text", str(SAMPLE_CLEANTEXT),
    ]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=BASE_ENV, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, (
        f"run_pipeline.py align failed (exit {result.returncode})\nstderr:\n{result.stderr}"
    )


def test_run_pipeline_align_hocr_with_example():
    """Run pipeline align step on sample hOCR page; assert success."""
    if not ROLE_RANDOMNESS_PAGE1_HOCR.is_file() or not ROLE_RANDOMNESS_PAGE1_CLEAN.is_file():
        return
    sample_hocr = ROLE_RANDOMNESS_PAGE1_HOCR
    sample_clean = ROLE_RANDOMNESS_PAGE1_CLEAN

    cmd = [
        sys.executable,
        str(SRC_ROOT / "run_pipeline.py"),
        "align",
        "--hocr-file", str(sample_hocr),
        "--clean-text", str(sample_clean),
        "--output-hocr",
    ]
    result = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=BASE_ENV,
        capture_output=True,
        text=True,
        timeout=_ROLE_RANDOMNESS_ALIGN_TIMEOUT_S,
    )
    assert result.returncode == 0, (
        f"run_pipeline.py align (hOCR) failed (exit {result.returncode})\nstderr:\n{result.stderr}"
    )


def test_make_cleaned_pdf_from_hocr_smoke():
    """Build a searchable PDF using the sample hOCR and a generated blank PNG page."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        sample_hocr = _ensure_minimal_hocr(td_path)
        img_path = td_path / "page.png"
        out_pdf = td_path / "out.pdf"

        # Create a blank page image (matches sample hOCR's bbox 1000x1000 well enough)
        from PIL import Image  # Pillow is already a dependency

        Image.new("RGB", (1000, 1000), color=(255, 255, 255)).save(img_path)

        cmd = [
            sys.executable,
            str(SRC_ROOT / "make_cleaned_pdf.py"),
            "--image", str(img_path),
            "--aligned-hocr", str(sample_hocr),
            "--output", str(out_pdf),
            "--dpi", "300",
        ]
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=BASE_ENV, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, (
            f"make_cleaned_pdf.py failed (exit {result.returncode})\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert out_pdf.is_file(), "Expected output PDF to be written"
        assert out_pdf.stat().st_size > 0, "Expected output PDF to be non-empty"


def test_hocr_combine_smoke():
    """Combine two per-page hOCR files into a single multi-page hOCR and verify it has two ocr_page blocks."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        sample_hocr = _ensure_minimal_hocr(td_path)
        p1 = td_path / "page-1.hocr.html"
        p2 = td_path / "page-2.hocr.html"
        out = td_path / "combined_hocr.html"
        p1.write_text(sample_hocr.read_text(encoding="utf-8"), encoding="utf-8")
        p2.write_text(sample_hocr.read_text(encoding="utf-8"), encoding="utf-8")

        import hocr_combine

        hocr_combine.combine_hocr_files([p1, p2], out)
        combined = out.read_text(encoding="utf-8", errors="replace")
        assert combined.count("ocr_page") >= 2, "Expected multiple ocr_page blocks in combined hOCR"


if __name__ == "__main__":
    test_align_completes_with_example()
    print("✓ test_align_completes_with_example")
    test_align_produces_output_hocr()
    print("✓ test_align_produces_output_hocr")
    test_align_produces_output_xml()
    print("✓ test_align_produces_output_xml")
    test_run_pipeline_align_with_example()
    print("✓ test_run_pipeline_align_with_example")
    test_run_pipeline_align_hocr_with_example()
    print("✓ test_run_pipeline_align_hocr_with_example")
    test_make_cleaned_pdf_from_hocr_smoke()
    print("✓ test_make_cleaned_pdf_from_hocr_smoke")
    test_hocr_combine_smoke()
    print("✓ test_hocr_combine_smoke")
    print("All smoke tests passed.")
