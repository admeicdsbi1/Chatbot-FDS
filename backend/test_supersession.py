"""
Tests for registry-declared supersession in retrieval (rag._build_superseded_by,
rag._supersession_factor, the context header tag). No network, no KB load.
Run:  python backend/test_supersession.py    (no pytest needed)
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import rag

_fails = []


def check(name, cond):
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _fails.append(name)


old = {"doc_id": "REPORT", "issue_date": "2025-08-20", "title": "Report", "text": "85 Nm"}
cs1 = {"doc_id": "CS1", "issue_date": "2026-04-09", "letter_no": "IRCAMTECH/2.0",
       "supersedes": ["REPORT"], "title": "Slip 1", "text": "85 Nm"}
cs2 = {"doc_id": "CS2", "issue_date": "2027-01-01", "letter_no": "IRCAMTECH/2.0 CS2",
       "supersedes": ["REPORT"], "title": "Slip 2", "text": "x"}
other = {"doc_id": "OTHER", "issue_date": "2024-01-01", "title": "Other", "text": "y"}

m = rag._build_superseded_by([old, cs1, other])
check("map built from chunks' supersedes", set(m) == {"REPORT"} and m["REPORT"]["doc_id"] == "CS1")
check("no supersedes -> empty map", rag._build_superseded_by([old, other]) == {})
m2 = rag._build_superseded_by([cs2, old, cs1])
check("newest superseding doc wins regardless of order", m2["REPORT"]["doc_id"] == "CS2")

rag.superseded_by = m
check("superseded doc demoted", rag._supersession_factor(old) == rag.SUPERSEDED_PENALTY < 1.0)
check("superseding doc untouched", rag._supersession_factor(cs1) == 1.0)
check("unrelated doc untouched", rag._supersession_factor(other) == 1.0)
check("label cites letter and date",
      rag._supersession_label(cs1) == "IRCAMTECH/2.0, dt. 09.04.2026")

tagged = dict(old, _superseded_by=rag._supersession_label(cs1))
ctx = rag.build_context([(1.0, tagged), (0.9, cs1)])
first, second = ctx.split("\n\n[Source 2")
check("context tags the superseded source", "SUPERSEDED by IRCAMTECH/2.0, dt. 09.04.2026" in first)
check("context does not tag the newer source", "SUPERSEDED" not in second)
check("correction slip counts as an instruction for recency",
      rag._recency_factor({"issue_date": "2026-04-09", "doc_type": "correction_slip"})
      > rag._recency_factor({"issue_date": "2026-04-09", "doc_type": "report"}))
rag.superseded_by = {}

print(f"\n{len(_fails)} failure(s)")
sys.exit(1 if _fails else 0)
