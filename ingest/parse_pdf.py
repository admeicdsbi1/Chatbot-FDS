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


# Symbol fonts (Wingdings, Symbol, Webdings) encode their glyphs in the Unicode
# Private Use Area, so a tick drawn in Wingdings extracts as U+F0FC, not U+2713.
# That is invisible three times over: the embedding model sees an unknown
# codepoint, rag's keyword index only takes [a-zA-Z]{3,}, and the LLM is handed
# a character with no meaning. The shop-schedule report marks SS-1/SS-2/SS-3
# applicability with exactly these ticks — 19,520 of them across the corpus —
# so for every electrical item the answer to "is this done in SS-2?" was present
# in the file and unreadable at every stage of the pipeline.
_PUA_MAP = {
    "": "✓", "": "✓", "": "✗", "": "➤",
    "": "•", "": "•", "": "•", "": "▼",
    "": "▼", "": "→", "": "←", "": "↔",
    "": "→", "": "°", "": "µ", "": "Ω",
    "": "±", "": "×", "": "□", "": "●",
    "": "∞", "": "∈", "": " ", "": "-",
}
_PUA_RE = re.compile(r"[-]")


def normalize_symbols(text):
    """Map private-use symbol-font codepoints onto real characters.

    Anything unmapped is dropped rather than kept: an unknown PUA codepoint
    carries no information downstream and only pollutes the vector."""
    if not text or not _PUA_RE.search(text):
        return text
    return _PUA_RE.sub(lambda m: _PUA_MAP.get(m.group(0), ""), text)


def _line_text(line):
    return normalize_symbols(
        "".join(s.get("text", "") for s in line.get("spans", []))).strip()


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


# Table strategies, tried in order of how much structure they preserve. The
# default ("lines") shatters a table whose rules are drawn per-cell: on the
# shop-schedule report's electrical pages it produced THIRTY columns with the
# header split mid-token ("**  S**|**  S1**|**   S**|**   S**|**   2**"), so the
# SS-1/SS-2/SS-3 column identity was destroyed on 412 chunks. "lines_strict"
# reads the same page as 14 columns with the labels intact. Which one wins is a
# property of the individual page, so choose per table rather than globally.
_TABLE_STRATEGIES = ("lines_strict", "lines", "text")

# `\|Col\d+\|` cannot count adjacent placeholders: the closing pipe of one match
# is the opening pipe of the next, so "|Col6|Col7|Col8|" scored 2, not 3. Every
# strategy was under-counted, but not by the same factor.
_COLN_RE = re.compile(r"\|Col\d+(?=\|)")
_COLN_CELL = re.compile(r"^Col\d+$")

# A cell boundary that cuts a word in half: "12 Lakh kilom|eter". Real tables
# almost never do this — across the 2,659 committed chunks the rate per cell
# boundary is 0 at the 90th percentile and 0.068 at the 99th — while a grid laid
# over a prose page does it constantly (90th percentile 0.58). The two
# populations do not overlap, so unlike the garble statistics this one separates.
_WORD_SPLIT_RE = re.compile(r"[a-z]\|[a-z]")

# Above this share of boundaries the candidate is prose that has been gridded,
# not a table. Set between the two measured distributions: ~2x the known-good
# 99th percentile, and far below the shattered mass.
SHATTER_MAX = 0.12

# ...but a rate alone convicts a small table on a single accident. A legitimate
# 3-row table on VB_ASDIS_Protocol_2024 p5 scored 0.167 on ONE boundary,
# "Connect back sensor wire|a) Observe ...", where a complete word simply meets a
# list marker. Genuine shattering is never that thrifty — the gridded prose on
# the same page produces dozens — so require a count as well as a rate.
SHATTER_MIN_HITS = 3


def _cells(row):
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _md_cells(row):
    """Cells of a markdown row with their positions intact.

    _cells strips EVERY leading pipe, so "|||4|Check the fasteners" reads as
    ['4', 'Check the fasteners'] and the two empty cells in front of it vanish.
    That is harmless wherever only the SET of values matters (a full-width banner
    row), but a vertically merged column is identified BY its empty cells, so the
    column-group pass needs true indices.
    """
    r = row.strip()
    if r.startswith("|"):
        r = r[1:]
    if r.endswith("|"):
        r = r[:-1]
    return [c.strip() for c in r.split("|")]


def _plain(cell):
    return re.sub(r"\*+", "", cell).strip()


def _flat(s):
    return re.sub(r"[\s|*_`]+", "", s).lower()


def _named(cell):
    """True when a header cell holds content PyMuPDF managed to attribute."""
    c = _plain(cell)
    return bool(c) and not _COLN_CELL.match(c)


def _looks_like_label(cell):
    """True when a header cell reads like a column label rather than prose.

    Being non-empty is not enough. The "text" strategy will lay a grid over an
    ordinary prose page and report the first line of the paragraph as the header,
    split mid-word: "|Axle speed of|rotation is|measured and|evaluated se|parately
    within|a sp|ee|". Every one of those cells is "named", so a naive count rates
    that page-grid as highly as a real "|Connector|Board type|Function|" header.
    Labels are short and start with a capital or a digit; prose fragments carved
    out of the middle of a sentence do not.
    """
    c = _plain(cell)
    if not c or _COLN_CELL.match(c) or len(c) > 40:
        return False
    return c[0].isupper() or c[0].isdigit()


def _page_lines(d):
    """(bbox, text) for every text line on the page."""
    out = []
    for block in d.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            t = _line_text(line)
            if t:
                out.append((line.get("bbox", block.get("bbox")), t))
    return out


def _clipped(bbox, lines, repeated):
    """Text lines this box cuts off: vertically inside it, horizontally outside.

    This is the signal that a strategy has mis-bounded the table, and it is the
    one that matters most, because a clipped column is data leaving the table
    altogether. On the shop-schedule report's electrical pages the "text"
    strategy boxes the table at x>=190, so the S.No. and Equipment/Sub-Assy.
    columns fall outside it — and heading detection then re-reads those bold
    labels as section titles, which is how 68 chunks came to be filed under
    "Equipment/" and 67 under "S.No".
    """
    x0, y0, x1, y1 = bbox
    n = 0
    for (bx0, by0, bx1, by1), t in lines:
        if t in repeated:
            continue
        if y0 <= (by0 + by1) / 2 <= y1 and not x0 <= (bx0 + bx1) / 2 <= x1:
            n += 1
    return n


def _swallowed(bbox, lines, repeated):
    """Running header/footer lines this box has absorbed as table rows.

    A table whose first row is the page's running title has no column labels at
    all — "|ON SH|OP S|CHEDULE ACTI|VI|TIES FOR|VANDE BHA|RAT TRAINSET|" is what
    _split_table then repeats at the top of every piece of that table.
    """
    x0, y0, x1, y1 = bbox
    n = 0
    for (bx0, by0, bx1, by1), t in lines:
        if t not in repeated:
            continue
        if y0 <= (by0 + by1) / 2 <= y1 and x0 <= (bx0 + bx1) / 2 <= x1:
            n += 1
    return n


def _covered(bbox, lines, repeated):
    """Content lines this box actually contains."""
    x0, y0, x1, y1 = bbox
    return sum(1 for (bx0, by0, bx1, by1), t in lines
               if t not in repeated
               and y0 <= (by0 + by1) / 2 <= y1 and x0 <= (bx0 + bx1) / 2 <= x1)


def _shatter_rate(md):
    """Share of this table's cell boundaries that cut a word in half.

    A rate, not a count, because a long table would otherwise look worse than a
    short one purely for having more rows.
    """
    rows = [r for r in md.splitlines() if r.strip().startswith("|")]
    boundaries = sum(max(0, len(_cells(r)) - 1) for r in rows)
    if boundaries < 4:
        return 0.0
    return len(_WORD_SPLIT_RE.findall(md)) / boundaries


def _is_shattered(tb):
    """True when this candidate is a grid laid over prose rather than a table.

    _find_tables only ever compares strategies against EACH OTHER, so it has no
    way to reject a page that is not tabular at all: where "lines_strict" and
    "lines" find nothing they simply `continue`, and "text" wins by default. On a
    5-document sample "text" was the only candidate on 129 pages and 103 of those
    were shattered prose — an RDSO letter's "refurbishment schedule (36+3|months
    or| / |12 Lakh kilom|eter" among them, which cost that value its eval case.

    Every other criterion here rewards this failure: a prose grid clips nothing,
    swallows nothing, and its header cells are all "named", so it scores a
    flawless zero on the primary term. Word-splitting is the one signal a
    strategy cannot earn by finding LESS, which is what sank the clipping and
    coverage criteria when they were tried as primaries.
    """
    try:
        md = tb.to_markdown()
    except Exception:
        return False
    if len(_WORD_SPLIT_RE.findall(md)) < SHATTER_MIN_HITS:
        return False
    return _shatter_rate(md) >= SHATTER_MAX


def _table_measure(tb, lines, repeated):
    """(labelled_coverage, clipped, swallowed, unnamed, columns) for a candidate.

    Three ways a table can look better-extracted than it is, all found by
    measuring rather than reasoning, and all the same mistake — treating an
    ABSENCE of evidence as evidence of quality:

    1. The real labels of a two-level head sit in the first BODY row, so a
       candidate judged on its header row alone is judged on group names full of
       holes. That row is admitted as a header candidate — but only when it reads
       as labels, or any data row free of ColN would certify the table as named.
    2. Scoring the fewer-ColN of the two candidates let an EMPTY row
       ("||||||||||||" — no ColN because no content) certify a table as perfect.
       That is how p243's page-title-as-header extraction outscored the one
       holding the real SS-1/SS-2/SS-3 labels. Score the better-LABELLED instead.
    3. A header with no labels at all likewise scores zero ColN and looks
       flawless, which is how "text" won on Vol1's Foreword, Preface and Contents
       and turned prose and a dotted table of contents into table chunks. It gets
       an explicit penalty.

    ColN count otherwise stays the measure of unnamed columns. Counting every
    unlabelled cell instead was measured corpus-wide and came out worse (ColN
    1548 -> 1721): _repair_header legitimately leaves holes empty once it has
    filled what it can, so that rule punished the repaired headers hardest.

    Coverage is weighted by header quality, because content captured under
    columns that name nothing is barely captured at all.
    """
    try:
        md = tb.to_markdown()
    except Exception:
        return (0, 10_000, 10_000, 10_000, 10_000)
    rows = md.splitlines()
    head = [rows[0] if rows else ""]
    if len(rows) > 2 and (_is_label_row(rows[2]) or _header_quality(rows[2]) >= 0.6):
        head.append(rows[2])            # rows[1] is the |---| separator
    best = max(head, key=_header_quality)
    quality = _header_quality(best)
    unnamed = (len(_COLN_RE.findall(best + "|"))
               + (len(_cells(best)) if quality == 0 else 0))
    return (_covered(tb.bbox, lines, repeated) * quality,
            _clipped(tb.bbox, lines, repeated),
            _swallowed(tb.bbox, lines, repeated),
            unnamed, tb.col_count)


def _find_tables(page, lines, repeated):
    """Tables on `page`, extracted with whichever strategy keeps most structure.

    Scored on content kept minus damage done, rather than on unnamed ColN header
    cells alone. The old rule picked the wrong strategy on exactly the pages that
    matter: on p243 "text" scores fewer ColN than "lines_strict" and yet loses
    two whole columns off the left edge and makes the page's running title its
    header row.

    Order arrived at by measurement, not taste. Column naming stays the PRIMARY
    criterion, as it always was; the new geometric signals are tie-breakers.
    Ranking clipping above naming was measured across all 97 documents and made
    95 of them worse (ColN +39, unusable headers +60) while helping only the
    report it was designed for — because "text" will lay a grid over an entire
    prose page, clip nothing, and so beat a correctly-read
    "|Connector|Board type|Function|".

    What actually fixed p243 was not a new criterion but two defects in the old
    one: _COLN_RE could not count adjacent placeholders, and the first body row
    was never considered even though PyMuPDF puts the real labels there. With
    those corrected the original rule picks the right strategy on its own.
    """
    best, best_score = [], None
    for strategy in _TABLE_STRATEGIES:
        try:
            tables = list(page.find_tables(strategy=strategy).tables)
        except Exception:
            continue
        tables = [t for t in tables if not _is_shattered(t)]
        if not tables:
            continue
        cov, clip, swal, unnamed, cols = (
            sum(m) for m in zip(*(_table_measure(t, lines, repeated) for t in tables)))
        score = (unnamed, clip, swal, -cov, cols)
        if best_score is None or score < best_score:
            best, best_score = tables, score
        if clip == swal == unnamed == 0:
            break                      # nothing clipped or swallowed, all named
    return best


# ---- header repair ----------------------------------------------------------
def _is_label_row(row):
    """A row of column labels rather than data: short cells, mostly bold."""
    cells = [c for c in _cells(row) if _plain(c)]
    if not cells or max(len(_plain(c)) for c in cells) > 60:
        return False
    bold = sum(1 for c in cells if c.startswith("**"))
    return bold >= max(1, len(cells) // 2)


def _is_running_row(row, repeated):
    """A row that is a running header/footer shattered across the columns."""
    named = [_plain(c) for c in _cells(row) if _named(c)]
    joined = _flat("".join(named))
    if len(joined) < 12:
        return False
    return any(len(_flat(t)) >= 12 and (joined in _flat(t) or _flat(t) in joined)
               for t in repeated)


def _header_quality(row):
    """Fraction of a header row's cells that read as column labels."""
    cells = _cells(row) if row else []
    return sum(map(_looks_like_label, cells)) / len(cells) if cells else 0.0


def _dup(a, b):
    """True when `b` is `a`'s label repeated rather than a second, distinct label.

    Length-guarded, because the single-letter schedule columns T/M/Q are
    substrings of almost anything: an unguarded test found "T" inside
    "Maintenance Periodicity" and deleted the T column's label, leaving every
    tick in that column filed under the group heading instead. On this table a
    mislabelled column is a wrong periodicity, so the guard is load-bearing.
    """
    fa, fb = _flat(a), _flat(b)
    return bool(fa) and len(fb) >= 3 and fb in fa


# A merged, full-width row is rendered by PyMuPDF as its value repeated in every
# column. Collapsed rows are marked so chunker._split_table can recognise them;
# the marker is a character normalize_symbols never emits.
GROUP_MARK = "▸"


def _group_label(row):
    """The label of a full-width spanning row, or "".

    "1. Line & Traction Converter (MEDHA)- MC1,2" arrives twelve times over, once
    per column. That row is a heading INSIDE the table — the equipment whose
    activities the rows beneath it list — and across the report's ~100 electrical
    pages it is the only place that equipment is named: pages 239-245 are all
    activities of item 1, with the name printed once on page 238.
    """
    cells = [_plain(c) for c in _cells(row)]
    vals = {c for c in cells if c}
    if len(cells) < 2 or len(vals) != 1:
        return ""
    v = re.sub(r"\s+", " ", re.sub(r"\s*<br>\s*", " ", vals.pop())).strip()
    return v if 3 <= len(v) <= 140 and sum(c.isalpha() for c in v) >= 3 else ""


_EQUIP_COL = re.compile(r"equipment|sub-?\s*assy|sub-?assembly", re.I)


def _column_group_index(header):
    """Index of the column naming the equipment a run of rows describes, or None."""
    if not header:
        return None
    for i, c in enumerate(_md_cells(header)):
        if _EQUIP_COL.search(re.sub(r"\s*<br>\s*", " ", _plain(c))):
            return i
    return None


def _group_value(cell):
    """The equipment name held in a group-carrying cell, or "".

    Stricter than a non-empty test on purpose: the same column also receives
    wrapped prose ("_Note:_ _For replacement criteria, instruction..._"), and on a
    page whose header was clipped it receives the column label itself.
    """
    v = re.sub(r"\s+", " ", re.sub(r"\s*<br>\s*", " ", _plain(cell))).strip()
    if not (3 <= len(v) <= 140) or sum(c.isalpha() for c in v) < 3:
        return ""
    if v.startswith("_") or v.lower().startswith("note") or len(v.split()) > 10:
        return ""
    if _EQUIP_COL.search(v) and len(v.split()) <= 4:
        return ""          # the header row repeated as data
    return v


def _mark_column_groups(header, body, mark):
    """Mark the runs of a vertically merged equipment column as group headings.

    _group_label already handles the electrical tables, which name their
    equipment in a full-width banner row. The mechanical schedule instead names
    it in the "Equipment / Sub-Assy." column, merged vertically across every
    activity of that equipment: printed once on whichever page the run starts and
    blank on every row after. Measured over this corpus, 80 of the 195 chunks
    carrying that column hold NO equipment value at all, so they fall back to the
    page heading — which is why all 67 chunks of the mechanical schedule are
    titled "MAINTENANCE SCHEDULE ACTIVITIES FOR MECHANICAL EQUIPMENT". That title
    shares no word with "stabilizer link fastener torque", so rag.py's
    title-overlap multiplier can never fire for a query naming a component.

    Emitting the run's name as a group row lets the existing machinery do the
    rest: _table_markdown carries it onto continuation pages and chunker
    restates it atop every piece and titles the chunk with it.
    """
    idx = _column_group_index(header)
    if idx is None:
        return body
    out, active, emitted = [], "", 0
    for row in body:
        if _marked_label(row):
            active = ""          # a full-width banner supersedes the column
            out.append(row)
            continue
        cells = _md_cells(row)
        val = _group_value(cells[idx]) if idx < len(cells) else ""
        if val and val != active:
            active = val
            out.append(mark(val))
            emitted += 1
        out.append(row)
    # A column naming something fresh on most of its rows is data, not a
    # grouping — emitting a heading per row would retitle every chunk after
    # whichever row it happened to begin on. Fall back rather than guess.
    return out if emitted <= max(1, len(body) // 3) else body


def _marked_label(row):
    """The label of a row already collapsed by _table_markdown."""
    return row[3:].split("|")[0].strip() if row.startswith(f"|{GROUP_MARK} ") else ""


def _labels(header):
    return {_flat(c) for c in _cells(header) if _named(c)} - {""}


def _same_table(h1, h2):
    """Whether two pages' header rows describe the same continuing table.

    Exact equality is too strict — PyMuPDF reads the SAME matrix as 12 columns on
    p238, 16 on p240 and 14 on p244, because a row with more wrapped cells splits
    differently. Shared column labels are the stable part. This gate is what lets
    a group heading carry onto continuation pages without letting it leak onto an
    unrelated table that merely happens to follow.
    """
    a, b = _labels(h1), _labels(h2)
    if not a or not b:
        return False
    return len(a & b) >= 3 or len(a & b) >= 0.5 * min(len(a), len(b))


def _repair_header(header, body):
    """Give the table one header row that names its own columns.

    PyMuPDF reports a two-level head as two rows: the group names ("Maintenance
    Periodicity") on the header row with ColN holes beneath them, and the leaf
    labels ("T | M | Q | 9 M | SS1 | SS2 | SS3") as the FIRST BODY ROW. Left
    alone, the SS-1/SS-2/SS-3 identity sits in a row that chunker._split_table
    treats as data — so it is not repeated on the continuation pieces of a long
    table, and every piece after the first loses the column meaning entirely.
    That is the same information the Wingdings ticks encode, lost one stage later.
    """
    if not body or not _is_label_row(body[0]):
        return header, body
    fc = _cells(body[0])
    hc = _cells(header) if header else [""] * len(fc)
    # Only merge when the header is visibly the poorer of the two, so a table
    # whose first data row merely happens to be bold keeps its real header.
    if len(hc) != len(fc) or sum(map(_named, fc)) <= sum(map(_named, hc)):
        return header, body
    merged = []
    for h, f in zip(hc, fc):
        h, f = _plain(h), _plain(f)
        if not _named(h) or _dup(f, h):
            merged.append(f)
        elif not f or _dup(h, f):
            merged.append(h)
        else:
            merged.append(f"{h} {f}")
    return "|" + "|".join(merged) + "|", body[1:]


def _table_markdown(tb, repeated, carried, page_no, groups):
    """Table -> markdown with a usable header row and its group headings marked.

    `carried` maps column count -> (header, page) for the last well-named header
    seen, so the continuation pages of a table that runs for 47 pages keep the
    labels printed once on its first page. `groups` holds the equivalent state
    for the in-table equipment heading. Both are restricted to the immediately
    preceding page: that is what makes it a continuation rather than a guess.
    """
    try:
        md = normalize_symbols(tb.to_markdown().strip())
    except Exception:
        return ""
    rows = md.splitlines()
    if len(rows) < 3:
        return md
    sep = rows[1]
    header = "" if _is_running_row(rows[0], repeated) else rows[0]
    body = [r for r in rows[2:] if not _is_running_row(r, repeated)]
    header, body = _repair_header(header, body)
    if not body:
        return ""

    ncols = len(_cells(header or body[0]))
    if _header_quality(header) >= 0.5:
        carried[ncols] = (header, page_no)
    else:
        prev, prev_page = carried.get(ncols, ("", -9))
        if prev and page_no - prev_page <= 1:
            header = prev
            carried[ncols] = (prev, page_no)

    # collapse spanning rows: twelve copies of an equipment name cost chunk
    # budget and read as data; one marked row reads as the heading it is
    def mark(label):
        return f"|{GROUP_MARK} {label}|" + "|" * (ncols - 1)

    body = [mark(g) if (g := _group_label(r)) else r for r in body]
    body = _mark_column_groups(header, body, mark)

    # A table continuing onto the next page inherits the group heading in force,
    # gated on the header describing the same table: the equipment is named once
    # on p238 and its activities run to p245, so without this every page but the
    # first is an unattributed list of checks.
    prev_label, prev_page, prev_header = groups.get("state", ("", -9, ""))
    if prev_label and page_no - prev_page <= 1 and not _marked_label(body[0]) \
            and _same_table(header, prev_header):
        body.insert(0, mark(prev_label))
    last = next((lbl for r in reversed(body) if (lbl := _marked_label(r))), "")
    if last:
        groups["state"] = (last, page_no, header)
    return "\n".join(([header, sep] if header else []) + body)


# Column labels are not section headings. They are bold and short, so the
# bold-line heading rule reads them as headings on any page whose table box has
# clipped them — which is how "Equipment/", "S.No" and "Maintenance Periodicity"
# became the three most common section titles in a 359-page report. The bounding
# fix above removes the cause; this keeps one bad page from inventing a section.
# Repeated, so a slash-joined pair of labels ("Remark/ Reference") is recognised
# as readily as either half — that pair alone titled 45 chunks.
_COLUMN_LABEL = re.compile(
    r"^(?:(?:s\.?\s*no|sr\.?\s*no|equipment|sub-?\s*assy|activit(?:y|ies)|"
    r"maintenance\s+periodicity|periodicity|remarks?|references?|ref\.?|"
    r"description|specifications?|[tmq]|9\s*m|ss-?[1-4]|col\d+)[\s./:-]*)+$", re.I)

# Page footers vary per page ("Page 241 of 359"), so _collect_repeated_lines can
# never match them verbatim — they were surviving as the first text block of
# most sections in this report.
_PAGE_FOOTER = re.compile(r"^\s*(page\s+)?\d+\s*(of|/)\s*\d+\s*$", re.I)


def _in_any_rect(bbox, rects):
    cx = (bbox[0] + bbox[2]) / 2
    cy = (bbox[1] + bbox[3]) / 2
    return any(r[0] <= cx <= r[2] and r[1] <= cy <= r[3] for r in rects)


def _ocr_cache_path(doc_id, page_no):
    return os.path.join(OCR_CACHE_DIR, doc_id, f"p{page_no:03d}.txt")


def _ocr_attempted(doc_id, page_no):
    """True once ocr_gemini has processed this page — including when it came back
    [UNREADABLE] and cached an empty marker. Distinct from _ocr_text_for returning
    None, which conflates 'never OCR'd' with 'OCR found nothing readable'; without
    the distinction a photo-only page is reported as a missing-OCR gap on every
    build, forever."""
    return os.path.exists(_ocr_cache_path(doc_id, page_no))


def _ocr_text_for(doc_id, page_no):
    path = _ocr_cache_path(doc_id, page_no)
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

# ...but only short ones. doc_type does not separate a 2-page SMI letter from the
# 90-page En-route Trouble Shooting manual (VB/SMI/E/18), which carries the same
# type. That manual's heading detection finds 75 real sections — "Isolation
# procedure for Parking Brake", "…for Majority BP drop", "…for BP Low pressure" —
# and those are precisely the titles a technician's query overlaps with. Page
# count is what actually separates the two shapes: RDSO/ICF letters run 1-10
# pages, the manual-like SMIs 28/41/90.
LETTER_MAX_PAGES = 12


def _retitle_letter_sections(sections, entry, n_pages):
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
    if (entry.get("doc_type") not in LETTER_DOC_TYPES
            or not sections or n_pages > LETTER_MAX_PAGES):
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
                           "ocr_merged": used_ocr, "suspect_layer": True,
                           "ocr_attempted": _ocr_attempted(entry["doc_id"], page_no)})
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
    carried = {}                      # column count -> (header row, page) for continuations
    groups = {}                       # last in-table group heading -> (label, page, header)

    for pno in range(n_pages):
        page = doc[pno]
        page_no = pno + 1
        d = page_dicts[pno]

        raw_lines = _page_lines(d)
        table_rects, table_blocks = [], []
        for t_idx, tb in enumerate(_find_tables(page, raw_lines, repeated)):
            md = _table_markdown(tb, repeated, carried, page_no, groups)
            if md and md.count("|") >= 4:
                table_rects.append(tuple(tb.bbox))
                table_blocks.append({"type": "table", "text": md, "page": page_no,
                                     "y": tb.bbox[1], "table_index": t_idx})

        # text lines outside table regions, in reading order
        line_items = []
        for block in d.get("blocks", []):
            if block.get("type", 0) != 0:
                continue
            for line in block.get("lines", []):
                t = _line_text(line)
                if not t or t in repeated or _PAGE_FOOTER.match(t):
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

        # Lines and tables are walked together in page order so that a table
        # lands in the section whose heading stands ABOVE it. Appending tables
        # after the loop instead bound every table to whichever heading happened
        # to be open at the END of the page — which on a page that opens a new
        # section below its table filed that table under the wrong equipment.
        events = [(round(li["y"], 1), 0, li) for li in (line_items if use_native else [])]
        events += [(round(tb["y"], 1), 1, tb) for tb in table_blocks]
        events.sort(key=lambda e: (e[0], e[1]))

        for _y, kind, item in events:
            if kind == 1:
                flush_buf()
                current["blocks"].append({"type": "table", "text": item["text"],
                                          "page": page_no,
                                          "table_index": item["table_index"]})
                continue
            li = item
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
            if is_heading and _COLUMN_LABEL.match(title):
                is_heading = False     # a clipped column label, not a section
            if is_heading:
                flush_buf()
                if current["blocks"]:
                    sections.append(current)
                current = {"section": title, "section_num": sec_num,
                           "page_start": page_no, "blocks": []}
            else:
                buf.append(t)
        flush_buf()

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
                           "ocr_merged": ocr_merged, "suspect_layer": suspect,
                           "ocr_attempted": _ocr_attempted(doc_id, page_no)})

    if current["blocks"]:
        sections.append(current)
    doc.close()

    # slide decks / circulars may not produce headings; fall back to per-page sections
    if len(sections) < 3 and n_pages > 3:
        sections = _per_page_sections(path, entry, repeated)
    return _retitle_letter_sections(sections, entry, n_pages), page_stats


def _per_page_sections(path, entry, repeated):
    """Fallback: one section per page, titled by the page's first short line.

    Tables are extracted here too. This path is reached whenever heading
    detection finds fewer than three sections, and it used to emit text blocks
    only — so a document that tripped the fallback lost EVERY table it had,
    silently. VB_SMI_CPA_RMPU_2024 lost all 12 the moment the column-label guard
    stopped a handful of table labels from being miscounted as headings: the
    document did not change, the number of spurious headings did.
    """
    doc = fitz.open(path)
    sections = []
    carried, groups = {}, {}
    for pno in range(len(doc)):
        page_no = pno + 1
        page = doc[pno]
        raw_lines = _page_lines(page.get_text("dict"))
        table_rects, table_blocks = [], []
        for t_idx, tb in enumerate(_find_tables(page, raw_lines, repeated)):
            md = _table_markdown(tb, repeated, carried, page_no, groups)
            if md and md.count("|") >= 4:
                table_rects.append(tuple(tb.bbox))
                table_blocks.append({"type": "table", "text": md, "page": page_no,
                                     "table_index": t_idx})
        lines = [t.strip() for bbox, t in raw_lines
                 if t.strip() and t.strip() not in repeated
                 and not _PAGE_FOOTER.match(t.strip())
                 and not _in_any_rect(bbox, table_rects)]
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
        blocks.extend(table_blocks)
        if ocr and len(text) < WEAK_TEXT_CHARS:
            blocks.append({"type": "text", "text": ocr, "page": page_no})
        if blocks:
            sections.append({"section": title, "section_num": "",
                             "page_start": page_no, "blocks": blocks})
    doc.close()
    return sections
