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


def merge_tiny_sections(sections):
    merged = []
    pending = []  # blocks from tiny sections awaiting a host
    for sec in sections:
        chars = sum(len(b["text"]) for b in sec["blocks"])
        if chars < MIN_SECTION_CHARS:
            pending.extend(sec["blocks"])
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
    evil against content that is unreachable by construction."""
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


def _split_table(md, section):
    """Table -> one or more chunk texts, header repeated, never mid-row unless a
    single row exceeds TABLE_MAX on its own."""
    lead = f"Table — {section}:\n"
    if len(md) + len(lead) <= TABLE_MAX:
        return [lead + md]
    lines = md.splitlines()
    header = lines[:2] if len(lines) >= 2 and set(lines[1]) <= set("|-: ") else lines[:1]
    head_len = sum(len(l) + 1 for l in header) + len(lead)
    body = lines[len(header):]
    pieces, cur = [], list(header)
    cur_len = head_len

    def flush():
        nonlocal cur, cur_len
        if len(cur) > len(header):
            pieces.append(lead + "\n".join(cur))
        cur, cur_len = list(header), head_len

    for row in body:
        if head_len + len(row) + 1 > TABLE_MAX:
            flush()                                   # oversized row stands alone
            for frag in _split_row(row, TABLE_MAX - head_len):
                pieces.append(lead + "\n".join(header + [frag]))
            continue
        if cur_len + len(row) + 1 > TABLE_MAX and len(cur) > len(header):
            flush()
        cur.append(row)
        cur_len += len(row) + 1
    flush()
    return pieces


def chunk_document(sections, entry, tagger):
    """sections -> list of chunk dicts in the backend schema."""
    sections = merge_tiny_sections(sections)
    chunks = []
    seen_texts = set()  # repeated slides/pages produce byte-identical pieces
    for sec in sections:
        sec_title = re.sub(r"\s+", " ", sec["section"]).strip()[:120]
        pieces = []  # (text, page)
        text_blocks = [b for b in sec["blocks"] if b["type"] == "text"]
        table_blocks = [b for b in sec["blocks"] if b["type"] == "table"]
        pieces.extend(_pack_text(text_blocks))
        for tb in table_blocks:
            for t in _split_table(tb["text"], sec_title):
                pieces.append((t, tb["page"]))
        deduped = []
        for text, page in pieces:
            key = text.strip()
            if key and key not in seen_texts:
                seen_texts.add(key)
                deduped.append((text, page))
        pieces = deduped

        total = len(pieces)
        for idx, (text, page) in enumerate(pieces):
            text = text.strip()
            if not text:
                continue
            tags, oem = tagger(text, sec_title, entry)
            cid = hashlib.md5(
                f"{entry['doc_id']}|{sec_title}|{idx}|{text}".encode("utf-8")
            ).hexdigest()[:12]
            chunks.append({
                "chunk_id": cid,
                "doc_id": entry["doc_id"],
                "doc_type": entry["doc_type"],
                "title": entry["title"],
                "source": entry["source"],
                "section": sec_title,
                "section_num": sec.get("section_num", ""),
                "page_num": page if page is not None else sec["page_start"],
                "chunk_index": idx,
                "total_chunks_in_section": total,
                "tags": tags,
                "oem": oem,
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
