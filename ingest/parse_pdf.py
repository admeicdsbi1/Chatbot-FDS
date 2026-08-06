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

# ---- "is this page a scan?" -------------------------------------------------
# A page whose text layer came from a scanner's own OCR still extracts plenty of
# characters — they are simply wrong ("CAI No 8,-2025t16", "Date: 1614.2025",
# "l/odifications"). The char-count triggers below cannot see that (these pages
# hold 950-1800 chars), and a whole-document force_ocr flag cannot express it
# either: in this corpus the damage sits on the *cover* page of an otherwise
# born-digital document — exactly the page carrying the letter number and date.
#
# Text statistics do NOT separate these pages: measured over known-garbled vs
# known-clean VB pages, stopword ratio was 0.28-0.34 vs 0.29-0.35 and
# dirty-token ratio 0.036-0.048 vs 0.006-0.053 — fully overlapping, because the
# page really is ~95% correct prose with a few critical tokens mangled.
#
# What does separate them, perfectly, is geometry: a page rendered as one image
# covering the whole sheet IS a scan, so its text layer is scanner output by
# definition, however clean it reads. Measured 1.00 coverage on every garbled
# page vs 0.00-0.08 on every born-digital one.
SCAN_COVERAGE = 0.9


def page_image_coverage(page):
    """Largest embedded image's area as a fraction of the page area."""
    area = page.rect.width * page.rect.height
    best = 0.0
    for info in page.get_image_info():
        r = fitz.Rect(info["bbox"])
        best = max(best, (r.width * r.height) / max(area, 1))
    return best


def is_scanned_page(page):
    return page_image_coverage(page) >= SCAN_COVERAGE


# ---- mojibake detection (shared with ingest/eval/audit_garbled.py) -----------
# The other failure mode: born-digital PDFs with a broken font encoding, whose
# text is not merely lossy but nonsense. Real prose uses common English stopwords
# constantly; mojibake has almost none. Tables and short/label-only blocks are
# excluded, as they legitimately contain few stopwords.
STOP = set(("the of to and a in is for be shall with on as by or that this are at "
            "from will not it its an been being which each any all per such system "
            "fire coach railway detection supply power supplier railways board "
            "office letter dated ref sub no design maintenance").split())

STOP_MIN = 0.08     # prose below this stopword ratio is treated as garbled
MIN_TOKENS = 12     # too few words to judge


def is_table_text(t):
    return t.lstrip().startswith("Table") or (t.count("|") / max(len(t), 1) > 0.03)


def stopword_ratio(text):
    """Fraction of alpha tokens that are common stopwords, or None when the text
    is a table / too short to judge."""
    if is_table_text(text):
        return None
    toks = re.findall(r"[A-Za-z]{2,}", text)
    if len(toks) < MIN_TOKENS:
        return None
    return sum(1 for t in toks if t.lower() in STOP) / len(toks)


def is_garbled(text):
    r = stopword_ratio(text)
    return r is not None and r < STOP_MIN


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


# Documents that are letters, not manuals: a letterhead, a Sub: line and numbered
# paragraphs, with no headings anywhere.
LETTER_DOC_TYPES = {"circular", "instruction_letter",
                    "special_maintenance_instruction",
                    "coach_alteration_instruction"}


def _retitle_letter_sections(sections, entry):
    """Give every section of a letter-shaped document its subject line as title.

    Heading detection has nothing real to latch onto in these documents, so it
    picks up address blocks ("All Zonal Railways & PUs"), signature fragments
    ("approval)") and date lines ("Date: As signed"). That is not just an ugly
    citation: rag.py multiplies a chunk's score by the overlap between its section
    title and the query (~1.15-1.6x), so boilerplate titles quietly deny these
    documents the boost a manual's "Speed sensors" heading receives. For a letter
    the Sub: line IS the section title — which is what the force-OCR path already
    assumes; this extends the same rule to born-digital letters.
    """
    if entry.get("doc_type") not in LETTER_DOC_TYPES or not sections:
        return sections
    # The REGISTRY title wins over a Sub: line scraped from the body, because
    # these letters routinely carry the letter they supersede as an attachment —
    # and that attachment's Sub: line is indistinguishable from the document's
    # own. Scraping gave VB_CTRB_SKF_Replacement_SS2_2025 the subject of the 2025
    # withholding letter reproduced on its page 3. The registry title is
    # human-verified, so it is the more trustworthy of the two.
    title = (entry.get("title") or "").strip()
    if not title:
        body = " ".join(b["text"] for s in sections for b in s["blocks"])
        title = _ocr_section_title(body, entry, sections[0]["page_start"])
    for s in sections:
        s["section"] = title
    return sections


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
                           "ocr_merged": used_ocr, "suspect_layer": True})
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
        # A scanned or mojibake text layer is worse than no text layer: it looks
        # extractable, so it needs OCR just as much as a blank scan does.
        suspect = is_scanned_page(page) or is_garbled(" ".join(l["text"] for l in line_items))
        needs_ocr = (page_chars < NEEDS_OCR_CHARS and bool(page.get_images())) or suspect

        # Once such a page HAS been OCR'd, drop its native text entirely rather
        # than appending the OCR to it: keeping both would leave "Date: 1614.2025"
        # in the same chunk as the correct "16.04.2025", and two conflicting dates
        # in one chunk is worse than either alone. Headings go with it — a heading
        # read off a scanner layer is itself suspect, and section titles feed a
        # 1.15-1.6x retrieval multiplier in rag.py.
        page_ocr = _ocr_text_for(doc_id, page_no)
        use_native = not (suspect and page_ocr)

        # emit lines, opening a new section at each heading
        buf = []

        def flush_buf():
            if buf:
                current["blocks"].append({"type": "text", "text": " ".join(buf),
                                          "page": page_no})
                buf.clear()

        for li in (line_items if use_native else []):
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
        # content; on diagram pages it adds labels the native text lacks; on
        # scanned/mojibake pages it REPLACES the native text (use_native above)
        ocr_merged = False
        if page_ocr:
            if not use_native:
                # Suppressing the native lines also suppressed this page's heading
                # events, so its OCR text would otherwise be filed under whatever
                # section was last open — usually the default "Introduction". That
                # is the boilerplate-title trap that costs a document rag.py's
                # section-title multiplier, so title the page the way the force-OCR
                # path does: from the letter's own Sub: line, then the registry title.
                flush_buf()
                if current["blocks"]:
                    sections.append(current)
                current = {"section": _ocr_section_title(page_ocr, entry, page_no),
                           "section_num": "", "page_start": page_no, "blocks": []}
            current["blocks"].append({"type": "text", "text": page_ocr, "page": page_no})
            ocr_merged = True

        page_stats.append({"page": page_no, "chars": page_chars,
                           "tables": len(table_blocks), "big_images": big_images,
                           "needs_ocr": needs_ocr and not ocr_merged,
                           "ocr_merged": ocr_merged, "suspect_layer": suspect})

    if current["blocks"]:
        sections.append(current)
    doc.close()

    # slide decks / circulars may not produce headings; fall back to per-page sections
    if len(sections) < 3 and n_pages > 3:
        sections = _per_page_sections(path, entry, repeated)
    return _retitle_letter_sections(sections, entry), page_stats


def _per_page_sections(path, entry, repeated):
    """Fallback: one section per page, titled by the page's first short line."""
    doc = fitz.open(path)
    sections = []
    for pno in range(len(doc)):
        page_no = pno + 1
        lines = [l.strip() for l in doc[pno].get_text().splitlines()
                 if l.strip() and l.strip() not in repeated]
        text = " ".join(lines)
        ocr = _ocr_text_for(entry["doc_id"], page_no)
        # same rule as extract(): OCR replaces a scanner/mojibake text layer,
        # and merely supplements a weak-but-trustworthy one
        if ocr and (is_scanned_page(doc[pno]) or is_garbled(text)):
            text, lines = "", []
        title = next((l for l in lines if 3 <= len(l) <= 80), None) \
            or _ocr_section_title(ocr or "", entry, page_no)
        blocks = []
        if text:
            blocks.append({"type": "text", "text": text, "page": page_no})
        if ocr and len(text) < WEAK_TEXT_CHARS:
            blocks.append({"type": "text", "text": ocr, "page": page_no})
        if blocks:
            sections.append({"section": title, "section_num": "",
                             "page_start": page_no, "blocks": blocks})
    doc.close()
    return sections
