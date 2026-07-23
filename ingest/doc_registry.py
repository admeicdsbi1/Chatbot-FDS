"""
doc_registry.py — hand-written registry of the source PDFs.

doc_id values for documents already in the old KB are kept identical so chunk
provenance stays comparable across rebuilds. `system` drives the FSDS/FDSS/WSP
tags; `default_oem` stamps single-OEM manuals so rag.py's OEM boost works.
Nothing is inferred from filenames (some are WhatsApp exports).

Routing + provenance fields (added for the multi-manual scale-up — used by
retrieval routing, supersession/recency, and clause-level citation):
  coach_type : list of applicable coaches — LHB / ICF / Vande Bharat /
               Amrit Bharat / common. Drives cross-manual disambiguation.
  subsystem  : finer than `system` (e.g. "fire detection", "wheel slide
               protection", later "brakes", "bogie", "electrical", "HVAC").
  issue_date : ISO 'YYYY-MM-DD' (or 'YYYY-MM') of issue/revision — reformatted
               from `source`, NOT invented. Newest wins on a value conflict.
  revision   : document revision label as printed.
  letter_no  : circular / SMI / manual reference number, for citations.
  supersedes : doc_ids whose values this document overrides. Leave [] unless the
               supersession is explicit in the document — a mechanical engineer
               should confirm before adding, as it changes which value is quoted.
"""
import os

DOCUMENTS_ROOT = os.path.join(os.path.dirname(__file__), "..", "Documents")

# Applied by `full()` so every consumer sees the complete schema even for rows
# that omit an optional routing/provenance field.
_DEFAULTS = {
    "coach_type": [],
    "subsystem": "",
    "issue_date": "",
    "revision": "",
    "letter_no": "",
    "supersedes": [],
}

REGISTRY = [
    {
        "doc_id": "IRCAMTECH_FSDS_FDSS_Vol2",
        "path": os.path.join("FDSS", "ICF LHB FDSS  FSDS Maintenance Manual Volume-2.pdf"),
        "doc_type": "maintenance_manual",
        "title": "Maintenance Manual for FSDS and FDSS Volume-2 (LHB & ICF Coaches)",
        "source": "IRCAMTECH/GWL/M/FSDS/FDSS/1.0, October 2024",
        "system": "FSDS",
        "default_oem": None,
        "coach_type": ["LHB", "ICF"],
        "subsystem": "fire detection",
        "issue_date": "2024-10",
        "revision": "1.0",
        "letter_no": "IRCAMTECH/GWL/M/FSDS/FDSS/1.0",
    },
    {
        "doc_id": "IRCAMTECH_FSDS_FDSS_Vol1",
        "path": os.path.join("FDSS", "VB  for FDSS FSDS Maintenance Manual Volume-1.pdf"),
        "doc_type": "maintenance_manual",
        "title": "Maintenance Manual for FSDS and FDSS Volume-1 (Vande Bharat & Amrit Bharat Coaches)",
        "source": "IRCAMTECH/GWL/M/FSDS/FDSS/1.0, October 2024",
        "system": "FSDS",
        "default_oem": None,
        "coach_type": ["Vande Bharat", "Amrit Bharat"],
        "subsystem": "fire detection",
        "issue_date": "2024-10",
        "revision": "1.0",
        "letter_no": "IRCAMTECH/GWL/M/FSDS/FDSS/1.0",
    },
    {
        "doc_id": "MC_ACF_MCB_2A_Standardization",
        "path": os.path.join("FDSS", "MC ACF Fire detection AC_Standardise MCB 2A_1 10 24.pdf"),
        "doc_type": "circular",
        "title": "RDSO Circular: Standardization of 2A MCB in FSDS System",
        "source": "RDSO MC/ACF/Fire Detection/AC, 01.10.2024 & 12.08.2024",
        "system": "FSDS",
        "default_oem": None,
        "coach_type": ["common"],
        "subsystem": "fire detection",
        "issue_date": "2024-10-01",
        "revision": "",
        "letter_no": "RDSO MC/ACF/Fire Detection/AC",
        "supersedes": [],
    },
    {
        "doc_id": "MC_ACF_FSDS_Guideline",
        "path": os.path.join("FDSS", "MC ACF Fire Detection AC_PED EN HM Proj_Guideline FSDS.pdf"),
        "doc_type": "circular",
        "title": "RDSO Guideline: FSDS Fire Detection System (PED EN HM Project)",
        "source": "RDSO MC/ACF/Fire Detection/AC",
        "system": "FSDS",
        "default_oem": None,
        "coach_type": ["common"],
        "subsystem": "fire detection",
        "issue_date": "",
        "revision": "",
        "letter_no": "RDSO MC/ACF/Fire Detection/AC",
    },
    {
        "doc_id": "FSDS_Dead_Attach_Operationalisation",
        "path": os.path.join("FDSS", "Operationalisation of FSDS during dead attach movement of coaches dated 06.06.2024.pdf"),
        "doc_type": "circular",
        "title": "Operationalisation of FSDS during Dead Attach Movement of Coaches",
        "source": "Railway circular, 06.06.2024",
        "system": "FSDS",
        "default_oem": None,
        "coach_type": ["common"],
        "subsystem": "fire detection",
        "issue_date": "2024-06-06",
        "revision": "",
        "letter_no": "",
    },
    {
        "doc_id": "RDSO_Fire_Properties_Testing",
        "path": os.path.join("FDSS", "Testing of Fire Properties for coach furnishing materials dated 24.06.2022.pdf"),
        "doc_type": "circular",
        "title": "RDSO: Testing of Fire Properties for Coach Furnishing Materials",
        "source": "RDSO Lucknow MC/Testing, 24.06.2022",
        "system": "FSDS",
        "default_oem": None,
        "coach_type": ["common"],
        "subsystem": "fire properties testing",
        "issue_date": "2022-06-24",
        "revision": "",
        "letter_no": "RDSO Lucknow MC/Testing",
    },
    {
        "doc_id": "IRCAMTECH_WSP_Handbook",
        "path": os.path.join("wsp", "1469096933210-WSP Handbook CAMTECH.pdf"),
        "doc_type": "maintenance_manual",
        "title": "Handbook on Wheel Slide Protection Device (WSP)",
        "source": "IRCAMTECH/2011/Mech/WSP/1.0, August 2011",
        "system": "WSP",
        "default_oem": None,
        "coach_type": ["LHB"],
        "subsystem": "wheel slide protection",
        "issue_date": "2011-08",
        "revision": "1.0",
        "letter_no": "IRCAMTECH/2011/Mech/WSP/1.0",
    },
    {
        "doc_id": "Faiveley_AEF_G2_WSP",
        "path": os.path.join("wsp", "Faiveley FT.pdf"),
        "doc_type": "oem_manual",
        "title": "AEF G2 WSP Maintenance/Use Manual - LHB Coaches Indian Railways",
        "source": "FT0027800-003 E00 MUM Rev A01, 26/02/2019, Faiveley/Wabtec",
        "system": "WSP",
        "default_oem": "FAIVELEY",
        "coach_type": ["LHB"],
        "subsystem": "wheel slide protection",
        "issue_date": "2019-02-26",
        "revision": "A01",
        "letter_no": "FT0027800-003 E00 MUM",
    },
    {
        "doc_id": "KB_CMG_WSP_Presentation",
        "path": os.path.join("wsp", "KB WSP full.pdf"),
        "doc_type": "oem_presentation",
        "title": "Knorr-Bremse WSP Device - 14th CMG Meeting Presentation (LHB Coaches)",
        "source": "Knorr-Bremse Group, 14th CMG Meeting PURI, September 2014, Rajiv Agarwal",
        "system": "WSP",
        "default_oem": "KNORR BREMSE",
        "coach_type": ["LHB"],
        "subsystem": "wheel slide protection",
        "issue_date": "2014-09",
        "revision": "",
        "letter_no": "",
    },
    {
        "doc_id": "Escorts_Kubota_WSP_GUI",
        "path": os.path.join("wsp", "DOC-20240502-WA0048.pdf"),
        "doc_type": "oem_manual",
        "title": "Escorts Kubota WSP GUI Application Rev 4.1 - User Manual",
        "source": "Escorts Kubota Limited (Railway Equipment Division), 2024",
        "system": "WSP",
        "default_oem": "ESCORTS KUBOTA",
        "coach_type": ["LHB"],
        "subsystem": "wheel slide protection",
        "issue_date": "2024",
        "revision": "4.1",
        "letter_no": "",
    },
]


def full(entry):
    """Entry with all routing/provenance keys present (defaults applied)."""
    return {**_DEFAULTS, **entry}


def pdf_path(entry):
    return os.path.normpath(os.path.join(DOCUMENTS_ROOT, entry["path"]))


def by_id(doc_id):
    for e in REGISTRY:
        if e["doc_id"] == doc_id:
            return e
    raise KeyError(f"unknown doc_id: {doc_id}")
