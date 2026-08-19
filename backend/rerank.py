"""
rerank.py — optional listwise reranker (Gemini flash-lite).

At 10-20x KB scale the top hybrid candidates for a symptom-only query can span
several manuals. A cheap listwise rerank re-scores the top pool against the query
and returns the best first. It reuses GEMINI_API_KEY (no new vendor, no local
model → still fits Render's 512 MB tier).

Gated by RERANK_ENABLED (default OFF, so behaviour is unchanged until you enable
it with a key and validate via ingest/eval). Fails safe: any error, missing key,
or malformed response leaves the original hybrid order untouched.
"""
import os
import re

import requests

API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL = os.environ.get("RERANK_MODEL", "gemini-3.1-flash-lite")
_ENABLED = os.environ.get("RERANK_ENABLED", "0") == "1"
SNIPPET_CHARS = int(os.environ.get("RERANK_SNIPPET_CHARS", "320"))
_SNIPPET_RAW = os.environ.get("RERANK_SNIPPET_RAW", "0") == "1"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

# Groq fallback (separate free quota): when Gemini is throttled, rerank stays
# alive here instead of silently dropping to plain hybrid order — so retrieval
# precision does NOT degrade under Gemini quota pressure.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("RERANK_GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def enabled():
    return _ENABLED and (bool(API_KEY) or bool(GROQ_API_KEY))


# A table chunk's text opens with a lead line ("Table - <section>:"), the
# markdown column-label row and its |---| separator. Measured over the 803 table
# chunks in the current KB — a third of it — that scaffolding eats a MEDIAN 82%
# of a 320-char snippet, and over 80% of it on 427 of them. Those column labels
# are byte-identical across hundreds of chunks, so the reranker was left
# discriminating on the one part of the text carrying no signal, while a prose
# candidate spent all 320 characters on prose. That is how "Use of Digital Torque
# Wrench" came to outrank the schedule holding the torque VALUE.
#
# Widening the budget does not fix this (320 and 900 measured identically): the
# problem is snippet COMPOSITION, not size. The section is already supplied
# separately in the listing label, so dropping the lead line loses nothing.
_LEAD_ROW = re.compile(r"^Table\s.{0,160}?:$")
_SEP_ROW = re.compile(r"^\|[-:|\s]+\|?$")
# ingest/chunker.py marks an in-table equipment heading with this character;
# backend/ cannot import from ingest/, so the convention is restated here.
_GROUP_MARK = re.compile(r"^\|?\s*▸\s*")

# Hinglish question words carry no topical signal but match many rows; without
# this "kya hai" and "kitna" would pull arbitrary prose into every excerpt.
_STOP = {"the", "and", "for", "with", "kya", "hai", "hona", "chahiye", "kitna",
         "kitne", "kaise", "mein", "kar", "ka", "ke", "ki", "me", "per", "are",
         "what", "how", "much", "should", "vande", "bharat"}


def _row_score(row, terms):
    """How well one row answers a query: matched terms, then value density.

    The tie-break matters more than the match count here. Several rows of a
    stabilizer table mention the stabilizer; only one carries "85 Nm", and a
    question asking what a torque IS contains no numeral to match it on. Rows
    holding a number-plus-unit are what a specification question wants.
    """
    low = row.lower()
    hits = sum(1 for t in terms if t in low)
    if not hits:
        return 0.0
    has_value = 1 if re.search(r"\d+(?:\.\d+)?\s*[A-Za-z%°/]", row) else 0
    return hits + 0.5 * has_value


def _snippet(ch, query="", budget=None):
    """The excerpt the reranker reads for one candidate.

    Two things decide whether the reranker can tell a value-bearing chunk from a
    lookalike, and a first-N-characters snippet gets both wrong.

    1. Table scaffolding. The lead line and column-label row eat a MEDIAN 82% of
       a 320-char window across the 803 table chunks (a third of the KB), and
       those labels are byte-identical across hundreds of chunks — so the model
       was discriminating on the one part carrying no signal.
    2. Position. For "stabilizer link fastener tightening torque" the answer
       `85 Nm` sits at character 1639 of a 2039-char chunk. Every candidate's
       first 320 characters look equally on-topic, so the reranker ranked by
       subject alone and picked a stabilizer chunk WITHOUT the torque. Widening
       the window does not reach it (320 and 900 measured identically); the
       excerpt has to be chosen by relevance, not by position.

    So: drop the scaffolding, then keep the rows that actually match the query,
    in document order. Fails safe — a chunk that is nothing but scaffolding, or
    one no row matches, falls back rather than going in empty.

    RERANK_SNIPPET_RAW=1 restores the old behaviour so an A/B needs an env var
    rather than an edit between runs — the same affordance rag._diversify
    already offers for forcing a flat per-doc cap.
    """
    budget = SNIPPET_CHARS if budget is None else budget
    text = ch.get("text", "")
    raw = re.sub(r"\s+", " ", text)[:budget]
    if _SNIPPET_RAW:
        return raw
    lines = text.splitlines()
    kept = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or _LEAD_ROW.match(s) or _SEP_ROW.match(s):
            continue
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if s.startswith("|") and _SEP_ROW.match(nxt):
            continue                      # the column-label row
        s = _GROUP_MARK.sub("", s)
        s = re.sub(r"\s*<br>\s*", " ", s)
        s = re.sub(r"\s*\|\s*", " ", s).strip(" |")
        if s:
            kept.append(s)
    if not kept:
        return raw

    terms = {w for w in re.findall(r"[a-z0-9]{3,}", query.lower()) if w not in _STOP}
    if terms:
        # Keep the best-matching rows, then restore document order so the
        # excerpt still reads as a passage rather than a bag of rows.
        scored = sorted(range(len(kept)),
                        key=lambda i: (-_row_score(kept[i], terms), i))
        chosen, used = set(), 0
        for i in scored:
            if used and used + len(kept[i]) + 1 > budget:
                continue
            chosen.add(i)
            used += len(kept[i]) + 1
            if used >= budget:
                break
        if chosen:
            kept = [kept[i] for i in sorted(chosen)]
    out = re.sub(r"\s+", " ", " ".join(kept)).strip()
    return out[:budget] if out else raw


def rerank(query, candidates, pool=30):
    """candidates: list of (score, chunk). Returns a reordered list, best first.
    Only the first `pool` candidates are reranked; the remainder keep their order
    after them. Fail-safe: returns candidates unchanged on any problem."""
    if not enabled() or len(candidates) < 2:
        return candidates
    head, tail = candidates[:pool], candidates[pool:]
    listing = []
    for i, (_, ch) in enumerate(head):
        doc = ch.get("title", ch.get("doc_id", ""))
        sec = ch.get("section", "")
        listing.append(f"[{i}] ({doc} — {sec}) {_snippet(ch, query)}")
    prompt = (
        "Rank the numbered maintenance-manual excerpts by how directly they answer "
        "the QUESTION. Return ONLY a JSON array of excerpt numbers, best first, no "
        "other text.\n\nQUESTION: " + query + "\n\nEXCERPTS:\n" + "\n".join(listing)
    )
    order = _ask(prompt, len(head))
    if not order:
        return candidates
    chosen = set(order)
    reordered = ([head[i] for i in order]
                 + [head[i] for i in range(len(head)) if i not in chosen])
    return reordered + tail


def _parse_order(txt, n):
    """Extract a valid, unique, in-range index order from the model's reply."""
    if not txt:
        return None
    m = re.search(r"\[[\d,\s]*\]", txt)
    if not m:
        return None
    seen, out = set(), []
    for x in re.findall(r"\d+", m.group(0)):
        i = int(x)
        if 0 <= i < n and i not in seen:
            seen.add(i)
            out.append(i)
    return out or None


def _ask_gemini(prompt, n):
    if not API_KEY:
        return None
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 200,
                             "thinkingConfig": {"thinkingBudget": 0}},
    }
    try:
        r = requests.post(URL, params={"key": API_KEY}, json=payload, timeout=30)
        if r.status_code != 200:
            print(f"rerank(gemini) {r.status_code}: {r.text[:120]}")
            return None
        cands = r.json().get("candidates", [])
        txt = "".join(p.get("text", "")
                      for p in cands[0].get("content", {}).get("parts", [])) if cands else ""
        return _parse_order(txt, n)
    except Exception as e:
        print(f"rerank(gemini) error: {e}")
        return None


def _ask_groq(prompt, n):
    if not GROQ_API_KEY:
        return None
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200, "temperature": 0.0, "stream": False,
    }
    try:
        r = requests.post(GROQ_URL, headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"}, json=payload, timeout=30)
        if r.status_code != 200:
            print(f"rerank(groq) {r.status_code}: {r.text[:120]}")
            return None
        choices = r.json().get("choices", [])
        txt = choices[0]["message"]["content"] if choices else ""
        return _parse_order(txt, n)
    except Exception as e:
        print(f"rerank(groq) error: {e}")
        return None


def _ask(prompt, n):
    """Gemini first, then Groq (separate quota) so rerank survives throttling."""
    return _ask_gemini(prompt, n) or _ask_groq(prompt, n)
