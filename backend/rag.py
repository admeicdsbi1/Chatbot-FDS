"""
rag.py — Retrieval brain. Loads the KB, embeds queries via the Gemini Embedding
API (no local model → fits Render's 512MB free tier), and runs the hybrid
semantic+keyword retrieval ported from the original app.py. Semantic search is a
plain NumPy cosine over 257 normalized vectors — FAISS/torch are not needed.
"""
import os, json, re
from collections import Counter
import numpy as np

import embed
from voice_text import (
    ABBREVIATIONS, PROCEDURAL_SIGNALS, HINGLISH_TO_ENGLISH,
)

# ---- Config ----
_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
JSONL = os.path.join(_DATA_DIR, "chunks_merged.jsonl")
EMB_CACHE = os.path.join(_DATA_DIR, "embeddings.npy")

TOP_K_SEMANTIC = 12
TOP_K_FINAL = 4

# ---- Module state (populated by init_kb) ----
chunks = []
emb_matrix = None          # (N, D) normalized float32, or None if unavailable
keyword_index = {}


def _normalize_rows(m):
    m = np.asarray(m, dtype=np.float32)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


def init_kb():
    """Load chunks + keyword index. Load embeddings.npy if it matches the current
    Gemini embedding dimension; otherwise (missing / stale MiniLM file) rebuild it
    via the Gemini API and cache to disk. Falls back to keyword-only if no key."""
    global chunks, emb_matrix, keyword_index

    print("Loading knowledge base...")
    try:
        with open(JSONL, encoding="utf-8") as f:
            chunks = [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError:
        print(f"WARNING: {JSONL} not found")
        chunks = []
        return

    expected_dim = embed.probe_dim() if embed.available() else None
    cached = None
    if os.path.exists(EMB_CACHE):
        try:
            cached = np.load(EMB_CACHE)
        except Exception as e:
            print(f"Could not read {EMB_CACHE}: {e}")

    matches = (
        cached is not None
        and cached.shape[0] == len(chunks)
        and (expected_dim is None or cached.shape[1] == expected_dim)
    )

    if matches:
        emb_matrix = _normalize_rows(cached)
        print(f"Loaded embeddings: {emb_matrix.shape}")
    elif embed.available():
        why = "missing" if cached is None else f"stale (shape {cached.shape}, dim≠{expected_dim})"
        print(f"Embeddings {why} — rebuilding via Gemini API...")
        texts = [c.get("text", "") for c in chunks]
        emb_matrix = _normalize_rows(embed.embed_documents(texts))
        try:
            np.save(EMB_CACHE, emb_matrix)
            print(f"Saved rebuilt embeddings: {emb_matrix.shape}")
        except Exception as e:
            print(f"Could not cache embeddings: {e}")
    else:
        emb_matrix = None
        print("No GEMINI_API_KEY and no usable cache — keyword-only retrieval.")

    for i, c in enumerate(chunks):
        for tag in c.get("tags", []):
            keyword_index.setdefault(tag.lower(), set()).add(i)
        oem = c.get("oem")
        if oem:
            keyword_index.setdefault(oem.lower(), set()).add(i)
        for w in re.findall(r'\b[a-zA-Z]{3,}\b', c.get("section", "").lower()):
            keyword_index.setdefault(w, set()).add(i)
        for w in set(re.findall(r'\b[a-zA-Z]{3,}\b', c.get("text", "").lower())):
            keyword_index.setdefault(w, set()).add(i)
    print(f"KB loaded: {len(chunks)} chunks, {len(keyword_index)} terms")


def embed_query(text):
    """Embed a query via the Gemini API → normalized (D,) vector, or None."""
    return embed.embed_query(text)


# ================================================================
# Query expansion / normalization (ported verbatim)
# ================================================================
def expand_query(q):
    words = q.lower().split()
    exp = list(words)
    for w in words:
        cl = re.sub(r'[^\w]', '', w)
        if cl in ABBREVIATIONS:
            exp.append(ABBREVIATIONS[cl])
    return " ".join(exp)


def normalize_hinglish(q):
    """Convert Hinglish query to English-enriched form for better retrieval."""
    words = q.lower().split()
    joined = " ".join(words)
    joined = re.sub(r'\baa\s+raha\s+hai\b', 'showing displaying', joined)
    joined = re.sub(r'\bkaam\s+nahi\s+kar\s+raha\b', 'not working failure', joined)
    joined = re.sub(r'\bpower\s+nahi\s+aa\s+raha\b', 'no power supply failure', joined)
    joined = re.sub(r'\bkya\s+karna\s+chahiye\b', 'what to do procedure', joined)
    joined = re.sub(r'\bkya\s+kare\b', 'what to do procedure', joined)
    joined = re.sub(r'\bkaise\s+kare\b', 'how to procedure steps', joined)
    joined = re.sub(r'\bkaise\s+check\s+kare\b', 'how to check test procedure', joined)
    joined = re.sub(r'\bkaise\s+test\s+kare\b', 'how to test procedure', joined)
    joined = re.sub(r'\bkaise\s+badle\b', 'how to replace procedure', joined)
    enriched = joined.split()
    extra = []
    for w in words:
        cl = re.sub(r'[^\w]', '', w)
        if cl in HINGLISH_TO_ENGLISH and HINGLISH_TO_ENGLISH[cl]:
            extra.append(HINGLISH_TO_ENGLISH[cl])
    enriched.extend(extra)
    return " ".join(enriched)


def is_procedural(q):
    return any(s in q.lower() for s in PROCEDURAL_SIGNALS)


def detect_query_oem(query):
    """Detect if query mentions a specific OEM."""
    ql = query.lower()
    oem_patterns = {
        "FAIVELEY": [r'\bfaiveley\b', r'\bwabtec\b', r'\baef\b', r'\bswkp\b', r'\bdv12\b', r'\bwbi\b'],
        "KNORR BREMSE": [r'\bknorr\b', r'\bbremse\b', r'\bmgs2\b', r'\besra\b', r'\bmb04\b', r'\bpb03\b', r'\beb01\b'],
        "ESCORTS KUBOTA": [r'\bescorts?\b', r'\bkubota\b', r'\bekl\b', r'\bjop\b', r'\bjfp\b', r'\bjio\b', r'\bgui\b'],
    }
    for oem, patterns in oem_patterns.items():
        for p in patterns:
            if re.search(p, ql):
                return oem
    return None


def retrieve(query, k=TOP_K_FINAL):
    if not chunks:
        return []
    exp = expand_query(query)
    hinglish_exp = normalize_hinglish(query)
    full_exp = exp + " " + hinglish_exp
    proc = is_procedural(query)
    query_oem = detect_query_oem(query)
    qv = embed_query(full_exp) if emb_matrix is not None else None
    if qv is None:
        qterms = set(re.findall(r'\b[a-zA-Z]{2,}\b', full_exp.lower()))
        hits = Counter()
        for t in qterms:
            for idx in keyword_index.get(t, set()):
                hits[idx] += 1
        results = []
        for idx, h in hits.most_common(k * 2):
            score = h / max(len(qterms), 1)
            ch = chunks[idx]
            tags = set(ch.get("tags", []))
            if proc and ("procedure" in tags or "testing" in tags):
                score *= 1.3
            if proc and ("overview" in tags or "general information" in tags):
                score *= 0.5
            ch_oem = ch.get("oem", "")
            if query_oem:
                if ch_oem == query_oem:
                    score *= 1.8
                elif ch_oem and ch_oem != query_oem:
                    score *= 0.3
            results.append((score, ch))
        results.sort(key=lambda x: -x[0])
        return results[:k]

    # Semantic search: cosine == dot product (both sides normalized).
    sims = emb_matrix @ qv.astype(np.float32)
    top_n = min(TOP_K_SEMANTIC, sims.shape[0])
    top_ids = np.argpartition(-sims, top_n - 1)[:top_n]
    top_ids = top_ids[np.argsort(-sims[top_ids])]
    cands = {}
    mx = max(float(sims[top_ids[0]]), 0.01)
    for idx in top_ids:
        idx = int(idx)
        cands[idx] = {"s": float(sims[idx]) / mx, "k": 0.0}
    qterms = set(re.findall(r'\b[a-zA-Z]{2,}\b', full_exp.lower()))
    hits = Counter()
    for t in qterms:
        for idx in keyword_index.get(t, set()):
            hits[idx] += 1
    for idx, h in hits.most_common(TOP_K_SEMANTIC * 2):
        kw = h / max(len(qterms), 1)
        if idx not in cands:
            cands[idx] = {"s": 0.0, "k": kw}
        else:
            cands[idx]["k"] = kw
    res = []
    for idx, sc in cands.items():
        score = 0.55 * sc["s"] + 0.45 * sc["k"]
        ch = chunks[idx]
        tags = set(ch.get("tags", []))
        if proc and ("procedure" in tags or "testing" in tags):
            score *= 1.3
        if proc and ("overview" in tags or "general information" in tags):
            score *= 0.5
        sec = ch.get("section", "").lower()
        if "abbreviation" in sec:
            score *= 0.4
        sw = set(re.findall(r'\b[a-zA-Z]{3,}\b', sec))
        qw = set(re.findall(r'\b[a-zA-Z]{3,}\b', query.lower()))
        ov = sw & qw
        if ov:
            score *= (1.0 + 0.15 * len(ov))
        ch_oem = ch.get("oem", "")
        if query_oem:
            if ch_oem == query_oem:
                score *= 1.8
            elif ch_oem and ch_oem != query_oem:
                score *= 0.3
        res.append((score, ch))
    res.sort(key=lambda x: -x[0])
    return res[:k]


def build_context(excerpts):
    lines = []
    for i, (sc, c) in enumerate(excerpts, 1):
        sec = c.get("section", "")
        doc = c.get("title", c.get("doc_id", ""))
        pg = c.get("page_num", "")
        oem = c.get("oem", "")
        txt = re.sub(r"\s+", " ", c.get("text", "").strip())
        if len(txt) > 1500:
            txt = txt[:1500] + " …"
        h = f"[Source {i}: {doc}"
        if sec: h += f" | {sec[:60]}"
        if pg: h += f" | p.{pg}"
        if oem: h += f" | OEM: {oem}"
        h += "]"
        lines.append(f"{h}\n{txt}")
    return "\n\n".join(lines)


def build_sources(excerpts):
    parts, seen = [], set()
    for _, c in excerpts[:3]:
        doc = c.get("title", c.get("doc_id", ""))
        sec = c.get("section", "")[:50]
        pg = c.get("page_num", "")
        key = f"{doc}|{sec}"
        if key not in seen:
            seen.add(key)
            s = f"**{doc}**"
            if sec: s += f" → {sec}"
            if pg: s += f" (p.{pg})"
            parts.append(s)
    return "\n".join(f"- {p}" for p in parts)
