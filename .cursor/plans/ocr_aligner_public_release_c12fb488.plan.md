---
name: OCR aligner public release
overview: "Polish the ocr-text-aligner repo for public GitHub release for two audiences: digital humanities users (run the pipeline, get results) and ML/OCR researchers (understand and extend the algorithms). Focus on docs, examples, repo hygiene, and minimal automated checks."
todos: []
isProject: false
---

# OCR Text Aligner — Public Release Plan

## Audiences

- **DH users**: Run OCR → clean → align; get aligned ALTO and cleaned PDFs. Need clear setup, a runnable example, and “what to expect” (including limitations).
- **ML researchers**: Understand and modify alignment (fuzzy + context + proximity, hyphen/merge handling). Need algorithm overview, entry points in code, and notes on known gaps (e.g. PENDING_ANALYSIS, tagged_span_matcher).

---

## 1. Documentation

### 1.1 README (main project)

- **Add a short “What this does”** (1–2 sentences) and a **one-command quickstart** (e.g. align-only with paths to sample files) near the top.
- **Audience signposting**: Two short sections — “Using the pipeline (DH)” and “Extending the algorithms (ML/research)” — with links to the right docs and source files.
- **Limitations**: Move/condense “Missing from current version” and “TODO” into a single **Limitations / Known issues** section; state that alignment works best when LLM-cleaned text is close to correct and OCR is moderate; mention single-article testing and that full-page / complex layouts may need manual prep or future work.
- **Example data**: Either document where to get a minimal ALTO + cleantext pair (e.g. from `inputs/` or a small example dir) or add a tiny `examples/` with one page so `python3 run_pipeline.py align ...` works out of the box. Avoid committing large PDFs/binary blobs; use small samples or point to external URLs if needed.
- **Config**: Briefly document `pipeline_config.json` (and that `pipeline_config.example.json` exists) and `TESSERACT_EXPERIMENT_DIR` in Setup/Prerequisites.
- **Last updated**: Refresh the “Last updated” date when you ship.

Keep existing setup, usage, project structure, dependencies, and license; link to [PIPELINE_EXPLANATION.md](PIPELINE_EXPLANATION.md) and [llm_cleaning/README.md](llm_cleaning/README.md) for depth.

### 1.2 Algorithm / research-facing doc

- **Single “Algorithm overview” doc** (e.g. `ALGORITHM.md` or a section in `PIPELINE_EXPLANATION.md`): high-level flow (fuzzy → context → hyphen/merges → linking → proximity), with **file/function pointers** for each stage (e.g. `fuzzy_matching.py`, `context_matching.py`, `hyphen_linking.py`, `map_up_text.run_candidate_pipeline`, `run_one_iteration`). Mention that paragraph/column boundaries and duplicate-word resolution are known limitations (point to [PENDING_ANALYSIS.md](PENDING_ANALYSIS.md) for details).
- **Tagged spans**: In README or ALGORITHM, note that `tagged_span_matcher.py` is experimental and not yet correct; link to README TODO so ML folks know what’s in progress.

This gives DH users a clear path to “run it” and ML users a map to “change it.”

---

## 2. Repo hygiene and first-run experience

- **.gitignore**: Already good. Ensure `outputs/`, `venv/`, `pipeline_work/` (if you don’t want to commit run artifacts), and any local secrets/config (e.g. `pipeline_config.json` if it contains paths/secrets) are ignored; keep `pipeline_config.example.json` committed.
- **Sensitive or local paths**: Don’t commit `pipeline_config.json` if it has machine-specific paths; document that users copy `pipeline_config.example.json` to `pipeline_config.json` and edit.
- **Top-level clutter**: Consider moving internal/scratch docs (`DESIGN.md`, `PENDING_ANALYSIS.md`, `LAYOUT_TAGS_PLAN.md`) into a `docs/` or `dev/` folder so the root is “user-facing” (README, LICENSE, pipeline, examples). Optional: add a one-line note in README like “Design notes and known-issue analysis are in `docs/`.”
- **LICENSE**: Already present (MIT); no change needed.
- **requirements.txt**: Pin versions for reproducibility (e.g. `rapidfuzz>=3.0,<4`) if you want; otherwise a brief note in README that “Python 3.8+” and listed deps are tested is enough for a first release.

---

## 3. Example and quickstart

- **Minimal runnable example**: Add a small, self-contained example so that:
  - DH users can run **align only** with two committed files (e.g. one ALTO XML + one cleantext) and see output without OCR or LLM.
  - Optionally, document a one-page **full pipeline** (OCR → clean → align) if you can include a tiny PDF/image or point to a public URL.
- **Where**: e.g. `examples/sample_page/` with `page-1.xml` and `page-1_cleantext.txt` (or similar), plus a short `examples/README.md` with the exact commands. Link from main README “Quickstart” to this.

---

## 4. Testing and CI (lightweight)

- **Smoke test**: One or two tests that run the alignment pipeline on the minimal example (e.g. `map_up_text` with `--xml-file` and `--clean-text`) and assert it completes without error and produces expected outputs (e.g. table or `--output-xml` file exists). Use the same sample files as in `examples/`.
- **LLM cleaning**: Keep or extend [llm_cleaning/test_ocr_refiner.py](llm_cleaning/test_ocr_refiner.py) as needed; optional: one test that mocks Ollama and checks chunker/validator behavior so CI doesn’t require Ollama.
- **CI**: Add a single GitHub Actions workflow that runs on push/PR: create venv, `pip install -r requirements.txt`, run the smoke test(s). This gives both DH and ML contributors confidence that the main path still works.

---

## 5. Optional but useful

- **CONTRIBUTING.md**: Short note: “Issues and PRs welcome; for algorithm changes, see ALGORITHM.md and PENDING_ANALYSIS.md.”
- **Version**: Add a `__version`__ in a single place (e.g. `run_pipeline.py` or a small `version.py`) and expose it with `python3 run_pipeline.py --version` (and optionally in `map_up_text.py --version`) so people can report “version X.”
- **Changelog**: A minimal `CHANGELOG.md` with “Unreleased” and a first version entry (e.g. “Initial public release”) helps future maintenance; optional for day-one.

---

## 6. What to leave as-is (for now)

- **No PyPI package** in this plan; clone-and-run from GitHub is enough. You can add `pyproject.toml` and `pip install -e .` later if you want.
- **Layout tags / LAYOUT_TAGS_PLAN.md**: No implementation required for release; keep as roadmap and reference.
- **DESIGN.md / PENDING_ANALYSIS**: Keep as developer notes; moving to `docs/` is optional.
- **GUI / batch processing**: Already in “Future development”; no change.

---

## Summary checklist


| Area         | Action                                                                                    |
| ------------ | ----------------------------------------------------------------------------------------- |
| README       | Quickstart, audience sections, limitations, example/config docs, date                     |
| Algorithm    | One doc with flow + file/function pointers; link PENDING_ANALYSIS and tagged_span_matcher |
| Examples     | Minimal `examples/` with ALTO + cleantext and commands                                    |
| Repo hygiene | .gitignore/config example; optional move of DESIGN/PENDING/LAYOUT to docs/                |
| Tests        | Smoke test(s) for align step (and optional LLM mock test)                                 |
| CI           | One workflow: install deps, run tests                                                     |
| Optional     | CONTRIBUTING.md, --version, CHANGELOG.md                                                  |


This keeps the repo focused, honest about limitations, and navigable for both DH users and ML researchers without over-engineering the first public release.