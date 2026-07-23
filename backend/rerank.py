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
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"


def enabled():
    return _ENABLED and bool(API_KEY)


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
        snip = re.sub(r"\s+", " ", ch.get("text", ""))[:SNIPPET_CHARS]
        listing.append(f"[{i}] ({doc} — {sec}) {snip}")
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


def _ask(prompt, n):
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 200,
                             "thinkingConfig": {"thinkingBudget": 0}},
    }
    try:
        r = requests.post(URL, params={"key": API_KEY}, json=payload, timeout=30)
        if r.status_code != 200:
            print(f"rerank {r.status_code}: {r.text[:120]}")
            return None
        cands = r.json().get("candidates", [])
        if not cands:
            return None
        txt = "".join(p.get("text", "")
                      for p in cands[0].get("content", {}).get("parts", []))
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
    except Exception as e:
        print(f"rerank error: {e}")
        return None
