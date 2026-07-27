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

# Groq fallback (separate free quota): when Gemini is throttled, rerank stays
# alive here instead of silently dropping to plain hybrid order — so retrieval
# precision does NOT degrade under Gemini quota pressure.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("RERANK_GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def enabled():
    return _ENABLED and (bool(API_KEY) or bool(GROQ_API_KEY))


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
