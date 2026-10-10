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

# ---- counterpart pull (rag._with_amendments) ----
OLD_T = "Shop Schedule-1 SS-1 18 Months 5 Days Shop Schedule-2 36 Months Monthly 30 Days Quarterly 90"
rep = {"doc_id": "REPORT", "chunk_id": "c0", "text": OLD_T}
slip_tab = {"doc_id": "CS1", "chunk_id": "c1",
            "text": "Shop Schedule-1 SS1 18 months 45 days Shop Schedule-2 36 months Monthly 30 days Quarterly 90"}
cover = {"doc_id": "CS1", "chunk_id": "c2", "text": "Correction Slip-1 covering letter Railway Board committee"}
fill = [(0.5, {"doc_id": "OTHER", "chunk_id": f"f{n}", "text": "unrelated"}) for n in range(7)]
pool = [(1.0, rep), (0.9, cover), (0.3, slip_tab)] + fill
saved = rag.superseded_by
rag.superseded_by = {"REPORT": {"doc_id": "CS1"}}

tr = {}
out = rag._with_amendments([(1.0, rep)] + fill, pool, 8, tr)
ids = [c["chunk_id"] for _, c in out]
check("counterpart seated right after the superseded chunk", ids[:2] == ["c0", "c1"])
check("the cover letter (least overlap, though better ranked) is not the one pulled", "c2" not in ids)
check("still k results, lowest filler dropped", len(out) == 8 and "f6" not in ids)
check("trace records the pull", tr.get("amendments_pulled") == ["c1"])

out = rag._with_amendments(fill + [(0.4, rep)], pool, 8)
check("a counterpart seated past slot k survives the trim",
      [c["chunk_id"] for _, c in out][-2:] == ["c0", "c1"] and len(out) == 8)
check("no pull when the counterpart is already present",
      len(rag._with_amendments([(1.0, rep), (0.9, slip_tab)], pool, 8)) == 2)
check("no pull when the counterpart is not in the retrieval pool",
      len(rag._with_amendments([(1.0, rep)], [(1.0, rep), (0.9, cover)], 8)) == 1)
weak = {"doc_id": "CS1", "chunk_id": "c3", "text": "Shop Schedule-1 something else entirely different words"}
check("no pull below AMENDMENT_MIN_OVERLAP",
      len(rag._with_amendments([(1.0, rep)], [(1.0, rep), (0.5, weak)], 8)) == 1)
check("unsuperseded chunks never pull",
      len(rag._with_amendments([(1.0, slip_tab)], pool, 8)) == 1)
rag.superseded_by = saved
check("printed page shown beside the PDF page",
      rag._page_label({"page_num": 52, "printed_page": "4"}) == "p.4 (PDF p.52)")
check("no duplicate when they agree", rag._page_label({"page_num": 5, "printed_page": "5"}) == "p.5")

print(f"\n{len(_fails)} failure(s)")
sys.exit(1 if _fails else 0)
