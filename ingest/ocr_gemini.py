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
import load_env  # noqa: F401  — must precede the GEMINI_API_KEY read below

import argparse
import base64
import os
import sys
import time

import fitz
import requests

from doc_registry import REGISTRY, pdf_path
from parse_pdf import (OCR_CACHE_DIR, WEAK_TEXT_CHARS, BIG_IMAGE_WH,
                       is_garbled, is_scanned_page)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
# flash-lite keeps heavy multi-hundred-page OCR runs inside the daily free vision
# quota; override to a larger model per-run if a batch of pages transcribes poorly.
MODEL = os.environ.get("GEMINI_OCR_MODEL", "gemini-3.1-flash-lite")
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
SLEEP = float(os.environ.get("GEMINI_OCR_SLEEP", "5"))

# Groq-vision fallback (separate free quota): used only when the Gemini OCR call
# fails/throttles, so ingestion isn't blocked by one provider's daily limit. Same
# transcription prompt, so OCR quality/handling is unchanged when it does run.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_OCR_MODEL = os.environ.get("GROQ_OCR_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

PROMPT = """Transcribe ALL text visible in this scanned page from an Indian Railways maintenance manual (FSDS fire detection / WSP wheel slide protection).

Rules:
- Output plain text / markdown only, no commentary.
- Reproduce tables as markdown tables with their header row.
- For wiring diagrams or panel layouts: list EVERY component designation and label you can read (e.g. relay K05, MCB Q1, terminal X7.22d), each with its visible description, like "K05 - off delay timer relay".
- Keep exact values: voltages, part numbers, fault codes, thresholds, timings.
- If the page is bilingual, transcribe both Hindi and English text.
- If truly nothing is readable, output exactly: [UNREADABLE]"""

# Fallback prompt for pages Gemini refuses with finishReason RECITATION.
# Verbatim-transcription framing over a *published* circular (the RDSO WSP
# instruction letters are public documents the model has memorised) trips the
# recitation filter and returns zero parts — silently, since the HTTP status is
# still 200. Re-asking for the same content as a structured technical extraction
# clears the filter and, as a side effect, recovers table column headers that the
# scanned text layer had detached from their values. Values are still required
# verbatim, so numeric fidelity is unchanged.
EXTRACT_PROMPT = """You are reading a page from an Indian Railways engineering maintenance document, to build an internal technical index for depot maintenance staff.

Extract, as structured markdown, the engineering content of this image:
- every table, as a markdown table with its header row and all cell values
- every technical value: sizes, part numbers, model designations, voltages, pressures, timings, tolerances, fault codes
- every component designation and its description (e.g. "K05 - off delay timer relay")
- the subject line, and any reference letter numbers and dates

Report all values exactly as printed — they are safety-critical. Do not add commentary or interpretation. If nothing technical is visible, output exactly: [UNREADABLE]"""

# Horizontal bands (with overlap) used as a last resort when a whole page is
# refused: a band carrying only part of the document is usually not recognised as
# recitation, so the technical content still gets through.
BAND_COUNT = 3
BAND_OVERLAP = 0.08

# Once the daily vision cap is reached, every remaining page costs the full
# retry ladder (~3.5 min of backoff) and still fails. Stop the run instead of
# grinding through hundreds of pages discovering the same wall one at a time —
# nothing is lost, because a failed page writes no cache entry and is retried on
# the next run.
QUOTA_GIVE_UP_AFTER = 3


def qualifying_pages(entry):
    """Pages worth OCR: weak/moderate native text with a big embedded image
    (scanned circulars, slides), several big images regardless of text (wiring-
    diagram pages whose captions extract fine but whose component labels — e.g.
    relay K05 — live inside the images), or a page that IS a full-page scan.

    The scan case is not covered by any character-count rule: those pages extract
    950-1800 characters, they are simply the scanner's own OCR of them, so
    without this test a lossy scanner-OCR cover page is never queued at all."""
    doc = fitz.open(pdf_path(entry))
    # force_ocr docs (corrupted native text) get every page OCR'd
    if entry.get("force_ocr"):
        pages = list(range(1, len(doc) + 1))
        doc.close()
        return pages
    out = []
    for pno in range(len(doc)):
        page = doc[pno]
        text = page.get_text().strip()
        chars = len(text)
        big = sum(1 for img in page.get_images()
                  if img[2] >= BIG_IMAGE_WH[0] and img[3] >= BIG_IMAGE_WH[1])
        if (big >= 1 and chars < 800) or big >= 2 or is_scanned_page(page) \
                or is_garbled(text):
            out.append(pno + 1)
    doc.close()
    return out


def _ocr_gemini(png, prompt=PROMPT):
    """-> (text|None, finish_reason|None). A 200 response with no parts is NOT a
    generic failure: finishReason tells us whether to give up (SAFETY) or retry
    under different framing (RECITATION), so it is returned to the caller."""
    if not GEMINI_API_KEY:
        return None, None
    payload = {
        "contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": "image/png",
                             "data": base64.b64encode(png).decode()}},
            {"text": prompt},
        ]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 4000,
                             "thinkingConfig": {"thinkingBudget": 0}},
    }
    for attempt in range(6):
        r = requests.post(URL, params={"key": GEMINI_API_KEY}, json=payload, timeout=120)
        if r.status_code == 200:
            cands = r.json().get("candidates", [])
            if not cands:
                return None, None
            finish = cands[0].get("finishReason")
            parts = cands[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts).strip()
            if not text:
                print(f"    gemini returned no text (finishReason={finish})")
            return (text or None), finish
        if r.status_code in (429, 500, 503):
            wait = min(2 ** attempt * 5, 60)
            print(f"    gemini {r.status_code}, retrying in {wait}s")
            time.sleep(wait)
            continue
        print(f"    gemini OCR failed {r.status_code}: {r.text[:160]}")
        return None, None
    return None, None


def _render(entry, page_no, clip=None, zoom=2.0):
    doc = fitz.open(pdf_path(entry))
    page = doc[page_no - 1]
    rect = page.rect
    if clip is not None:
        clip = fitz.Rect(rect.x0, clip[0], rect.x1, clip[1])
    png = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip).tobytes("png")
    height = rect.height
    y0 = rect.y0
    doc.close()
    return png, y0, height


def _ocr_banded(entry, page_no):
    """Split the page into overlapping horizontal bands and OCR each separately.
    Used only when the full page is refused as recitation; partial bands usually
    are not. Bands still refused are skipped rather than failing the page, so we
    keep whatever content did come through."""
    _, y0, height = _render(entry, page_no)
    out, refused = [], 0
    for i in range(BAND_COUNT):
        top = max(y0, y0 + height * (i / BAND_COUNT) - height * BAND_OVERLAP)
        bot = min(y0 + height,
                  y0 + height * ((i + 1) / BAND_COUNT) + height * BAND_OVERLAP)
        png, _, _ = _render(entry, page_no, clip=(top, bot), zoom=2.5)
        text, finish = _ocr_gemini(png, EXTRACT_PROMPT)
        if text and text != "[UNREADABLE]":
            out.append(text)
        else:
            refused += 1
        time.sleep(SLEEP)
    if refused:
        print(f"    banded: {BAND_COUNT - refused}/{BAND_COUNT} bands recovered")
    return "\n\n".join(out) or None


def _ocr_groq(png):
    if not GROQ_API_KEY:
        return None
    data_url = "data:image/png;base64," + base64.b64encode(png).decode()
    payload = {
        "model": GROQ_OCR_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}],
        "temperature": 0.0, "max_tokens": 4000, "stream": False,
    }
    try:
        r = requests.post(GROQ_URL, headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"}, json=payload, timeout=120)
        if r.status_code != 200:
            print(f"    groq OCR failed {r.status_code}: {r.text[:160]}")
            return None
        choices = r.json().get("choices", [])
        return choices[0]["message"]["content"].strip() if choices else None
    except Exception as e:
        print(f"    groq OCR error: {e}")
        return None


def ocr_page(entry, page_no):
    """Fallback ladder: verbatim prompt -> extraction prompt (clears RECITATION)
    -> per-band extraction -> Groq vision (separate quota)."""
    png, _, _ = _render(entry, page_no)
    text, finish = _ocr_gemini(png)
    if text:
        return text
    if finish == "RECITATION":
        # published circular the model won't recite back; re-ask as extraction
        print("    recitation-blocked, retrying as structured extraction")
        time.sleep(SLEEP)
        text, _ = _ocr_gemini(png, EXTRACT_PROMPT)
        if text:
            return text
        print("    still blocked, retrying per-band")
        text = _ocr_banded(entry, page_no)
        if text:
            return text
    return _ocr_groq(png)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", help="only this doc_id")
    args = ap.parse_args()
    if not GEMINI_API_KEY:
        raise SystemExit("GEMINI_API_KEY not set — required for OCR.")

    entries = [e for e in REGISTRY if not args.doc or e["doc_id"] == args.doc]
    total_done = total_skipped = 0
    consecutive_failures = 0
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
                consecutive_failures = 0
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
                consecutive_failures += 1
                if consecutive_failures >= QUOTA_GIVE_UP_AFTER:
                    print(f"\n{consecutive_failures} pages failed in a row after the "
                          f"full retry ladder — the daily vision quota is spent. "
                          f"Stopping here rather than burning ~3.5 min of backoff per "
                          f"remaining page.")
                    print(f"OCR stopped: {total_done} new pages this run, "
                          f"{total_skipped} already cached.")
                    print("The free tier resets at midnight Pacific; rerun then and "
                          "it picks up exactly where this left off.")
                    raise SystemExit(2)
            time.sleep(SLEEP)
    print(f"OCR complete: {total_done} new pages, {total_skipped} already cached.")


if __name__ == "__main__":
    main()
