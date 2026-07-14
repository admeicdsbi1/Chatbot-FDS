"""
ocr_gemini.py — one-time OCR of image-heavy pages via Gemini vision.

Tesseract is not installed on this machine, but the project already runs on the
Gemini API, so scanned circulars / presentation slides / wiring diagrams are
transcribed by rendering the page to PNG and asking gemini-2.5-flash for a
faithful markdown transcription (tables as markdown tables, diagram labels
like relay designations K01..K99 listed explicitly).

Results are cached as ingest/ocr_cache/<doc_id>/pNNN.txt and picked up
automatically by parse_pdf.py on the next build_kb.py run. Re-running skips
cached pages, so the API is only hit once per page, ever.

    set GEMINI_API_KEY=...
    python ingest/ocr_gemini.py            # all qualifying pages, all docs
    python ingest/ocr_gemini.py --doc KB_CMG_WSP_Presentation
"""
import argparse
import base64
import os
import sys
import time

import fitz
import requests

from doc_registry import REGISTRY, pdf_path
from parse_pdf import OCR_CACHE_DIR, WEAK_TEXT_CHARS, BIG_IMAGE_WH

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL = os.environ.get("GEMINI_OCR_MODEL", "gemini-3.5-flash")
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
SLEEP = float(os.environ.get("GEMINI_OCR_SLEEP", "5"))

PROMPT = """Transcribe ALL text visible in this scanned page from an Indian Railways maintenance manual (FSDS fire detection / WSP wheel slide protection).

Rules:
- Output plain text / markdown only, no commentary.
- Reproduce tables as markdown tables with their header row.
- For wiring diagrams or panel layouts: list EVERY component designation and label you can read (e.g. relay K05, MCB Q1, terminal X7.22d), each with its visible description, like "K05 - off delay timer relay".
- Keep exact values: voltages, part numbers, fault codes, thresholds, timings.
- If the page is bilingual, transcribe both Hindi and English text.
- If truly nothing is readable, output exactly: [UNREADABLE]"""


def qualifying_pages(entry):
    """Pages worth OCR: weak/moderate native text with a big embedded image
    (scanned circulars, slides), or several big images regardless of text
    (wiring-diagram pages whose captions extract fine but whose component
    labels — e.g. relay K05 — live inside the images)."""
    doc = fitz.open(pdf_path(entry))
    out = []
    for pno in range(len(doc)):
        page = doc[pno]
        chars = len(page.get_text().strip())
        big = sum(1 for img in page.get_images()
                  if img[2] >= BIG_IMAGE_WH[0] and img[3] >= BIG_IMAGE_WH[1])
        if (big >= 1 and chars < 800) or big >= 2:
            out.append(pno + 1)
    doc.close()
    return out


def ocr_page(entry, page_no):
    doc = fitz.open(pdf_path(entry))
    pix = doc[page_no - 1].get_pixmap(matrix=fitz.Matrix(2, 2))
    png = pix.tobytes("png")
    doc.close()
    payload = {
        "contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": "image/png",
                             "data": base64.b64encode(png).decode()}},
            {"text": PROMPT},
        ]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 4000,
                             "thinkingConfig": {"thinkingBudget": 0}},
    }
    for attempt in range(6):
        r = requests.post(URL, params={"key": GEMINI_API_KEY}, json=payload, timeout=120)
        if r.status_code == 200:
            cands = r.json().get("candidates", [])
            if not cands:
                return None
            parts = cands[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts).strip() or None
        if r.status_code in (429, 500, 503):
            wait = min(2 ** attempt * 5, 60)
            print(f"    {r.status_code}, retrying in {wait}s")
            time.sleep(wait)
            continue
        print(f"    OCR failed {r.status_code}: {r.text[:160]}")
        return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", help="only this doc_id")
    args = ap.parse_args()
    if not GEMINI_API_KEY:
        raise SystemExit("GEMINI_API_KEY not set — required for OCR.")

    entries = [e for e in REGISTRY if not args.doc or e["doc_id"] == args.doc]
    total_done = total_skipped = 0
    for entry in entries:
        pages = qualifying_pages(entry)
        if not pages:
            continue
        cache_dir = os.path.join(OCR_CACHE_DIR, entry["doc_id"])
        os.makedirs(cache_dir, exist_ok=True)
        print(f"{entry['doc_id']}: {len(pages)} qualifying pages {pages}")
        for pno in pages:
            out_path = os.path.join(cache_dir, f"p{pno:03d}.txt")
            if os.path.exists(out_path):
                total_skipped += 1
                continue
            print(f"  OCR p{pno}...")
            text = ocr_page(entry, pno)
            if text and text != "[UNREADABLE]":
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(text)
                total_done += 1
                print(f"    -> {len(text)} chars")
            elif text == "[UNREADABLE]":
                # the model saw the page and found nothing — cache the empty
                # marker so we don't re-send a genuinely blank page forever
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write("")
                print("    -> unreadable")
            else:
                # API failure (404/429/exhausted retries): write NOTHING so the
                # next run retries this page instead of skipping a poisoned cache
                print("    -> FAILED (no cache written; rerun to retry)")
            time.sleep(SLEEP)
    print(f"OCR complete: {total_done} new pages, {total_skipped} already cached.")


if __name__ == "__main__":
    main()
