"""
chunker.py — section-aware chunking that emits the schema the backend consumes
(see backend/data/chunks_merged.jsonl): the original 14 keys plus routing/
provenance keys (coach_type, subsystem, issue_date, revision, letter_no) carried
from the registry entry. All keys are read defensively in the backend, so older
committed chunks that lack the new keys keep working.

Text: packed into chunks of ~900-1200 chars (hard max 1600) with ~150-char
sentence overlap inside a section. Tables: never split mid-row; the markdown
header row is repeated in every piece of a large table so each fault-code row
keeps its column labels. Sections under 250 chars merge into the next section.
"""
import hashlib
import re

TARGET_LO = 900
TARGET_HI = 1200
HARD_MAX = 1600
OVERLAP_CHARS = 150
TABLE_MAX = 2500
MIN_SECTION_CHARS = 250
MAX_HEADER_CHARS = 600    # per header line, repeated on every piece of a table

_SENT_SPLIT = re.compile(r"(?<=[.!?।])\s+|\n+")


def _sentences(text):
    parts = [p.strip() for p in _SENT_SPLIT.split(text) if p and p.strip()]
    out = []
    for p in parts:  # never let a single monster "sentence" exceed HARD_MAX
        while len(p) > HARD_MAX:
            out.append(p[:HARD_MAX])
            p = p[HARD_MAX:]
        out.append(p)
    return out


def _title_block(sec):
    """The dissolved section's title, kept as text so its words survive.

    A section shorter than MIN_SECTION_CHARS loses its own heading when it is
    absorbed, and on a "MUST CHANGE ITEMS FOR SHOP SCHEDULE-2" page that heading
    is the only place the equipment is named: BOGIE, CTRB and Rubber Metal Bonded
    Items were each a ~40-char section holding a bare list, so all three names
    were deleted and their sub-items left orphaned under "1. Gangway". The title
    is worth more than the blocks it introduced.
    """
    title = re.sub(r"\s+", " ", sec.get("section") or "").strip()
    if not title or title.lower() in ("introduction", "general"):
        return []
    num = (sec.get("section_num") or "").strip()
    label = f"{num} {title}".strip() if num else title
    page = sec["blocks"][0]["page"] if sec["blocks"] else sec.get("page_start")
    return [{"type": "text", "text": f"{label}:", "page": page}]


def merge_tiny_sections(sections):
    merged = []
    pending = []  # blocks from tiny sections awaiting a host
    for sec in sections:
        chars = sum(len(b["text"]) for b in sec["blocks"])
        if chars < MIN_SECTION_CHARS:
            pending.extend(_title_block(sec) + sec["blocks"])
            continue
        if pending:
            sec = dict(sec, blocks=pending + sec["blocks"])
            pending = []
        merged.append(sec)
    if pending:
        if merged:
            merged[-1]["blocks"].extend(pending)
        else:
            merged.append({"section": "General", "section_num": "",
                           "page_start": pending[0]["page"], "blocks": pending})
    return merged


def _pack_text(blocks):
    """Pack text blocks into (text, page) pieces with sentence overlap."""
    pieces = []
    cur, cur_page = [], None
    cur_len = 0
    for b in blocks:
        for s in _sentences(b["text"]):
            if cur_len + len(s) + 1 > (TARGET_HI if cur_len >= TARGET_LO else HARD_MAX):
                if cur:
                    pieces.append((" ".join(cur), cur_page))
                    # overlap: carry trailing sentences up to OVERLAP_CHARS
                    keep, keep_len = [], 0
                    for t in reversed(cur):
                        if keep_len + len(t) > OVERLAP_CHARS:
                            break
                        keep.insert(0, t)
                        keep_len += len(t)
                    cur, cur_len = keep, keep_len
                    cur_page = b["page"]
            if cur_page is None:
                cur_page = b["page"]
            cur.append(s)
            cur_len += len(s) + 1
    if cur and cur_len > 40:
        pieces.append((" ".join(cur), cur_page))
    return pieces


def _split_row(row, budget):
    """A single row too large for `budget` -> pieces split on cell boundaries.

    Row-boundary splitting alone is not enough: a PDF table whose cells hold whole
    paragraphs can produce one row of ~9,000 chars, and four of those became a
    single 36,494-char chunk. That chunk broke three things at once — it made the
    embedding request oversized (persistent 429s), it exceeded rag.CTX_CHUNK_CHARS
    so ~93% of it could never reach the LLM even when retrieved, and one vector
    spanning 36k chars matches weakly on everything and precisely on nothing.
    Splitting mid-row loses column alignment for that row, which is the lesser
    evil against content that is unreachable by construction.

    `budget` is floored because a non-positive one is an infinite loop: c[:budget]
    with a negative budget returns a string that never shrinks to zero, so the
    while below appends forever until the process dies of MemoryError. That is
    reachable whenever a table's header row is wider than TABLE_MAX — rare, but
    it took out VB_CPA_VCD_Foot_Switch_Removal once repaired headers made header
    rows longer."""
    budget = max(budget, 200)
    cells = row.split("|")
    pieces, cur = [], []
    cur_len = 0
    for c in cells:
        if cur_len + len(c) + 1 > budget and cur:
            pieces.append("|".join(cur))
            cur, cur_len = [], 0
        # a single cell over budget still has to be cut somewhere
        while len(c) > budget:
            pieces.append(c[:budget])
            c = c[budget:]
        cur.append(c)
        cur_len += len(c) + 1
    if cur:
        pieces.append("|".join(cur))
    return [p for p in pieces if p.strip(" |")]


_GROUP_ROW = re.compile(r"^\|\s*▸\s*([^|]{3,140}?)\s*\|")


def _split_table(md, section):
    """Table -> [(chunk text, group label)], header repeated, never mid-row unless
    a single row exceeds TABLE_MAX on its own.

    A group row — a merged full-width cell naming the equipment whose activities
    follow, see parse_pdf._group_label — is repeated at the top of every piece the
    same way the header row is, and reported so the caller can title the chunk
    with it. Without that, only the first piece of a 47-page table knows its rows
    belong to the Line & Traction Converter; every later piece is an
    unattributed list of checks whose section title is whatever generic heading
    was open ("General (Applicable to all Schedules)", 153 chunks of one report).
    """
    lead = f"Table — {section}:\n"
    lines = md.splitlines()
    header = lines[:2] if len(lines) >= 2 and set(lines[1]) <= set("|-: ") else lines[:1]
    body = lines[len(header):]
    # A header repeated on every piece has to leave room for rows on every piece.
    # Past this width it is a wall of merged cells that crowds out the data it is
    # meant to label, and beyond TABLE_MAX it made the row budget negative.
    header = [l[:MAX_HEADER_CHARS] for l in header]

    def first_group(rows):
        return next((m.group(1).strip() for r in rows
                     if (m := _GROUP_ROW.match(r))), "")

    if len(md) + len(lead) <= TABLE_MAX:
        return [(lead + md, first_group(body))]

    head_len = sum(len(l) + 1 for l in header) + len(lead)
    pieces, cur = [], []
    cur_len = 0
    active = ""       # group heading in force at this point in the table
    opened = ""       # group heading to restate at the top of the current piece

    def group_row(label):
        return f"|▸ {label}|"

    def emit():
        nonlocal cur, cur_len, opened
        if any(not _GROUP_ROW.match(r) for r in cur):
            restate = [group_row(opened)] if opened and not _GROUP_ROW.match(cur[0]) else []
            pieces.append((lead + "\n".join(header + restate + cur),
                           opened or first_group(cur)))
        cur, cur_len = [], 0
        opened = active

    for row in body:
        extra = len(group_row(opened)) + 1 if opened else 0
        if head_len + len(row) + 1 > TABLE_MAX:
            emit()                                    # oversized row stands alone
            for frag in _split_row(row, TABLE_MAX - head_len):
                pieces.append((lead + "\n".join(header + [frag]), active))
            continue
        if head_len + extra + cur_len + len(row) + 1 > TABLE_MAX and cur_len:
            emit()
        if m := _GROUP_ROW.match(row):
            active = m.group(1).strip()
            if not cur:
                opened = active
        cur.append(row)
        cur_len += len(row) + 1
    emit()
    return pieces


def _columns_of(text):
    """The chunk's column labels, from its repeated markdown header row."""
    for line in text.splitlines():
        if not line.startswith("|") or _GROUP_ROW.match(line) or line.startswith("Table —"):
            continue
        cells = [re.sub(r"\s*<br>\s*", " ", c).strip(" *")
                 for c in line.strip().strip("|").split("|")]
        return [c for c in cells if c]
    return []


def chunk_document(sections, entry, tagger):
    """sections -> list of chunk dicts in the backend schema."""
    sections = merge_tiny_sections(sections)
    chunks = []
    seen_texts = set()  # repeated slides/pages produce byte-identical pieces
    for sec in sections:
        sec_title = re.sub(r"\s+", " ", sec["section"]).strip()[:120]
        pieces = []  # (text, page, group, table_id)
        text_blocks = [b for b in sec["blocks"] if b["type"] == "text"]
        table_blocks = [b for b in sec["blocks"] if b["type"] == "table"]
        pieces.extend((t, p, "", "") for t, p in _pack_text(text_blocks))
        for tb in table_blocks:
            tid = f"{entry['doc_id']}:p{tb['page']}:t{tb.get('table_index', 0)}"
            for t, grp in _split_table(tb["text"], sec_title):
                pieces.append((t, tb["page"], grp, tid))
        deduped = []
        for piece in pieces:
            key = piece[0].strip()
            if key and key not in seen_texts:
                seen_texts.add(key)
                deduped.append(piece)
        pieces = deduped

        total = len(pieces)
        for idx, (text, page, grp, tid) in enumerate(pieces):
            text = text.strip()
            if not text:
                continue
            # An equipment name from inside the table REPLACES the heading that
            # was open on the page. Section title feeds both the keyword index
            # and rag.py's title-overlap multiplier (1 + 0.15 per shared word,
            # uncapped), so "1. Line & Traction Converter (MEDHA)- MC1,2" earns a
            # boost that "General (Applicable to all Schedules)" cannot — and
            # keeping the page heading as well would push that same generic
            # phrase into 400+ chunks of one document, amplifying the boilerplate
            # this codebase already treats as a retrieval handicap.
            chunk_section = grp[:120] if grp else sec_title
            tags, oem = tagger(text, chunk_section, entry)
            cid = hashlib.md5(
                f"{entry['doc_id']}|{chunk_section}|{idx}|{text}".encode("utf-8")
            ).hexdigest()[:12]
            chunks.append({
                "chunk_id": cid,
                "doc_id": entry["doc_id"],
                "doc_type": entry["doc_type"],
                "title": entry["title"],
                "source": entry["source"],
                "section": chunk_section,
                "section_num": sec.get("section_num", ""),
                "page_num": page if page is not None else sec["page_start"],
                "chunk_index": idx,
                "total_chunks_in_section": total,
                "tags": tags,
                "oem": oem,
                # structure (see _split_table): lets retrieval and answering tell
                # a table from prose, group the pieces of one physical table back
                # together, and see which columns a row's values sit under
                "chunk_type": "table" if tid else "text",
                "table_id": tid,
                "columns": _columns_of(text) if tid else [],
                # routing + provenance (see doc_registry) — used by retrieval
                # routing, supersession/recency, and clause-level citation
                "coach_type": entry.get("coach_type", []),
                "subsystem": entry.get("subsystem", ""),
                "issue_date": entry.get("issue_date", ""),
                "revision": entry.get("revision", ""),
                "letter_no": entry.get("letter_no", ""),
                # link to the source PDF (empty when no bucket configured) — used
                # by rag.build_sources to render clickable, page-deep citations
                "download_url": entry.get("download_url", ""),
                "text": text,
                "char_count": len(text),
            })
    return chunks
