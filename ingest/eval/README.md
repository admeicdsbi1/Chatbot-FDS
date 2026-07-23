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

## Workflow for a new manual family
1. Ingest the manual (registry → OCR → build_kb → generate_embeddings).
2. `python ingest/eval/seed_eval.py --doc <doc_id> --n 5`
3. Open `eval_candidates.jsonl`, **verify every `gold_value` against the PDF**,
   set `planted_wrong` to a plausible near-miss, move good rows into
   `eval_set.jsonl`.
4. `python ingest/eval/run_eval.py` — confirm existing cases did not regress and
   the new cases pass.
