"""
rag.py — Retrieval brain. Loads the KB, embeds queries via the Gemini Embedding
API (no local model → fits Render's 512MB free tier), and runs the hybrid
semantic+keyword retrieval ported from the original app.py. Semantic search is a
plain NumPy cosine over 257 normalized vectors — FAISS/torch are not needed.
"""
import os, json, re, threading
from collections import Counter
import numpy as np

import embed
import rerank
from voice_text import (
    ABBREVIATIONS, PROCEDURAL_SIGNALS, HINGLISH_TO_ENGLISH,
)

# ---- Config ----
_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
JSONL = os.path.join(_DATA_DIR, "chunks_merged.jsonl")
EMB_CACHE = os.path.join(_DATA_DIR, "embeddings.npy")

TOP_K_SEMANTIC = int(os.environ.get("TOP_K_SEMANTIC", "40"))
TOP_K_FINAL = int(os.environ.get("TOP_K_FINAL", "8"))
CTX_CHUNK_CHARS = int(os.environ.get("CTX_CHUNK_CHARS", "2500"))
RERANK_POOL = int(os.environ.get("RERANK_POOL", "30"))

# ---- Module state (populated by init_kb) ----
chunks = []
emb_matrix = None          # (N, D) normalized float32, or None if unavailable
keyword_index = {}


def _normalize_rows(m):
    m = np.asarray(m, dtype=np.float32)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


def _build_embeddings_bg():
    """Build embeddings via the Gemini API in the background, then swap them in.
    Never raises into startup — on failure the app stays on keyword-only retrieval."""
    global emb_matrix
    try:
        texts = [c.get("text", "") for c in chunks]
        m = _normalize_rows(embed.embed_documents(texts))
        emb_matrix = m
        print(f"Semantic search ready: embeddings {m.shape}")
        try:
            np.save(EMB_CACHE, m)
            print(f"Cached embeddings to {EMB_CACHE}")
        except Exception as e:
            print(f"Could not cache embeddings: {e}")
    except Exception as e:
        print(f"Background embedding build failed — staying keyword-only: {e}")


def init_kb():
    """Load chunks + keyword index (fast, never crashes). Load embeddings.npy if it
    matches the current embedding dimension; otherwise build it via the Gemini API
    in a BACKGROUND thread so startup is instant and serving begins immediately
    (keyword-only until embeddings are ready)."""
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
        print(f"WARNING: embeddings {why} — this should not happen with committed "
              f"artifacts; check GEMINI_EMBED_DIM matches the .npy. "
              f"Building via Gemini API in background...")
        threading.Thread(target=_build_embeddings_bg, daemon=True).start()
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


def retrieval_mode():
    """'semantic' when the embedding matrix is loaded, else 'keyword-only'."""
    return "semantic" if emb_matrix is not None else "keyword-only"


def embedding_shape():
    return list(emb_matrix.shape) if emb_matrix is not None else None


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


def detect_query_coach(query):
    """Detect if the query names a coach type."""
    ql = query.lower()
    coach_patterns = {
        "LHB": [r'\blhb\b'],
        "ICF": [r'\bicf\b'],
        "Vande Bharat": [r'\bvande\s*bharat\b', r'\bt-?18\b'],
        "Amrit Bharat": [r'\bamrit\s*bharat\b'],
    }
    for coach, patterns in coach_patterns.items():
        for p in patterns:
            if re.search(p, ql):
                return coach
    return None


# Query-side signals that a question is clearly about one safety system. FSDS
# (fire detection/suppression) and WSP (wheel-slide protection) are unrelated
# systems; a cross-system match is almost always generic keyword noise
# ("test", "LHB", "coach", "procedure"), so we route the query to its system.
_FSDS_QUERY_SIGNALS = [
    r'\bfsds\b', r'\bfdss\b', r'\bfdas\b', r'\bfire\b', r'\bsmoke\b',
    r'\baerosol\b', r'\bsuppression\b', r'\bextinguish', r'\bdetector',
    r'\bdetection\b', r'\bflame\b', r'\blhd\b', r'\blinear\s+heat\b',
    r'\bhooter\b',
]
_WSP_QUERY_SIGNALS = [
    r'\bwsp\b', r'\bwheel\s+slide\b', r'\bwheel\s+slip\b', r'\banti[- ]?skid\b',
    r'\bslide\s+protection\b', r'\bdump\s+valve\b', r'\bskid\b',
    r'\bspeed\s+sensor\b', r'\bphonic\b', r'\bfaiveley\b', r'\bwabtec\b',
    r'\bknorr\b', r'\bbremse\b', r'\bescorts?\b', r'\bkubota\b',
]


def detect_query_system(query):
    """'FSDS' or 'WSP' when the query unambiguously targets one system, else None
    (no signal, or signals for both — stay neutral rather than mis-route)."""
    ql = query.lower()
    fs = any(re.search(p, ql) for p in _FSDS_QUERY_SIGNALS)
    ws = any(re.search(p, ql) for p in _WSP_QUERY_SIGNALS)
    if fs and not ws:
        return "FSDS"
    if ws and not fs:
        return "WSP"
    return None


def _chunk_system(ch):
    """The safety system a chunk belongs to (FSDS / WSP / None), from its
    registry-stamped subsystem, falling back to tags."""
    sub = (ch.get("subsystem") or "").lower()
    if "wheel slide" in sub or "wsp" in sub:
        return "WSP"
    if "fire" in sub:
        return "FSDS"
    tags = {t.upper() for t in ch.get("tags", [])}
    if "WSP" in tags:
        return "WSP"
    if "FSDS" in tags or "FDSS" in tags:
        return "FSDS"
    return None


def _system_factor(ch, query_system):
    """Demote a chunk from the other safety system when the query clearly targets
    one. Only demotes (never boosts), so ranking within the correct system — and
    of system-neutral chunks — is untouched."""
    if not query_system:
        return 1.0
    ch_sys = _chunk_system(ch)
    if ch_sys and ch_sys != query_system:
        return 0.3
    return 1.0


CLARIFY_ENABLED = os.environ.get("CLARIFY_ENABLED", "1") == "1"
CLARIFY_TOPN = int(os.environ.get("CLARIFY_TOPN", "3"))


def clarification_needed(query, excerpts):
    """Return a short clarifying question when the query gives NO coach/OEM signal
    yet the top excerpts genuinely span conflicting coach types or OEMs — otherwise
    None. Users usually describe only a symptom; blending specs across coaches/OEMs
    would be a safety issue, so asking is safer than guessing.

    Kept deliberately conservative to avoid over-asking:
      - only the top CLARIFY_TOPN results are considered;
      - if any of them is an IR-wide ('common') source, that answers all coaches,
        so we do NOT ask (e.g. a standardised-value circular resolves the query);
      - the conflict must come from >=2 DISTINCT documents, so a single manual that
        merely lists several coach types does not by itself trigger a question.

    Inert until chunks carry coach_type/oem (i.e. after a KB rebuild), so it never
    changes behaviour on the legacy committed KB."""
    if not CLARIFY_ENABLED or not excerpts:
        return None
    if detect_query_oem(query) or detect_query_coach(query):
        return None
    top = [c for _, c in excerpts[:CLARIFY_TOPN]]

    parts = []

    # System spanning (FSDS fire-detection vs WSP wheel-slide) when the query
    # names no system — these are unrelated systems, so blending their specs is
    # unsafe. Checked before the 'common' short-circuit below, since an all-coach
    # source resolves coach ambiguity but NOT which system the user means.
    if not detect_query_system(query):
        sys_docs = {}
        for c in top:
            s = _chunk_system(c)
            if s:
                sys_docs.setdefault(s, set()).add(c.get("doc_id"))
        if len(sys_docs) >= 2 and len({d for ds in sys_docs.values() for d in ds}) >= 2:
            parts.append("system (FSDS fire-detection / WSP wheel-slide)")

    # Coach / OEM spanning, only when contributed by >=2 distinct documents (a
    # lone multi-coach manual is not a cross-source conflict). An IR-wide
    # ('common') source answers all coaches, so skip these when one is present.
    if not any("common" in (c.get("coach_type") or []) for c in top):
        coach_docs = {}
        for c in top:
            for ct in (c.get("coach_type") or []):
                if ct and ct != "common":
                    coach_docs.setdefault(ct, set()).add(c.get("doc_id"))
        coaches = set(coach_docs)
        oems = {c.get("oem") for c in top if c.get("oem")}
        n_coach_docs = len({d for docs in coach_docs.values() for d in docs})
        if len(coaches) >= 2 and n_coach_docs >= 2:
            parts.append("coach type (" + " / ".join(sorted(coaches)) + ")")
        if len(oems) >= 2:
            parts.append("OEM (" + " / ".join(sorted(oems)) + ")")

    if not parts:
        return None
    return ("To give you the correct values, please tell me the "
            + " and ".join(parts) + " for your equipment.")


def _recency_factor(ch):
    """Gentle boost so a newer instruction letter edges ahead of an older manual
    on otherwise-similar matches (supersession: latest governs). Circulars/SMIs
    get a touch more since they override manual values. Bounded (~1.0–1.11) so it
    never overrides genuine semantic relevance."""
    d = ch.get("issue_date", "") or ""
    if not d[:4].isdigit():
        return 1.0
    year = int(d[:4])
    factor = 1.0 + max(0, min(year - 2010, 20)) * 0.004
    dt = ch.get("doc_type", "") or ""
    if "circular" in dt or "instruction" in dt:
        factor += 0.03
    return factor


def _pool_is_ambiguous(cands):
    """True when the top candidates span >1 coach type, OEM, or subsystem — the
    case where a rerank most helps separate the right manual from lookalikes."""
    top = [c for _, c in cands[:15]]
    coaches = {ct for c in top for ct in (c.get("coach_type") or [])
               if ct and ct != "common"}
    oems = {c.get("oem") for c in top if c.get("oem")}
    subs = {c.get("subsystem") for c in top if c.get("subsystem")}
    return len(coaches) >= 2 or len(oems) >= 2 or len(subs) >= 2


def _coach_factor(ch, query_coach):
    """Route to the queried coach type: boost matches, demote a different coach
    (but never demote 'common' documents that apply to all coaches)."""
    if not query_coach:
        return 1.0
    cts = ch.get("coach_type") or []
    if query_coach in cts:
        return 1.5
    if cts and "common" not in cts:
        return 0.4
    return 1.0


def retrieve(query, k=TOP_K_FINAL):
    if not chunks:
        return []
    exp = expand_query(query)
    hinglish_exp = normalize_hinglish(query)
    full_exp = exp + " " + hinglish_exp
    proc = is_procedural(query)
    query_oem = detect_query_oem(query)
    query_coach = detect_query_coach(query)
    query_system = detect_query_system(query)
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
            score *= _coach_factor(ch, query_coach)
            score *= _system_factor(ch, query_system)
            score *= _recency_factor(ch)
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
        score *= _coach_factor(ch, query_coach)
        score *= _system_factor(ch, query_system)
        score *= _recency_factor(ch)
        res.append((score, ch))
    res.sort(key=lambda x: -x[0])
    # Optional flash-lite rerank, only when the pool spans several manuals (gated
    # by RERANK_ENABLED; fail-safe to hybrid order otherwise).
    if rerank.enabled() and _pool_is_ambiguous(res):
        res = rerank.rerank(query, res, pool=RERANK_POOL)
    return res[:k]


def _fmt_date(iso):
    """ISO issue_date -> railway-style citation date. 2024-10-01 -> 01.10.2024;
    2024-10 -> 10.2024; 2024 -> 2024. Anything unexpected passes through."""
    if not iso:
        return ""
    parts = iso.split("-")
    if len(parts) == 3:
        return f"{parts[2]}.{parts[1]}.{parts[0]}"
    if len(parts) == 2:
        return f"{parts[1]}.{parts[0]}"
    return iso


def _cite_ref(c):
    """Circular/manual reference string for a chunk: 'LETTER, dt. DD.MM.YYYY'."""
    letter = c.get("letter_no", "")
    dt = _fmt_date(c.get("issue_date", ""))
    if letter and dt:
        return f"{letter}, dt. {dt}"
    return letter or (f"dt. {dt}" if dt else "")


def build_context(excerpts):
    lines = []
    for i, (sc, c) in enumerate(excerpts, 1):
        sec = c.get("section", "")
        clause = c.get("section_num", "")
        doc = c.get("title", c.get("doc_id", ""))
        pg = c.get("page_num", "")
        oem = c.get("oem", "")
        coach = c.get("coach_type", []) or []
        raw = c.get("text", "").strip()
        if "|" in raw and "\n" in raw:
            # markdown table chunk — collapsing newlines would destroy the rows
            txt = re.sub(r"[ \t]+", " ", raw)
        else:
            txt = re.sub(r"\s+", " ", raw)
        if len(txt) > CTX_CHUNK_CHARS:
            txt = txt[:CTX_CHUNK_CHARS] + " …"
        h = f"[Source {i}: {doc}"
        sec_label = (f"Clause {clause} " if clause else "") + sec
        if sec_label.strip(): h += f" | {sec_label.strip()[:70]}"
        if pg: h += f" | p.{pg}"
        if coach: h += f" | Coach: {', '.join(coach)}"
        if oem: h += f" | OEM: {oem}"
        ref = _cite_ref(c)
        if ref: h += f" | Ref: {ref}"
        h += "]"
        lines.append(f"{h}\n{txt}")
    return "\n\n".join(lines)


def _doc_label(c):
    """Document title as a markdown link to its source PDF (deep-linked to the
    cited page via #page=N) when the chunk carries a download_url; otherwise the
    bare bold title. Titles have no brackets, but sanitize defensively so a stray
    ']' can't break the markdown link."""
    doc = c.get("title", c.get("doc_id", ""))
    url = c.get("download_url", "")
    if not url:
        return f"**{doc}**"
    text = doc.replace("[", "(").replace("]", ")")
    pg = c.get("page_num", "")
    href = f"{url}#page={pg}" if pg else url
    return f"[**{text}**]({href})"


def build_sources(excerpts):
    parts, seen = [], set()
    for _, c in excerpts:
        doc = c.get("title", c.get("doc_id", ""))
        sec = c.get("section", "")[:50]
        clause = c.get("section_num", "")
        pg = c.get("page_num", "")
        key = f"{doc}|{clause}|{sec}"
        if key not in seen:
            seen.add(key)
            s = _doc_label(c)
            loc = []
            if clause: loc.append(f"Clause {clause}")
            if sec: loc.append(sec)
            if loc: s += " → " + " ".join(loc)
            if pg: s += f" (p.{pg})"
            ref = _cite_ref(c)
            if ref: s += f" — {ref}"
            parts.append(s)
    return "\n".join(f"- {p}" for p in parts)
