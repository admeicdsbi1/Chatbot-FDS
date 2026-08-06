"""
scaffold_registry.py — turn a folder of PDFs into pre-filled doc_registry entries
for a human to verify. Authoring 65 entries by hand is both the bottleneck of a
large ingest and its likeliest source of silent metadata errors.

    python ingest/scaffold_registry.py --dir "Vande Bharat"
    python ingest/scaffold_registry.py --dir "Vande Bharat" --only wheel --only CTRB

Prints a paste-ready Python block plus, above each entry, a REVIEW comment listing
what could not be determined confidently. Nothing here is authoritative: the output
is 65 pre-filled forms, not a registry.

Two rules it deliberately does NOT break:
  * `supersedes` is always [] — supersession changes which value the app quotes and
    must be signed off by an engineer (see doc_registry's header).
  * `letter_no` / `issue_date` are cross-checked between the FILENAME and the page-1
    text, and any disagreement is reported rather than silently resolved. On a
    scanned cover page the text layer is the scanner's own OCR, which is exactly
    where these fields get mangled ("Date: 1614.2025" for 16.04.2025), so the two
    sources disagreeing is the signal that the page needs OCR before it is trusted.
"""
import load_env  # noqa: F401  — must precede doc_registry (reads PDF_BUCKET_BASE at import)

import argparse
import os
import re
import sys

import fitz

from doc_registry import REGISTRY, DOCUMENTS_ROOT
from parse_pdf import _SUBJECT_RE, is_scanned_page, is_garbled

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# --- subsystem routing vocabulary. `subsystem` is stamped on every chunk and is
# what separates a door query from an HVAC one once one coach type dominates the
# corpus, so a wrong guess here is a retrieval bug, not a cosmetic one.
SUBSYSTEMS = [
    ("bearings", r"\bCTRB\b|\bbearing|\bSKF\b|\baxle\s*box|refurbish|\bgrease\b"),
    ("wheels", r"\bwheel|re-?profil|\btyre\b|\bdiameter\b|marking|stamping|\bflange\b|\bKLW\b"),
    ("air suspension", r"\bair\s*spring|\bair\s*suspension\b|\bASDIS\b|\blevelling\s+valve\b"),
    ("bogie", r"\bbogie\b|\bspring|\bdamper\b|central\s+sleeve|vibration"),
    ("HVAC", r"\bRMPU\b|\bHVAC\b|air\s*condition|\bCPA\b|\bscoop\b|\bduct\b|pre-?filter|\blouvre\b"),
    ("doors", r"\bdoor\b|hatch|\bramp\b|wheel\s*chair|door\s*handle"),
    ("brakes", r"\bbrake|\bWSP\b|wheel\s*slide|leakage\s*test|\bASDIS\b|\bAS\s+leakage"),
    ("electrical", r"\bVCB\b|\bbattery\b|connector|jumper|\bcable\b|shielding|\bADCR\b|\bVCD\b|"
                   r"master\s+controller|traction|dimming|\bconverter\b|power\s+supply|\bcoupler\b"),
    ("interior fittings", r"trim\s+panel|\bFRP\b|wash\s*basin|\bseat\b|footrest|hammer|wiper|"
                          r"polycarbonate|nose\s*cone|sealing|drain\s*hole|lifting\s*pad|"
                          r"isolating\s*cock|plumbing|\bglass\b"),
    ("maintenance schedule", r"\bSS-?[12]\b|shop\s+schedule|\bIWWP\b|preparedness|\bschedule\b"),
    ("fire detection", r"\bFSDS\b|\bFDSS\b|fire\s+detect|\bsmoke\b"),
]

DOC_TYPES = [
    ("coach_alteration_instruction", r"\bCAI\b"),
    ("special_maintenance_instruction", r"\bSMI\b|VB[_/]SMI"),
    ("report", r"\breport\b|guidelines?"),
]

# Letter numbers as printed on these documents: RDSO/ICF/Railway Board series.
_LETTER_RES = [
    re.compile(r"\b(MC[/\-][A-Za-z0-9/\-\.]{2,30})", re.I),
    re.compile(r"\b(VB\s*/\s*SMI\s*/\s*[A-Z]\s*/\s*\d+)", re.I),
    re.compile(r"\b(IRCAMTECH/[A-Za-z0-9/\-\.&]{3,40})", re.I),
    re.compile(r"\bNo\.?\s*[:\-]?\s*(I\s*C\s*F/[A-Za-z0-9/\-\.'\s]{4,40})", re.I),
    re.compile(r"\bNo\.?\s*[:\-]?\s*([A-Z][A-Za-z0-9]*(?:[/\-][A-Za-z0-9\.]+){2,})"),
]
# The colon is required, and only the letterhead block is searched. Without both,
# this matches the "…letter No. MC/WA/Genl. dated 17.07.2025" inside a Ref line and
# stamps a document with the date of the letter it *cites* — verified on
# 2025_10_25_Replacement of SKF Bearing, whose own date field reads "Date: As signed".
_PAGE_DATE_RE = re.compile(r"\bDate[d]?\s*[:\-]\s*(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", re.I)
_LETTERHEAD_CHARS = 1200
_CAI_NO_RE = re.compile(r"\bCAI\s*([AB])[\s\-]*(\d{4})[\-/](\d{1,2})\b", re.I)


def _iso(d, m, y):
    if not (1 <= d <= 31 and 1 <= m <= 12 and 2000 <= y <= 2035):
        return ""
    return f"{y:04d}-{m:02d}-{d:02d}"


def date_from_filename(fn):
    """These filenames carry the date in five different shapes. Returns ISO or ''."""
    for pat, order in (
        (r"(20\d{2})[_\-](\d{2})[_\-](\d{2})", "ymd"),   # 2025_10_25_… / 2024-08-08-…
        (r"\b(\d{2})[_\-](\d{2})[_\-](20\d{2})", "dmy"),  # 25_09_2025 …
        (r"(\d{2})\.(\d{2})\.(20\d{2})", "dmy"),          # …_07.09.2024 / dated 23.10.2020
        (r"\b(\d{2})(\d{2})(20\d{2})\b", "dmy"),          # …11082025
    ):
        m = re.search(pat, fn)
        if m:
            a, b, c = (int(x) for x in m.groups())
            iso = _iso(c, b, a) if order == "ymd" else _iso(a, b, c)
            if iso:
                return iso
    m = re.search(r"\b(20\d{2})\b", fn)          # CAI B-2024-06 → year only
    return m.group(1) if m else ""


def date_from_text(text):
    m = _PAGE_DATE_RE.search(text[:_LETTERHEAD_CHARS])
    if m:
        return _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return ""


def letter_from_text(text):
    for rx in _LETTER_RES:
        m = rx.search(text[:_LETTERHEAD_CHARS])
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip(" .,;:")
    return ""


def letter_from_filename(fn):
    m = re.search(r"VB[_\s]*SMI[_\s]*([A-Z])[_\s]*(\d{1,2})", fn, re.I)
    if m:
        return f"VB/SMI/{m.group(1).upper()}/{int(m.group(2)):02d}"
    m = _CAI_NO_RE.search(fn) or re.search(r"\bCAI\s*([AB])[\s\-]*(\d{4})[\-/](\d{1,2})", fn, re.I)
    if m:
        return f"CAI {m.group(1).upper()}-{m.group(2)}/{int(m.group(3)):02d}"
    return ""


def title_from_text(text, fallback):
    m = _SUBJECT_RE.search(text)
    if m:
        subj = re.sub(r"[*_`]", "", m.group(1))
        subj = re.sub(r"\s+", " ", subj).strip(" .:-")
        if 8 <= len(subj) <= 160:
            return subj
    return fallback


def classify(haystack, table, default):
    for name, pat in table:
        if re.search(pat, haystack, re.I):
            return name
    return default


def doc_id_from(fn):
    stem = os.path.splitext(fn)[0]
    stem = re.sub(r"\(\d+\)|_[a-z0-9]{8}$", "", stem)          # "(1)", download suffixes
    stem = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_")
    stem = re.sub(r"_+", "_", stem)
    return ("VB_" + stem)[:60].rstrip("_")


def scaffold(path, rel_path):
    doc = fitz.open(path)
    n = len(doc)
    p1 = doc[0].get_text() if n else ""
    scans = sum(1 for p in doc if is_scanned_page(p))
    text_chars = sum(len(p.get_text().strip()) for p in doc)
    doc.close()

    fn = os.path.basename(path)
    hay = fn + " " + p1

    fn_date, tx_date = date_from_filename(fn), date_from_text(p1)
    fn_letter, tx_letter = letter_from_filename(fn), letter_from_text(p1)

    warn = []
    # A filename/page disagreement on these two fields is the scanner-OCR tell.
    if fn_date and tx_date and fn_date != tx_date:
        warn.append(f"date: filename={fn_date} vs page={tx_date}")
    if not (fn_date or tx_date):
        warn.append("no date found")
    if fn_letter and tx_letter and fn_letter.lower().replace(" ", "") not in \
            tx_letter.lower().replace(" ", ""):
        warn.append(f"letter_no: filename={fn_letter!r} vs page={tx_letter!r}")
    if not (fn_letter or tx_letter):
        warn.append("no letter_no found")
    if scans:
        warn.append(f"{scans}/{n} pages are scans — page-1 metadata is scanner OCR, "
                    f"re-check after ingest/ocr_gemini.py")
    if is_garbled(p1):
        warn.append("page 1 text is mojibake")
    if not _SUBJECT_RE.search(p1):
        warn.append("no 'Sub:' line — title taken from filename")

    force_ocr = n > 0 and text_chars / n < 120      # effectively image-only document

    return {
        "doc_id": doc_id_from(fn),
        "path": rel_path,
        "doc_type": classify(hay, DOC_TYPES, "circular"),
        "title": title_from_text(p1, os.path.splitext(fn)[0].replace("_", " ").strip()),
        "source": "",
        "system": "VB",
        "default_oem": None,
        "coach_type": ["Vande Bharat"],
        "subsystem": classify(hay, SUBSYSTEMS, ""),
        "issue_date": tx_date or fn_date,
        "revision": "",
        "letter_no": tx_letter or fn_letter,
        "supersedes": [],
        **({"force_ocr": True} if force_ocr else {}),
    }, warn, n, scans


def emit(entry, warn, pages, scans):
    print(f"    # {pages} pages, {scans} scanned"
          + ("".join(f"\n    # REVIEW: {w}" for w in warn) if warn else ""))
    print("    {")
    for k, v in entry.items():
        if k == "path":
            head, tail = os.path.split(v)
            print(f'        "path": os.path.join({head!r}, {tail!r}),')
        else:
            print(f"        {k!r}: {v!r},")
    print("    },")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="folder under Documents/")
    ap.add_argument("--only", action="append", default=[],
                    help="only files whose name contains this (repeatable)")
    args = ap.parse_args()

    root = os.path.normpath(os.path.join(DOCUMENTS_ROOT, args.dir))
    if not os.path.isdir(root):
        raise SystemExit(f"no such folder: {root}")
    known = {e["path"] for e in REGISTRY}

    rows = []
    for fn in sorted(os.listdir(root)):
        if not fn.lower().endswith(".pdf"):
            continue
        if args.only and not any(s.lower() in fn.lower() for s in args.only):
            continue
        rel = os.path.join(args.dir, fn)
        if rel in known:
            print(f"# already registered, skipped: {fn}", file=sys.stderr)
            continue
        rows.append(scaffold(os.path.join(root, fn), rel))

    print(f"# --- {len(rows)} scaffolded entries from Documents/{args.dir} ---")
    print("# VERIFY EVERY FIELD before pasting into doc_registry.REGISTRY.")
    print("# `supersedes` is intentionally left [] — it needs an engineer's sign-off.")
    ids = set()
    for entry, warn, pages, scans in rows:
        while entry["doc_id"] in ids:                # filenames can collide after normalising
            entry["doc_id"] += "_2"
        ids.add(entry["doc_id"])
        emit(entry, warn, pages, scans)
    print(f"# --- end ({sum(s for *_, s in rows)} scanned pages need OCR) ---")


if __name__ == "__main__":
    main()
