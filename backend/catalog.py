"""
catalog.py — Browsable views over the loaded KB.

The registry stamps every chunk with a fine-grained `subsystem` (15 values, some
holding a single chunk). That granularity is right for retrieval metadata and
wrong for navigation: nobody browses to "fire properties testing". This module
groups them into the nine areas depot staff actually think in, and derives both
the system nav and the document shelf from `rag.chunks` at request time.

Nothing is stored or duplicated — the KB is the single source of truth, so the
next ingest updates the navigation for free.
"""
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
