"""
rag.py — Retrieval brain. Loads the KB + FAISS index, embeds queries LOCALLY
(no Hugging Face Inference dependency), and runs the hybrid semantic+keyword
retrieval ported from the original app.py.
"""
import os, json, re, gc
from collections import Counter
import numpy as np
import faiss

from voice_text import (
    ABBREVIATIONS, PROCEDURAL_SIGNALS, HINGLISH_TO_ENGLISH,
)

# ---- Config ----
_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
JSONL = os.path.join(_DATA_DIR, "chunks_merged.jsonl")
EMB_CACHE = os.path.join(_DATA_DIR, "embeddings.npy")
EMB_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

TOP_K_SEMANTIC = 12
TOP_K_FINAL = 4

# ---- Module state (populated by init_kb) ----
chunks = []
faiss_index = None
keyword_index = {}
_emb_model = None


def init_kb():
    """Load chunks, build/load embeddings + FAISS index, build keyword index.
    Loads the SentenceTransformer model once for local query embedding."""
    global chunks, faiss_index, keyword_index, _emb_model

    print("Loading knowledge base...")
    try:
        with open(JSONL, encoding="utf-8") as f:
            chunks = [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError:
        print(f"WARNING: {JSONL} not found")
        chunks = []
        return

    print(f"Loading embedding model ({EMB_MODEL_NAME})...")
    from sentence_transformers import SentenceTransformer
    _emb_model = SentenceTransformer(EMB_MODEL_NAME)

    if os.path.exists(EMB_CACHE):
        print("Loading cached embeddings...")
        emb_matrix = np.load(EMB_CACHE)
    else:
        print("Computing embeddings for all chunks (one-time)...")
        texts = [c.get("text", "") for c in chunks]
        emb_matrix = _emb_model.encode(
            texts, normalize_embeddings=True, show_progress_bar=True
        )
        np.save(EMB_CACHE, emb_matrix)
    print(f"Embeddings: {emb_matrix.shape}")

    faiss_index = faiss.IndexFlatIP(emb_matrix.shape[1])
    faiss_index.add(emb_matrix.astype(np.float32))
    del emb_matrix
    gc.collect()

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
    """Embed a query locally with the cached SentenceTransformer model."""
    if _emb_model is None:
        return None
    try:
        vec = _emb_model.encode([text], normalize_embeddings=True)
        return np.asarray(vec, dtype=np.float32).reshape(1, -1)
    except Exception as e:
        print(f"Embed error: {e}")
        return None


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
    if not chunks or faiss_index is None:
        return []
    exp = expand_query(query)
    hinglish_exp = normalize_hinglish(query)
    full_exp = exp + " " + hinglish_exp
    proc = is_procedural(query)
    query_oem = detect_query_oem(query)
    qv = embed_query(full_exp)
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

    scores, ids = faiss_index.search(qv, TOP_K_SEMANTIC)
    cands = {}
    mx = max(float(scores[0][0]), 0.01)
    for sc, idx in zip(scores[0], ids[0]):
        idx = int(idx)
        cands[idx] = {"s": float(sc) / mx, "k": 0.0}
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
