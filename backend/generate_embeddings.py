"""
generate_embeddings.py — build data/embeddings.npy with the Gemini Embedding API,
INCREMENTALLY. Only chunks whose text is new or changed are sent to the API; every
unchanged chunk reuses its cached vector. Adding one manual then costs a few hundred
embeddings, not a full re-embed of the whole KB — essential once the KB is 10k+
chunks on a free-tier key.

    set GEMINI_API_KEY=...        (Windows)   /   export GEMINI_API_KEY=...
    set GEMINI_EMBED_SLEEP=8      (free tier: avoids 429 storms on large KBs)

    # ONE-TIME, before your first incremental rebuild, while the committed
    # embeddings.npy still matches the committed chunks_merged.jsonl:
    python generate_embeddings.py --seed-from-current

    # Normal use (after build_kb.py regenerates chunks_merged.jsonl):
    python generate_embeddings.py

Vectors are 768-dim (GEMINI_EMBED_DIM, must match embed.py at runtime) stored as
float16 (~1.5 KB/chunk). The content-addressed cache (data/embeddings_cache.npz,
keyed by hash(model|dim|task|text)) doubles as the checkpoint: an interrupted run
resumes because already-embedded texts are simply found in the cache and skipped.
Commit the regenerated embeddings.npy TOGETHER with chunks_merged.jsonl — rag.init_kb
requires their row counts to match, so they must always move as a pair.
"""
import load_env  # noqa: F401  — must precede `import embed` (reads env at import time)

import argparse
import hashlib
import os
import sys
import json

import numpy as np
import embed

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA = os.path.join(os.path.dirname(__file__), "data")
JSONL = os.path.join(DATA, "chunks_merged.jsonl")
EMB_CACHE = os.path.join(DATA, "embeddings.npy")
VEC_CACHE = os.path.join(DATA, "embeddings_cache.npz")

TASK = "RETRIEVAL_DOCUMENT"
SAVE_EVERY = 5  # persist the cache every N API batches so a crash loses little


def _load_chunks():
    with open(JSONL, encoding="utf-8") as f:
        chunks = [json.loads(l) for l in f if l.strip()]
    return chunks, [c.get("text", "") for c in chunks]


def _key(text, model, dim):
    """Content address for a chunk vector: identical text under the same model/
    dim/task always maps to the same cached vector."""
    h = hashlib.sha1(f"{model}|{dim}|{TASK}|{text}".encode("utf-8"))
    return h.hexdigest()


def _load_cache():
    """hash -> float16 vector. Missing/unreadable cache -> empty dict."""
    if not os.path.exists(VEC_CACHE):
        return {}
    try:
        z = np.load(VEC_CACHE, allow_pickle=False)
        keys, vecs = z["keys"], z["vectors"]
        return {str(k): vecs[i] for i, k in enumerate(keys)}
    except Exception as e:
        print(f"Ignoring unreadable cache {VEC_CACHE}: {e}")
        return {}


def _save_cache(cache):
    if not cache:
        return
    keys = np.array(list(cache.keys()))
    vecs = np.vstack([cache[k] for k in keys]).astype(np.float16)
    tmp = VEC_CACHE + ".tmp.npz"
    np.savez(tmp, keys=keys, vectors=vecs)
    os.replace(tmp, VEC_CACHE)


def seed_from_current(model, dim):
    """Bootstrap the cache from the CURRENTLY committed embeddings.npy +
    chunks_merged.jsonl. Only valid while they still correspond row-for-row
    (i.e. run this BEFORE the next build_kb.py rewrites the JSONL). Prevents a
    one-time full re-embed when first switching to incremental mode."""
    if not os.path.exists(EMB_CACHE):
        raise SystemExit("No embeddings.npy to seed from.")
    chunks, texts = _load_chunks()
    emb = np.load(EMB_CACHE)
    if emb.shape[0] != len(texts):
        raise SystemExit(
            f"Refusing to seed: embeddings.npy has {emb.shape[0]} rows but "
            f"chunks_merged.jsonl has {len(texts)} — they are not the committed "
            f"pair. Seed only when they match.")
    cache = _load_cache()
    for t, v in zip(texts, emb):
        cache[_key(t, model, dim)] = v.astype(np.float16)
    _save_cache(cache)
    print(f"Seeded cache with {len(texts)} vectors from the current committed pair "
          f"→ {VEC_CACHE}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-from-current", action="store_true",
                    help="bootstrap the cache from the current committed "
                         "embeddings.npy + chunks_merged.jsonl, then exit")
    args = ap.parse_args()

    if not embed.available():
        raise SystemExit("GEMINI_API_KEY not set — required to build embeddings.")
    model = embed.current_model()
    dim = embed.EMBED_DIM

    if args.seed_from_current:
        seed_from_current(model, dim)
        return

    chunks, texts = _load_chunks()
    cache = _load_cache()
    print(f"Loaded {len(chunks)} chunks; cache holds {len(cache)} vectors "
          f"(model={model}, dim={dim}).")

    # Which chunk texts still need embedding? De-dup identical texts so a repeated
    # slide/table row is embedded once.
    keys = [_key(t, model, dim) for t in texts]
    missing = []
    seen = set()
    for t, k in zip(texts, keys):
        if k not in cache and k not in seen:
            seen.add(k)
            missing.append((k, t))
    print(f"{len(missing)} new/changed chunks to embed; "
          f"{len(texts) - len(missing)} reused from cache.")

    # Embed the missing texts in throttled batches; the cache is the checkpoint.
    B = embed.BATCH_SIZE
    done = 0
    for bi, start in enumerate(range(0, len(missing), B), 1):
        batch = missing[start:start + B]
        try:
            vecs = embed.embed_documents([t for _, t in batch], task_type=TASK)
        except embed.QuotaExhausted as e:
            # Flush before exiting: the periodic checkpoint below can be up to
            # SAVE_EVERY batches stale, and those vectors cost real quota.
            _save_cache(cache)
            print(f"\n{e}")
            print(f"Cached {len(cache)} vectors ({done} embedded this run); "
                  f"{len(missing) - done} still to do.")
            print("embeddings.npy was NOT written — it must stay in step with "
                  "chunks_merged.jsonl. Rerun this script after the quota resets.")
            raise SystemExit(2)
        for (k, _), v in zip(batch, vecs):
            cache[k] = v.astype(np.float16)
        done += len(batch)
        print(f"progress: {min(start + B, len(missing))}/{len(missing)} new")
        if bi % SAVE_EVERY == 0:
            _save_cache(cache)
    _save_cache(cache)

    # Assemble embeddings.npy in exact JSONL row order (rag.init_kb requires
    # emb_matrix.shape[0] == len(chunks)).
    missing_keys = {k for k, _ in missing}
    still_missing = [i for i, k in enumerate(keys) if k not in cache]
    if still_missing:
        raise SystemExit(f"{len(still_missing)} chunks failed to embed "
                         f"(first at row {still_missing[0]}) — not saving.")
    emb = np.vstack([cache[k] for k in keys]).astype(np.float16)
    if emb.shape[0] != len(chunks):
        raise SystemExit(f"row mismatch: {emb.shape[0]} vs {len(chunks)} — not saving")
    np.save(EMB_CACHE, emb)
    size_mb = os.path.getsize(EMB_CACHE) / 1024 / 1024
    print(f"Saved {EMB_CACHE}  shape={emb.shape}  dtype={emb.dtype}  ({size_mb:.1f} MB)")
    print(f"Embedded {len(missing_keys)} new vectors this run.")
    print("Commit chunks_merged.jsonl and embeddings.npy together.")


if __name__ == "__main__":
    main()
