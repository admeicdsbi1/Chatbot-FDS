"""
catalog.py — Browsable views over the loaded KB, and corpus-level facts.

The registry stamps every chunk with a fine-grained `subsystem` (15 values, some
holding a single chunk). That granularity is right for retrieval metadata and
wrong for navigation: nobody browses to "fire properties testing". This module
groups them into the nine areas depot staff actually think in, and derives both
the system nav and the document shelf from `rag.chunks` at request time.

Nothing is stored or duplicated — the KB is the single source of truth, so the
next ingest updates the navigation for free.
"""
import re
from collections import Counter, defaultdict

import rag

# Display group -> the registry `subsystem` values it absorbs. The empty string
# is the En-route Trouble Shooting manual (VB/SMI/E/18) plus one lifting-pad CAI:
# a train stopped in section is its own use case, not a subsystem, so it gets its
# own entry rather than being filed under "other".
SYSTEMS = [
    {
        "id": "schedules",
        "label": "Shop Schedules",
        "sublabel": "SS-1 · SS-2 · POH · daily exam",
        "icon": "clipboard-list",
        "subsystems": ["maintenance schedule"],
        "questions": [
            "What activities are covered in the SS-1 schedule for Vande Bharat?",
            "Bogie run test procedure after schedule",
            "Daily safety examination items for mechanical equipment",
            "Which rubber metal bonded components are replaced in SS-2?",
        ],
    },
    {
        "id": "fire",
        "label": "Fire Detection & Suppression",
        "sublabel": "FSDS · FDSS · aerosol · LHD",
        "icon": "flame",
        "subsystems": [
            "fire detection",
            "fire suppression",
            "fire properties testing",
        ],
        "questions": [
            "FSDS system me MCB ki rating kitni honi chahiye?",
            "Smoke test procedure for FSDS",
            "Aerosol generator pin removal guidelines",
            "FDSS fault codes and what they mean",
        ],
    },
    {
        "id": "wsp",
        "label": "Wheel Slide Protection",
        "sublabel": "WSP · dump valves · brakes",
        "icon": "disc",
        "subsystems": ["wheel slide protection", "brakes"],
        "questions": [
            "WSP self test procedure",
            "Dump valve air gap setting",
            "WSP fault codes for Faiveley AEF G2",
            "Choke sizes of dump valves in LHB coaches",
        ],
    },
    {
        "id": "electrical",
        "label": "Electrical & TCMS",
        "sublabel": "VB/SMI/E series · VCB · connectors",
        "icon": "zap",
        "subsystems": ["electrical"],
        "questions": [
            "VCB isolation procedure in Vande Bharat trainset",
            "Cycle check inspection of jumper cables",
            "Traction prohibition isolation procedure",
            "Torque value for inter-vehicle coupler",
        ],
    },
    {
        "id": "interiors",
        "label": "Doors & Interiors",
        "sublabel": "CAI series · FRP · seats · panels",
        "icon": "door-open",
        "subsystems": ["doors", "interior fittings"],
        "questions": [
            "Nosecone sealing work in DTC of Vande Bharat",
            "FRP panel rectification and cleaning procedure",
            "Provision of drain holes per coach",
            "Automatic door troubleshooting steps",
        ],
    },
    {
        "id": "hvac",
        "label": "HVAC",
        "sublabel": "RMPU · air ducts · cooling",
        "icon": "snowflake",
        "subsystems": ["HVAC"],
        "questions": [
            "Modified supply and return air ducts in Vande Bharat",
            "RMPU maintenance schedule",
            "HVAC filter cleaning interval",
        ],
    },
    {
        "id": "running-gear",
        "label": "Wheels & Bearings",
        "sublabel": "CTRB · wheel profile · axle",
        "icon": "circle-dot",
        "subsystems": ["wheels", "bearings"],
        "questions": [
            "CTRB refurbishment interval for Vande Bharat",
            "Wheel condemning diameter limit",
            "Alternative lubricant for central sleeves",
            "Wheel re-profiling criteria",
        ],
    },
    {
        "id": "bogie",
        "label": "Bogie & Air Suspension",
        "sublabel": "springs · dampers · ASDIS",
        "icon": "train-front",
        "subsystems": ["bogie", "air suspension"],
        "questions": [
            "Stabilizer bar torque value",
            "Vibration in Vande Bharat coaches after SS-1",
            "Air suspension levelling valve link length",
            "ASDIS battery specification",
        ],
    },
    {
        "id": "enroute",
        "label": "En-route Troubleshooting",
        "sublabel": "failures in section · quick isolation",
        "icon": "life-buoy",
        "subsystems": [""],
        "questions": [
            "Isolation procedure for parking brake en-route",
            "What to do if brakes do not release in section?",
            "Master controller malfunctioning troubleshooting",
            "Emergency procedure for door not closing",
        ],
    },
]

_SUB_TO_SYSTEM = {
    sub: s["id"] for s in SYSTEMS for sub in s["subsystems"]
}


def system_of(chunk):
    """Display-group id for a chunk, or None if its subsystem is unmapped."""
    return _SUB_TO_SYSTEM.get((chunk.get("subsystem") or "").strip())


def systems():
    """The nav: every system with its live chunk and document counts.

    Systems with no content are dropped rather than shown empty — if a future
    ingest removes the last HVAC document, the nav entry goes with it.
    """
    chunk_counts = Counter()
    doc_ids = defaultdict(set)
    for c in rag.chunks:
        sid = system_of(c)
        if sid is None:
            continue
        chunk_counts[sid] += 1
        doc_ids[sid].add(c.get("doc_id"))

    out = []
    for s in SYSTEMS:
        n = chunk_counts.get(s["id"], 0)
        if not n:
            continue
        out.append({
            "id": s["id"],
            "label": s["label"],
            "sublabel": s["sublabel"],
            "icon": s["icon"],
            "chunks": n,
            "documents": len(doc_ids[s["id"]]),
            "questions": s["questions"],
        })
    out.sort(key=lambda s: -s["chunks"])
    return out


# Registry doc_type -> a label a technician recognises.
_DOC_TYPE_LABELS = {
    "instruction_letter": "Instruction Letter",
    "coach_alteration_instruction": "Coach Alteration Instruction",
    "special_maintenance_instruction": "Special Maintenance Instruction",
    "maintenance_instruction": "Maintenance Instruction",
    "circular": "Circular",
    "maintenance_manual": "Maintenance Manual",
    "oem_manual": "OEM Manual",
    "oem_presentation": "OEM Presentation",
    "report": "Report",
}


def documents():
    """The reference shelf: one row per source document.

    Deduped from `rag.chunks` by `doc_id` — ~97 rows over 2,659 chunks, cheap
    enough to build per request and always consistent with what retrieval can
    actually cite. `download_url` is the R2-hosted PDF (present on every chunk).
    """
    first = {}
    counts = Counter()
    pages = defaultdict(set)
    for c in rag.chunks:
        did = c.get("doc_id")
        counts[did] += 1
        if c.get("page_num"):
            pages[did].add(c["page_num"])
        if did not in first:
            first[did] = c

    out = []
    for did, c in first.items():
        dt = c.get("doc_type") or ""
        out.append({
            "doc_id": did,
            "title": c.get("title") or did,
            "coach_type": c.get("coach_type") or [],
            "subsystem": c.get("subsystem") or "",
            "system": system_of(c),
            "doc_type": dt,
            "doc_type_label": _DOC_TYPE_LABELS.get(dt, dt.replace("_", " ").title()),
            "issue_date": c.get("issue_date") or "",
            "letter_no": c.get("letter_no") or "",
            "revision": c.get("revision") or "",
            "oem": c.get("oem") or "",
            "download_url": c.get("download_url") or "",
            "chunks": counts[did],
            "pages": len(pages[did]),
        })
    # Newest first; undated documents sort last rather than to the top.
    out.sort(key=lambda d: (d["issue_date"] or "0000", d["title"]), reverse=True)
    return out


# ================================================================
# Corpus facts — counting questions that no passage can answer
# ================================================================
# "How many CAIs have been issued for Vande Bharat?" was answered "3". The true
# figure is 27, and it appears in NO chunk text: it is the cardinality of the
# document registry. Retrieval returns at most TOP_K_FINAL chunks from at most
# that many documents, so 27 documents can never be co-present however good the
# retriever is — the model saw three CAIs and correctly reported three.
#
# The corpus does contain a plausible decoy: Annexure-I of the shop-schedule
# report ("LIST OF CAIs & TECHNICAL INSTRUCTIONS ISSUED BY ICF", pp.134-136)
# ranks first for this query but enumerates 42 rows mixing 20 CAI-numbered items
# with 22 other ICF/RDSO letters, lists A-2023/12 three times, and predates every
# 2025 CAI. Grounding on it yields a confident, citable, wrong number.
#
# So the count is computed here from the registry and passed to the LLM as an
# explicitly-labelled facts block, ALONGSIDE the retrieved passages rather than
# instead of them. It is phrased as scope ("held in this knowledge base"),
# because how many CAIs ICF has issued in total is not something this corpus
# knows — only how many it holds.

# Question shapes that ask for a cardinality. Deliberately paired with a
# document-ish noun below: "how many months between SS-1 and SS-2" is an
# interval lookup, not a corpus count, and must stay on the normal path.
_COUNT_Q = re.compile(
    r"\bhow\s+many\b|\bhow\s+much\b|\bnumber\s+of\b|\btotal\s+(?:number|count)\b"
    r"|\bcount\s+of\b|\bkitne\b|\bkitni\b|\blist\s+(?:all|the)\b|\bwhich\s+all\b",
    re.IGNORECASE,
)

# doc_type -> what a technician calls it in a question.
_DOC_TYPE_PATTERNS = {
    "coach_alteration_instruction": r"\bcai'?s?\b|\bcoach\s+alteration\b",
    "special_maintenance_instruction": r"\bsmi'?s?\b|\bspecial\s+maintenance\s+instruction",
    "instruction_letter": r"\binstruction\s+letters?\b|\brdso\s+letters?\b",
    "circular": r"\bcirculars?\b",
    "maintenance_manual": r"\bmanuals?\b",
    "report": r"\breports?\b",
    "oem_manual": r"\boem\s+manuals?\b",
}

_GENERIC_DOC = r"\bdocuments?\b|\breferences?\b|\bpdfs?\b|\binstructions?\b"

# Words that identify one of the nine display areas, so "how many documents
# cover HVAC?" is scoped to HVAC rather than answered with the whole corpus —
# a correctly-counted but wrongly-scoped number is still a wrong answer.
_STOP = {"and", "the", "of", "for", "amp", "protection", "general", "information"}
_SYSTEM_TOKENS = {
    s["id"]: {s["id"].replace("-", " ")} | {
        w for src in [s["label"]] + s["subsystems"]
        for w in re.findall(r"[a-z]{3,}", src.lower()) if w not in _STOP
    }
    for s in SYSTEMS
}


def _detect_system(query):
    """The display area a counting question is scoped to, or None for all."""
    ql = query.lower()
    for sid, tokens in _SYSTEM_TOKENS.items():
        if any(re.search(rf"\b{re.escape(t)}\b", ql) for t in tokens):
            return sid
    return None


def aggregate(doc_type=None, coach_type=None, system=None):
    """Documents matching the filters, with their count. Pure registry maths."""
    rows = documents()
    if doc_type:
        rows = [d for d in rows if d["doc_type"] == doc_type]
    if coach_type:
        rows = [d for d in rows if coach_type in (d["coach_type"] or [])
                or "common" in (d["coach_type"] or [])]
    if system:
        rows = [d for d in rows if d["system"] == system]
    return {"count": len(rows), "documents": rows}


def corpus_facts(query, coach=None):
    """A facts block for a counting question, or None if the query is not one.

    Returns (text, facts) where `facts` carries the counts so verify.py can hold
    the answer to them. Conservative by construction: it fires only when the
    query both asks for a cardinality AND names a document kind, so physical
    counts ("how many bolts", "how many coaches in a rake") never reach it.
    """
    if not _COUNT_Q.search(query or ""):
        return None

    doc_type = next((dt for dt, pat in _DOC_TYPE_PATTERNS.items()
                     if re.search(pat, query, re.IGNORECASE)), None)
    if not doc_type and not re.search(_GENERIC_DOC, query, re.IGNORECASE):
        return None                      # a count of something that is not a document

    coach = coach or rag.detect_query_coach(query)
    system = _detect_system(query)
    res = aggregate(doc_type=doc_type, coach_type=coach, system=system)
    if not res["count"]:
        return None

    label = (_DOC_TYPE_LABELS[doc_type] + " documents") if doc_type else "Documents"
    area = next((s["label"] for s in SYSTEMS if s["id"] == system), None)
    scope = "".join([f" covering {area}" if area else "",
                     f" for {coach}" if coach else ""])
    head = f"{label}{scope} held in this knowledge base: {res['count']}"

    lines = [
        "[Corpus facts — counted from the document registry, not from any page.",
        " This states what this knowledge base HOLDS. It is NOT a claim about how",
        " many have been issued in total; say so when you use it.]",
        head,
    ]
    for d in sorted(res["documents"], key=lambda d: d["letter_no"] or d["title"]):
        ref = d["letter_no"] or "(no letter no.)"
        date = rag._fmt_date(d.get("issue_date", ""))
        lines.append(f"  - {ref}{f' ({date})' if date else ''} — {d['title']}")

    return "\n".join(lines), {"count": res["count"], "doc_type": doc_type,
                              "label": label, "coach": coach}
