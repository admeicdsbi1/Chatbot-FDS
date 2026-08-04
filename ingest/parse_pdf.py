"""
parse_pdf.py — deep PDF extraction with PyMuPDF.

Per document:
  - text blocks in reading order (sorted by y, then x), excluding table regions
  - tables via page.find_tables() -> markdown (kept intact for chunking)
  - heading detection: numbered sections, ALL-CAPS lines, larger/bold font
  - running header/footer suppression (lines repeated on >=60% of pages)
  - OCR cache merge: ingest/ocr_cache/<doc_id>/pNNN.txt is appended to pages
    whose native text is weak (scanned circulars, presentation slides)

Output: (sections, page_stats)
  sections:   [{section, section_num, page_start, blocks:[{type, text, page}]}]
  page_stats: [{page, chars, tables, big_images, needs_ocr, ocr_merged}]
"""
import os
import re
from collections import Counter

import fitz

OCR_CACHE_DIR = os.path.join(os.path.dirname(__file__), "ocr_cache")

BOLD_FLAG = 16                 # PyMuPDF span flag bit for bold
WEAK_TEXT_CHARS = 300          # below this + a big image => OCR candidate
NEEDS_OCR_CHARS = 30           # below this + any image => effectively scanned
BIG_IMAGE_WH = (300, 200)

_NUMBERED_HEADING = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]?\s+(\S.{2,85})$")
_TOC_DOTS = re.compile(r"\.{4,}\s*\d*\s*$")


def _line_text(line):
    return "".join(s.get("text", "") for s in line.get("spans", [])).strip()


def _line_size(line):
    return max((s.get("size", 0) for s in line.get("spans", [])), default=0)


def _line_bold(line):
    spans = line.get("spans", [])
    return bool(spans) and all(s.get("flags", 0) & BOLD_FLAG for s in spans if s.get("text", "").strip())


def _is_allcaps_heading(text):
    if not (3 <= len(text) <= 70) or "|" in text:
        return False
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 3 and all(c.isupper() for c in letters)


def _in_any_rect(bbox, rects):
    cx = (bbox[0] + bbox[2]) / 2
    cy = (bbox[1] + bbox[3]) / 2
    return any(r[0] <= cx <= r[2] and r[1] <= cy <= r[3] for r in rects)


def _ocr_text_for(doc_id, page_no):
    path = os.path.join(OCR_CACHE_DIR, doc_id, f"p{page_no:03d}.txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            t = f.read().strip()
        return t or None
    return None


def _collect_repeated_lines(pages_lines, n_pages):
    """Lines occurring verbatim on >=60% of pages (and >=3 pages) are running
    headers/footers/watermarks — e.g. 'Classification | ESCORTS KUBOTA-CONFIDENTIAL'."""
    counts = Counter()
    for lines in pages_lines:
        for t in set(lines):
            if 3 <= len(t) <= 120:
                counts[t] += 1
    threshold = max(3, int(0.6 * n_pages))
    return {t for t, c in counts.items() if c >= threshold}


_SUBJECT_RE = re.compile(
    r"^[\s*#>|-]*(?:\*\*)?\s*(?:sub|subject|विषय)\s*(?:\*\*)?\s*[:\-]\s*(?:\*\*)?\s*(.+)",
    re.I | re.M)


def _ocr_section_title(text, entry, page_no):
    """Section title for a force-OCR page.

    The obvious choice — the page's first short line — lands on the letterhead
    ("भारत सरकार - रेल मंत्रालय") or a markdown artifact ("### Document Metadata")
    for every scanned RDSO circular. That is not just an ugly citation: rag.py
    multiplies a chunk's score by the overlap between its section title and the
    query (~1.15-1.6x), so a boilerplate title silently costs these documents the
    boost that every OEM manual's "Speed sensors" heading receives. Prefer the
    letter's Subject line, then the registry title, and only then a short line.
    """
    m = _SUBJECT_RE.search(text)
    if m:
        subj = re.sub(r"[*_`]", "", m.group(1)).strip(" .:-")
        if 3 <= len(subj) <= 120:
            return subj
    title = (entry.get("title") or "").strip()
    if title:
        return title[:120]
    first = next((l.strip() for l in text.splitlines()
                  if 3 <= len(l.strip()) <= 80), None)
    return first or f"Page {page_no}"


def _ocr_only(path, entry):
    """Force-OCR path: for PDFs whose native text is corrupted (bad font
    encoding) or is a lossy scanner-OCR layer, ignore the native text and build
    one section per page from the OCR cache. Falls back to native text only if a
    page has no OCR yet."""
    doc = fitz.open(path)
    sections, page_stats = [], []
    for pno in range(len(doc)):
        page_no = pno + 1
        ocr = _ocr_text_for(entry["doc_id"], page_no)
        used_ocr = bool(ocr)
        text = ocr if used_ocr else re.sub(r"\s+", " ", doc[pno].get_text().strip())
        if text:
            sections.append({"section": _ocr_section_title(text, entry, page_no),
                             "section_num": "", "page_start": page_no,
                             "blocks": [{"type": "text", "text": text, "page": page_no}]})
        page_stats.append({"page": page_no, "chars": len(text), "tables": 0,
                           "big_images": 0, "needs_ocr": not used_ocr and not text,
                           "ocr_merged": used_ocr})
    doc.close()
    return sections, page_stats


def extract(path, entry):
    if entry.get("force_ocr"):
        return _ocr_only(path, entry)
    doc_id = entry["doc_id"]
    doc = fitz.open(path)
    n_pages = len(doc)

    # ---- pass 1: raw lines per page (for body font size + repeated-line detection)
    page_dicts = []
    pages_line_texts = []
    all_sizes = Counter()
    for page in doc:
        d = page.get_text("dict")
        page_dicts.append(d)
        texts = []
        for block in d.get("blocks", []):
            for line in block.get("lines", []):
                t = _line_text(line)
                if t:
                    texts.append(t)
                    sz = _line_size(line)
                    if sz:
                        all_sizes[round(sz)] += len(t)
        pages_line_texts.append(texts)
    body_size = all_sizes.most_common(1)[0][0] if all_sizes else 10
    repeated = _collect_repeated_lines(pages_line_texts, n_pages)

    # ---- pass 2: tables + ordered blocks + heading events
    sections = []
    current = {"section": "Introduction", "section_num": "", "page_start": 1, "blocks": []}
    page_stats = []

    for pno in range(n_pages):
        page = doc[pno]
        page_no = pno + 1
        d = page_dicts[pno]

        table_rects, table_blocks = [], []
        try:
            tf = page.find_tables()
            for tb in tf.tables:
                md = tb.to_markdown().strip()
                if md and md.count("|") >= 4:
                    table_rects.append(tuple(tb.bbox))
                    table_blocks.append({"type": "table", "text": md, "page": page_no,
                                         "y": tb.bbox[1]})
        except Exception:
            pass

        # text lines outside table regions, in reading order
        line_items = []
        for block in d.get("blocks", []):
            if block.get("type", 0) != 0:
                continue
            for line in block.get("lines", []):
                t = _line_text(line)
                if not t or t in repeated:
                    continue
                if _in_any_rect(line.get("bbox", block.get("bbox")), table_rects):
                    continue
                line_items.append({
                    "text": t, "y": line["bbox"][1], "x": line["bbox"][0],
                    "size": _line_size(line), "bold": _line_bold(line),
                })
        line_items.sort(key=lambda l: (round(l["y"], 1), l["x"]))

        page_chars = sum(len(l["text"]) for l in line_items)
        big_images = 0
        for img in page.get_images():
            try:
                if img[2] >= BIG_IMAGE_WH[0] and img[3] >= BIG_IMAGE_WH[1]:
                    big_images += 1
            except Exception:
                pass
        needs_ocr = page_chars < NEEDS_OCR_CHARS and bool(page.get_images())

        # emit lines, opening a new section at each heading
        buf = []

        def flush_buf():
            if buf:
                current["blocks"].append({"type": "text", "text": " ".join(buf),
                                          "page": page_no})
                buf.clear()

        for li in line_items:
            t = li["text"]
            if _TOC_DOTS.search(t):
                continue
            m = _NUMBERED_HEADING.match(t)
            is_heading = False
            sec_num = ""
            if m and (li["bold"] or li["size"] >= body_size + 1.0 or "." in m.group(1)):
                is_heading, sec_num = True, m.group(1)
                title = m.group(2).strip()
            elif _is_allcaps_heading(t):
                is_heading, title = True, t
            elif (li["size"] >= body_size + 1.5 or li["bold"]) and len(t) <= 85 \
                    and not t[-1:] in ".:," and len(t.split()) <= 12 and any(c.isalpha() for c in t):
                is_heading, title = True, t
            if is_heading:
                flush_buf()
                if current["blocks"]:
                    sections.append(current)
                current = {"section": title, "section_num": sec_num,
                           "page_start": page_no, "blocks": []}
            else:
                buf.append(t)
        flush_buf()

        # tables belong to the section active at end of page
        for tb in sorted(table_blocks, key=lambda b: b["y"]):
            current["blocks"].append({"type": "table", "text": tb["text"], "page": page_no})

        # merge cached OCR text whenever it exists — on weak pages it IS the
        # content; on diagram pages it adds labels the native text lacks
        ocr_merged = False
        ocr = _ocr_text_for(doc_id, page_no)
        if ocr:
            current["blocks"].append({"type": "text", "text": ocr, "page": page_no})
            ocr_merged = True

        page_stats.append({"page": page_no, "chars": page_chars,
                           "tables": len(table_blocks), "big_images": big_images,
                           "needs_ocr": needs_ocr and not ocr_merged,
                           "ocr_merged": ocr_merged})

    if current["blocks"]:
        sections.append(current)
    doc.close()

    # slide decks / circulars may not produce headings; fall back to per-page sections
    if len(sections) < 3 and n_pages > 3:
        sections = _per_page_sections(path, entry, repeated)
    return sections, page_stats


def _per_page_sections(path, entry, repeated):
    """Fallback: one section per page, titled by the page's first short line."""
    doc = fitz.open(path)
    sections = []
    for pno in range(len(doc)):
        page_no = pno + 1
        lines = [l.strip() for l in doc[pno].get_text().splitlines()
                 if l.strip() and l.strip() not in repeated]
        title = next((l for l in lines if 3 <= len(l) <= 80), f"Page {page_no}")
        text = " ".join(lines)
        blocks = []
        if text:
            blocks.append({"type": "text", "text": text, "page": page_no})
        ocr = _ocr_text_for(entry["doc_id"], page_no)
        if ocr and len(text) < WEAK_TEXT_CHARS:
            blocks.append({"type": "text", "text": ocr, "page": page_no})
        if blocks:
            sections.append({"section": title, "section_num": "",
                             "page_start": page_no, "blocks": blocks})
    doc.close()
    return sections
