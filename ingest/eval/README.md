# KB accuracy evaluation

Proves that answer effectiveness does **not** drop as the KB grows. Run it before
and after every ingestion batch and compare the numbers.

## Files
- `eval_set.jsonl` — the curated ground-truth cases. One JSON object per line.
- `run_eval.py` — scores retrieval + the numeric guard against `eval_set.jsonl`.
- `seed_eval.py` — drafts candidate cases from the KB with Gemini flash-lite
  (writes `eval_candidates.jsonl` for you to review — never used directly).

## Case schema (`eval_set.jsonl`)
| field | meaning |
|---|---|
| `id` | short unique label |
| `question` | how a technician really asks — usually symptom-style, no coach/OEM named |
| `coach_type` / `oem` | ground-truth context (for future routing checks) |
| `expect_doc` | `doc_id` (see `ingest/doc_registry.py`) that SHOULD be retrieved |
| `expect_clause` / `expect_page` | where the answer lives (citation check) |
| `gold_value` | the exact value the answer must contain, verbatim (or `null`) |
| `planted_wrong` | a wrong value the numeric guard must strip (or `null`) |
| `notes` | provenance / TODO |

## Metrics (`run_eval.py`)
- **recall@k** — did `expect_doc` appear in the top-k retrieved chunks?
- **MRR** — mean reciprocal rank of the first correct-document hit.
- **value-retrieved** — is `gold_value` present verbatim in the retrieved context?
  (a value can only be cited correctly if it is retrieved).
- **guard-suppress** — with a synthetic answer holding both `gold_value` and
  `planted_wrong`, does `verify.guard_answer` keep the right one and strip the
  wrong one? End-to-end test of the numeric hard guard.

```
# optional GEMINI_API_KEY enables semantic retrieval; otherwise keyword-only
python ingest/eval/run_eval.py --k 8
```

## The commit gate

**Gate on rerank-ON `value-retrieved`. Use rerank-off only as an unchanged-control.**

Production runs `RERANK_ENABLED=1`, so a rerank-off score describes a
configuration we do not ship. The older bar — rerank-off `recall@8` >= 0.98 — was
retired on 2026-08-19 after it was shown to be measuring the wrong thing:
`recall@8` scores whether `expect_doc` appears, not whether the answer does, so a
case can pass on a chunk that does not contain its `gold_value`. Two of the three
misses that blocked that rebuild were **hollow HITs** whose value was `MISSING`
in *both* the old and new KB — an unreachable bar for any corpus, punishing a
build for cases that never delivered an answer.

Run, in this order:

1. **Control**, `RERANK_ENABLED=0` — must reproduce the previous run's four
   numbers *exactly*. Any movement means a rerank-path change leaked.
2. **Gate**, `RERANK_ENABLED=1 EVAL_SLEEP=6` — `value-retrieved` must not
   regress. This is the production figure.
3. **Named regressions** — probe any specific value you are protecting **3x**,
   not once. Listwise LLM reranking is non-deterministic: 12 of 60 cases moved
   between two runs of *identical* code.

Always `PYTHONHASHSEED=0` — one case oscillates on the rank-8/9 boundary under
keyword-index tie-breaks, so differences smaller than that are not results.

### Discard a run that logged either 429

```
grep -c 'rerank(gemini) 429\|rerank(groq)' eval.log     # must be 0
grep -c 'embedContent 429\|Embed query error' eval.log  # must be 0
```

Both are silent: a throttled **rerank** falls back to plain hybrid order (there
is no Groq key locally), and a starved **query embedding** degrades that query to
keyword-only. Either way the run reports a number for a condition it never
measured. Two runs were discarded this way on 2026-08-19 — one with 31 of 60
rerank 429s, one with 5 of 60 embedding 429s — which is why `EVAL_SLEEP` exists.
`rag.retrieve(..., trace=t)` sets `t["mode"] == "keyword-only"` for a starved
query if you want to assert it in code.

Also note `value-retrieved` is a substring test on the assembled context, so a
number found under the **wrong column** still scores a pass.

## Workflow for a new manual family
1. Ingest the manual (registry → OCR → build_kb → generate_embeddings).
2. `python ingest/eval/seed_eval.py --doc <doc_id> --n 5`
3. Open `eval_candidates.jsonl`, **verify every `gold_value` against the PDF**,
   set `planted_wrong` to a plausible near-miss, move good rows into
   `eval_set.jsonl`.
4. `python ingest/eval/run_eval.py` — confirm existing cases did not regress and
   the new cases pass.
