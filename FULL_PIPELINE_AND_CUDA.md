# Full OCR pipeline, GPU / CUDA, and this repository

## What lives **in this repo** (`ocr-text-aligner`)

**This project does not use CUDA or PyTorch.** It is a **CPU-only** Python toolset:

- Input: ALTO XML + a **clean text** file (from your upstream workflow).
- Output: aligned tokens, visualizations, tables (`map_up_text.py`).

Install with `pip install -r requirements.txt` (rapidfuzz, matplotlib, rich, reportlab). No NVIDIA driver is required to **run the aligner**.

---

## Where the **full newspaper / VLM pipeline** lives

End-to-end flows that produce ALTO and clean text (PDF → raster → Tesseract → layout segmentation → Chandra / vLLM → LLM reading order → **then** this aligner) are maintained **separately**, e.g. the **British Colonist** driver repo (`bc_colonist_hocr_chandra_align` or your fork). That driver calls this repo as a **library/CLI** via:

```bash
python3 map_up_text.py --xml-file "…" --clean-text "…"
```

So: **macro-chunking, Chandra crops, hyphen-friendly assembly** are upstream concerns—what matters here is that **`clean_text` reads continuously** (fewer spurious line breaks across column fragments) so hyphen logic and fuzzy matching behave well. If upstream sends one coherent page string, this aligner can reconcile soft hyphens and OCR splits against **page-level** ALTO.

---

## ⚠️ If your machine does **not** support CUDA

### You can still use **this aligner**

No change. Run `map_up_text.py` as documented in `README.md`.

### You can still run the **full upstream pipeline**, with caveats

The upstream stack may use:

| Component | Typical GPU use | Without CUDA |
|-----------|-----------------|--------------|
| **vLLM** (Chandra-2, etc.) | Strongly prefers NVIDIA GPU for throughput | Use **CPU** or a **remote** API if available; generation is **much slower** and may need smaller batch sizes / shorter context. Some setups use **Metal (Apple)** or **ROCm (AMD)**—not the same as “CUDA” but may accelerate **some** PyTorch builds; vLLM itself is still mostly NVIDIA-focused. |
| **DocLayout-YOLO** / PyTorch layout | Often trained with CUDA | Set **`device: cpu`** in config; runs on CPU, slower. |
| **Tesseract** | CPU | No GPU required. |

### Practical steps (no CUDA)

1. **Confirm there is no NVIDIA GPU usable from Linux/WSL**  
   ```bash
   nvidia-smi
   ```  
   If the command fails or shows no device, assume **no CUDA** for PyTorch/vLLM.

2. **Upstream config** (names vary by repo; example ideas):  
   - **`doclayout_device: cpu`** for DocLayout-YOLO.  
   - **Chandra / vLLM**: point `VLLM_API_BASE` at a **remote** server with a GPU, **or** run a CPU-capable inference path if your Chandra packaging supports it (expect long runtimes).  
   - Reduce **batch size**, **max workers**, and **image size** (`imgsz`) to avoid OOM on CPU.

3. **Skip the VLM** for debugging: some drivers support **Tesseract-only** fallbacks for block text so you can validate **aligner + ALTO** without Chandra.

4. **Apple Silicon (M1/M2/M3)**: There is **no NVIDIA CUDA**. Use CPU for layout models unless you have a **PyTorch build with MPS** and libraries that support it. vLLM on Mac is **not** the same as Linux+NVIDIA; plan on **remote vLLM** or CPU.

5. **Windows**: Prefer **WSL2 + Linux** for vLLM/PyTorch stacks, or run heavy inference **remotely**.

### Expectations

- **Aligner**: minutes per page on CPU is unusual; usually seconds.  
- **Layout + Chandra on CPU**: can be **tens of minutes per page** for dense broadsheets—normal, not a bug.  
- If something **errors** with `CUDA out of memory` on a machine **without** CUDA, an upstream script is still requesting **`cuda:0`**—switch every `device` / `CUDA_VISIBLE_DEVICES` usage to **CPU** or fix the remote API URL.

---

## Hyphen reconciliation and chunk size (upstream)

The aligner’s strength is **joining OCR tokens to a coherent clean string** (including hyphenated line breaks). That works best when:

- Clean text is assembled **per page** (or large blocks), not as dozens of one-line Chandra snippets with hard line breaks between crops.

Upstream work (e.g. **macro-chunks for Chandra**, LLM instructions to merge hyphenation) belongs in the **driver repo**, not in `ocr-text-aligner` itself. This repo assumes you already produced a good **`clean_text` file**.

---

## References

- **Aligner usage:** [README.md](README.md)  
- **Pipeline logic:** [PIPELINE_EXPLANATION.md](PIPELINE_EXPLANATION.md)  
- **Driver integration (example):** your `bc_colonist_hocr_chandra_align` repo → `docs/ALIGNER.md` and `SEGMENTATION_EXPERIMENTS.md`

---

*Last updated: April 2026 — co-maintained with the British Colonist driver; keep CUDA notes here so clone-only users see GPU scope without reading the full pipeline repo.*
