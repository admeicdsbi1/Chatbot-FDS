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
| `expect_absent` | `true` for an absence case: no right document, no gold value, and `planted_wrong` must be stripped |
| `notes` | provenance / TODO |

## Metrics (`run_eval.py`)
- **recall@k** — did `expect_doc` appear in the top-k retrieved chunks?
- **MRR** — mean reciprocal rank of the first correct-document hit.
- **value-retrieved** — is `gold_value` present verbatim in the retrieved context?
  (a value can only be cited correctly if it is retrieved).
- **guard-suppress** — with a synthetic answer holding both `gold_value` and
  `planted_wrong`, does `verify.guard_answer` keep the right one and strip the
  wrong one? End-to-end test of the numeric hard guard.
- **absence-suppress** — for a case marked `expect_absent`, the KB holds no
  answer, so a plausible value is fed in alone and the guard must **strip** it.
  Added 2026-08-28: every other metric assumes a value exists, so the one path
  none of them could reach was the one where the honest answer is "not in these
  97 documents".

  Absence cases set `expect_doc: null` and `gold_value: null` and carry only a
  `planted_wrong`. **They take no part in recall@k or MRR** — those denominators
  are the number of cases naming an `expect_doc`, not `len(cases)`, so adding
  absence cases cannot move the four older metrics or break comparability with
  any figure recorded before them.

  On this corpus the metric does double duty. `guard_answer` compacts all
  retrieved chunks into a single haystack, so a value confirms if it appears
  *anywhere*. With 1,775 Vande Bharat chunks against 192 Amrit Bharat, an Amrit
  Bharat question retrieves mostly VB material — so a leak here is **cross-coach
  contamination caught in the act**. `absent-amrit-bharat-torque` does exactly
  that and currently **FAILS**: the real VB stabilizer figure `85 Nm` confirms an
  Amrit Bharat claim, sourced from a `coach_type: ['Vande Bharat']` chunk
  (`VB_Shop_Schedule_SS1_SS2_Report_2025` p.172) among 8 retrieved chunks of
  which **none** is Amrit-Bharat-only. That is the open proposal on
  `require-evidence-in-the-schema-not-the-prompt`, now demonstrated rather than
  argued.

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
   not once. Not because the reranker samples — `rerank._ask_gemini` sends
   `temperature: 0.0` with `thinkingBudget: 0`, so it decodes greedily. The 3x
   probe guards against **drift in a hosted model**, which no local setting
   controls.

**Measured 2026-08-28: the gate is exactly reproducible, and that is what the
zero-tolerance rule in step 2 rests on.** Five consecutive clean runs
(`PYTHONHASHSEED=0 EVAL_SLEEP=6 RERANK_ENABLED=1`, rerank confirmed firing on a
pool of 130–167, zero 429s) produced **byte-identical logs**:

```
recall@8 57/60 | MRR 0.778 | value-retrieved 27/35 | guard-suppress 11/16
mean context 10,077 chars/query | spread 0 on every metric, 5/5 runs
always missing: knorr-brakepipe, vb-fork-gap, wsp-maintenance-drive (no churn)
```

Those are the figures recorded for this KB on 2026-08-19, reproduced nine days
later. Diff against them.

**On the "12 of 60" this file used to attribute to the reranker.** It happened
and it stays on the record, but the cause was most likely **429 contamination,
not model sampling**. Two runs were discarded that day, one with 31 of 60 rerank
429s; a run where half the queries silently fell back to plain hybrid order,
diffed against one where a different subset did, differs in roughly a fifth of
its cases. Unproven — whether those two particular runs were 429-clean was never
recorded — but greedy decoding leaves little else to blame.

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

**This is not hygiene — it is the precondition the gate depends on.** With 429s
excluded the four numbers reproduce byte-for-byte across five runs; with them
admitted the suite swings by roughly a fifth of its cases. A run that skips this
check is not a slightly worse measurement, it is a measurement of a different
configuration.

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
