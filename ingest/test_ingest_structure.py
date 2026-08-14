"""Structural regression tests for the ingest path. No PDFs, no API, no quota.

    cd ingest && python -m pytest test_ingest_structure.py -q

These lock in the properties Phase 3.1 established. They exist because the 60-case
retrieval eval cannot see any of them: it measures which chunks come back, not
whether a chunk's columns still mean what the page meant.
"""
import re

import pytest

from chunker import (_columns_of, _split_table, merge_tiny_sections,
                     _GROUP_ROW, TABLE_MAX)
from parse_pdf import (_dup, _group_label, _marked_label, _repair_header,
                       _same_table, _header_quality, _is_running_row,
                       GROUP_MARK, _COLN_RE, _COLUMN_LABEL, _PAGE_FOOTER)

SEP = "|---|---|---|---|---|---|---|---|---|---|---|---|"
# the shop-schedule report's electrical matrix as PyMuPDF reports it: a spanning
# group row over the leaf labels, with the group name repeated in every column
HEAD = ("|S.No.|Equipment/<br>Sub-Assy.|Col3|Activities|Maintenance Periodicity"
        "|Col6|Col7|Col8|Col9|Col10|Col11|Col12|")
LABELS = ("|**S.No.**|**Equipment/**<br>**Sub-Assy. **||**Activities**|**T **"
          "|**M **|**Q **|**9 M**|**  SS1**|**   SS2**|**    SS3**"
          "|**Remark/ Reference**|")


# ---- header repair ----------------------------------------------------------
def test_repair_header_folds_two_level_head():
    header, body = _repair_header(HEAD, [LABELS, "|||1.|Check bolts.||||✓|✓|✓||"])
    cells = [c.strip() for c in header.strip().strip("|").split("|")]
    assert cells[8:11] == ["SS1", "SS2", "SS3"]
    assert body == ["|||1.|Check bolts.||||✓|✓|✓||"]   # label row consumed


def test_repair_header_keeps_single_letter_schedule_columns():
    """Regression: "T" is a substring of "Maintenance Periodicity", so an
    unguarded containment test deleted the T column's label and left its ticks
    filed under the group heading — a wrong periodicity, not just a wrong word."""
    header, _ = _repair_header(HEAD, [LABELS])
    cells = [c.strip() for c in header.strip().strip("|").split("|")]
    assert "T" in cells[4], cells
    assert cells[5] == "M" and cells[6] == "Q"


def test_dup_requires_a_meaningful_overlap():
    assert _dup("Maintenance Periodicity", "Maintenance") is True
    assert _dup("Maintenance Periodicity", "T") is False
    assert _dup("S.No.", "S.No.") is True


def test_repair_header_leaves_a_real_header_alone():
    """A table whose first data row merely happens to be bold keeps its header."""
    head = "|S.N.|B.U.|Activities|"
    body = ["|**1.**|Full Rake|● Receiving and placement of rake.|"]
    assert _repair_header(head, body) == (head, body)


def test_coln_regex_counts_adjacent_placeholders():
    assert len(_COLN_RE.findall("|Col6|Col7|Col8|")) == 3


def test_header_quality():
    assert _header_quality("|S.No.|Activities|SS1|") == 1.0
    assert _header_quality("|Col1|Col2|Col3|Col4|") == 0.0


# ---- group rows -------------------------------------------------------------
def test_group_label_detects_a_spanning_row():
    row = "|" + "|".join(["**1.**<br>**Line & Traction Converter (MEDHA)– MC1,2**"] * 12) + "|"
    assert _group_label(row) == "1. Line & Traction Converter (MEDHA)– MC1,2"


def test_group_label_rejects_ordinary_rows():
    assert _group_label("|||1.|Check bolts.||||✓|✓|✓||") == ""
    assert _group_label("|✓|✓|✓|") == ""          # repeated, but not a label
    assert _group_label("|Only one cell|") == ""   # single column is not a span


def test_marked_label_roundtrips():
    assert _marked_label(f"|{GROUP_MARK} Wiper - DTC|||||") == "Wiper - DTC"
    assert _marked_label("|S.No.|Activities|") == ""


def test_same_table_gate():
    a = "|S.No.|Equipment|Activities|T|M|Q|SS1|SS2|SS3|"
    b = "|S.No.|Equipment|Activities|Activities|T|M|Q|SS1|SS2|SS3|Remark|"
    c = "|Station|Division|Contact number|"
    assert _same_table(a, b) is True     # same matrix, different column split
    assert _same_table(a, c) is False    # unrelated table must not inherit


def test_running_row_detected():
    repeated = {"REPORT ON SHOP SCHEDULE ACTIVITIES FOR VANDE BHARAT TRAINSET (Ver. 2)"}
    row = "|ACTIV|ITIES FOR VANDE|BHARAT TR|AINSET (Ver. 2|)|Col6|Col7|"
    assert _is_running_row(row, repeated) is True
    assert _is_running_row("|S.No.|Equipment|Activities|", repeated) is False


# ---- table splitting --------------------------------------------------------
def _rows(n, filler="x"):
    return [f"|{i}|{filler * 60}|✓|" for i in range(n)]


def test_split_table_repeats_header_and_never_splits_a_row():
    md = "\n".join(["|S.N.|Activity|SS1|", "|---|---|---|"] + _rows(80))
    pieces = _split_table(md, "Electrical")
    assert len(pieces) > 1
    for text, _ in pieces:
        assert "|S.N.|Activity|SS1|" in text
        assert len(text) <= TABLE_MAX + 200
    body = [l for text, _ in pieces for l in text.splitlines()
            if re.match(r"^\|\d+\|", l)]
    assert len(body) == len(set(body)) == 80      # every row present exactly once


def test_split_table_restates_the_group_on_every_piece():
    g = f"|{GROUP_MARK} 1. Line & Traction Converter (MEDHA)|||"
    md = "\n".join(["|S.N.|Activity|SS1|", "|---|---|---|", g] + _rows(80))
    pieces = _split_table(md, "General (Applicable to all Schedules)")
    assert len(pieces) > 1
    for text, group in pieces:
        assert group == "1. Line & Traction Converter (MEDHA)"
        # _GROUP_ROW is anchored per row, so test the rows, not the blob
        assert any(_GROUP_ROW.match(l) for l in text.splitlines()), text[:200]


def test_split_table_switches_group_midway():
    g1 = f"|{GROUP_MARK} 1. Line Converter|||"
    g2 = f"|{GROUP_MARK} 2. Auxiliary Converter|||"
    md = "\n".join(["|S.N.|Activity|SS1|", "|---|---|---|",
                    g1] + _rows(60) + [g2] + _rows(60, "y"))
    pieces = _split_table(md, "General")
    seen = [g for _, g in pieces]
    assert seen[0] == "1. Line Converter"
    assert seen[-1] == "2. Auxiliary Converter"
    # a group never reappears after the next one has started
    assert seen == sorted(seen, key=lambda s: ["1. Line Converter",
                                               "2. Auxiliary Converter"].index(s))


def test_split_table_small_table_is_one_piece():
    md = "\n".join(["|S.N.|Activity|", "|---|---|", "|1|Check bolts.|"])
    pieces = _split_table(md, "Bogie")
    assert len(pieces) == 1 and pieces[0][1] == ""


# ---- section titles ---------------------------------------------------------
def test_merge_tiny_sections_keeps_the_dissolved_title():
    """BOGIE, CTRB and Rubber Metal Bonded Items were each a ~40-char section on
    the must-change page; absorbing them deleted the only place they were named."""
    tiny = {"section": "BOGIE", "section_num": "", "page_start": 5,
            "blocks": [{"type": "text", "text": "Axle box springs.", "page": 5}]}
    host = {"section": "1. Gangway", "section_num": "1", "page_start": 5,
            "blocks": [{"type": "text", "text": "y" * 400, "page": 5}]}
    merged = merge_tiny_sections([tiny, host])
    assert len(merged) == 1
    text = " ".join(b["text"] for b in merged[0]["blocks"])
    assert "BOGIE" in text and "Axle box springs." in text


def test_merge_tiny_sections_drops_boilerplate_titles():
    tiny = {"section": "Introduction", "section_num": "", "page_start": 1,
            "blocks": [{"type": "text", "text": "Short.", "page": 1}]}
    host = {"section": "Real", "section_num": "", "page_start": 1,
            "blocks": [{"type": "text", "text": "y" * 400, "page": 1}]}
    merged = merge_tiny_sections([tiny, host])
    assert "Introduction" not in " ".join(b["text"] for b in merged[0]["blocks"])


def test_merge_tiny_sections_keeps_trailing_pending_blocks():
    """A tiny section with no host after it must not be dropped on the floor."""
    tiny = {"section": "CTRB", "section_num": "", "page_start": 9,
            "blocks": [{"type": "text", "text": "Bearing.", "page": 9}]}
    merged = merge_tiny_sections([tiny])
    assert merged and any("Bearing." in b["text"] for b in merged[0]["blocks"])


@pytest.mark.parametrize("label", ["S.No", "S.No.", "Equipment/", "Sub-Assy.",
                                   "Activities", "Maintenance Periodicity",
                                   "Remark/ Reference", "SS1", "Col12", "9 M"])
def test_column_labels_are_not_headings(label):
    assert _COLUMN_LABEL.match(label), label


@pytest.mark.parametrize("heading", ["BOGIE", "CTRB", "Speed sensors",
                                     "MUST CHANGE ITEMS FOR SHOP SCHEDULE-2",
                                     "Air suspension", "Equipment room layout"])
def test_real_headings_survive_the_column_guard(heading):
    assert not _COLUMN_LABEL.match(heading), heading


def test_page_footer_pattern():
    assert _PAGE_FOOTER.match("Page 241 of 359")
    assert _PAGE_FOOTER.match("241 of 359")
    assert not _PAGE_FOOTER.match("Page 241 of the manual covers brakes")


# ---- chunk metadata ---------------------------------------------------------
def test_columns_of_reads_the_header_not_the_group_row():
    text = ("Table — Electrical:\n"
            f"|S.No.|Equipment/<br>Sub-Assy.|Activities|SS1|SS2|SS3|\n"
            "|---|---|---|---|---|---|\n"
            f"|{GROUP_MARK} 1. Line Converter||||||\n"
            "|1||Check bolts.|✓|✓|✓|")
    assert _columns_of(text) == ["S.No.", "Equipment/ Sub-Assy.", "Activities",
                                 "SS1", "SS2", "SS3"]


def test_columns_of_text_chunk_is_empty():
    assert _columns_of("Plain prose with no table at all.") == []
