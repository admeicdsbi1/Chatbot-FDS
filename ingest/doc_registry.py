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
from urllib.parse import quote

DOCUMENTS_ROOT = os.path.join(os.path.dirname(__file__), "..", "Documents")

# Public base URL of the object-storage bucket (Cloudflare R2 / Supabase) that
# holds the source PDFs — set at build time so `download_url()` can turn each
# doc into a clickable citation. Empty (unset) => no links, citations stay text.
# Trailing slash is stripped; the per-doc key is the URL-encoded PDF basename.
PDF_BUCKET_BASE = os.environ.get("PDF_BUCKET_BASE", "").rstrip("/")

# Applied by `full()` so every consumer sees the complete schema even for rows
# that omit an optional routing/provenance field.
_DEFAULTS = {
    "coach_type": [],
    "subsystem": "",
    "issue_date": "",
    "revision": "",
    "letter_no": "",
    "supersedes": [],
    # force_ocr: the PDF's native text is corrupted (bad font encoding), so ignore
    # it and build the doc purely from OCR. Set True only for such docs.
    "force_ocr": False,
    # download_url: filled by build_kb via download_url(entry) so each chunk
    # carries a link to its source PDF. Empty when PDF_BUCKET_BASE is unset.
    "download_url": "",
}

REGISTRY = [
    {
        "doc_id": "IRCAMTECH_FSDS_FDSS_Vol2",
        "path": os.path.join("Fire system", "Manual", "ICF LHB FDSS  FSDS Maintenance Manual Volume-2.pdf"),
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
        "path": os.path.join("Fire system", "Manual", "VB  for FDSS FSDS Maintenance Manual Volume-1.pdf"),
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
        "path": os.path.join("Fire system","MC ACF Fire detection AC_Standardise MCB 2A_1 10 24.pdf"),
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
        "path": os.path.join("Fire system","MC ACF Fire Detection AC_PED EN HM Proj_Guideline FSDS.pdf"),
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
        "path": os.path.join("Fire system","Operationalisation of FSDS during dead attach movement of coaches dated 06.06.2024.pdf"),
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
        "path": os.path.join("Fire system","Testing of Fire Properties for coach furnishing materials dated 24.06.2022.pdf"),
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

    # ── Fire-system circulars / instructions added 2026-07 ───────────────────
    # Titles/letter_no for SCANNED docs are best-effort until OCR confirms the
    # cover page — a mechanical engineer should verify the (*) fields.
    {
        "doc_id": "FDSS_Pantry_Power_Functionality_2024",
        "path": os.path.join("Fire system", "Functionality of automatic FDSS fitted in Pantry & Power cars dated 06.06.2024.pdf"),
        "doc_type": "circular",
        "title": "Functionality of Automatic FDSS fitted in Pantry & Power Cars",
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
        "doc_id": "FDSS_Guidelines_22001_Amend1_2024",
        "path": os.path.join("Fire system", "Guidlines of FDSS as per 22001_Amendment 1_PED EnHM_30 11 24.pdf"),
        "doc_type": "circular",
        "title": "RDSO Guidelines for FDSS Upgradation — Amendment-1 of IS/RDSO/CG/S/22001 (Pantry Cars & Generator-cum-Brake Vans, ICF & LHB)",
        "source": "RDSO MC/ACF/Fire Supprn/PC, 29.11.2024",
        "system": "FSDS",
        "default_oem": None,
        "coach_type": ["ICF", "LHB"],
        "subsystem": "fire detection",
        "issue_date": "2024-11-29",
        "revision": "Amendment 1",
        "letter_no": "MC/ACF/Fire Supprn/PC",
    },
    {
        "doc_id": "FDSS_PowerSupply_GaribRath",
        "path": os.path.join("Fire system", "letter to ZRs_Power supply for Garib Rath.pdf"),
        "doc_type": "circular",
        "title": "Letter to ZRs: Power Supply for FDSS in Garib Rath Coaches",
        "source": "RDSO MC/ACF/Fire Detection/AC (letter to ZRs)",
        "system": "FSDS",
        "default_oem": None,
        "coach_type": ["common"],
        "subsystem": "fire detection",
        "issue_date": "",
        "revision": "",
        "letter_no": "MC/ACF/Fire Detection/AC",
    },
    {
        "doc_id": "MC_ACF_Impl_Modification_2025",
        "path": os.path.join("Fire system", "MC ACF Fire Detection AC to PCMEs_Implementation modification dated 04.02.2025.pdf"),
        "doc_type": "circular",
        "title": "RDSO to PCMEs: Implementation Modification of FSDS Fire Detection",
        "source": "RDSO MC/ACF/Fire Detection/AC, 04.02.2025",
        "system": "FSDS",
        "default_oem": None,
        "coach_type": ["common"],
        "subsystem": "fire detection",
        "issue_date": "2025-02-04",
        "revision": "",
        "letter_no": "MC/ACF/Fire Detection/AC",
        # newest FSDS instruction here — recency tie-break makes it govern on
        # value conflicts; add explicit supersedes[] once the change is confirmed.
        "supersedes": [],
        # native text is corrupted-font mojibake (verified via KB audit) — OCR it
        "force_ocr": True,
    },
    {
        "doc_id": "MC_ACF_PowerSupply_MCB",
        "path": os.path.join("Fire system", "MC ACF Fire Detection AC_PCMEs_Power supply MCB.pdf"),
        "doc_type": "circular",
        "title": "RDSO to PCMEs: Power Supply MCB for FSDS Fire Detection",
        "source": "RDSO MC/ACF/Fire Detection/AC",
        "system": "FSDS",
        "default_oem": None,
        "coach_type": ["common"],
        "subsystem": "fire detection",
        "issue_date": "",
        "revision": "",
        "letter_no": "MC/ACF/Fire Detection/AC",
    },
    {
        "doc_id": "FSDS_Overheated_Wire_Test_2024",
        "path": os.path.join("Fire system", "over heated wire test for FSDS fitted in IR AC Coaches dated 13.06.2024.pdf"),
        "doc_type": "circular",
        "title": "Over-heated Wire Test for FSDS fitted in IR AC Coaches",
        "source": "Railway circular, 13.06.2024",
        "system": "FSDS",
        "default_oem": None,
        "coach_type": ["common"],
        "subsystem": "fire detection",
        "issue_date": "2024-06-13",
        "revision": "",
        "letter_no": "",
    },
    {
        "doc_id": "FSDS_Compliance_RDSO2008CG04_2024",
        "path": os.path.join("Fire system", "5. Compliance of RDSO specification no. RDSO2008CG-04 and guidelines for FSDS system dated 27.11.2024.pdf"),
        "doc_type": "circular",
        "title": "RDSO: Compliance of Specification RDSO/2008/CG-04 & FSDS Guidelines (MCB / control supply from TB X1 of SBC)",
        "source": "RDSO MC/ACF/Fire Detection/AC, 27.11.2024 (spec RDSO/2008/CG-04)",
        "system": "FSDS",
        "default_oem": None,
        "coach_type": ["LHB"],
        "subsystem": "fire detection",
        "issue_date": "2024-11-27",
        "revision": "",
        "letter_no": "MC/ACF/Fire Detection/AC",
    },
    {
        "doc_id": "FSDS_Aerosol_Pin_Removal_2023",
        "path": os.path.join("Fire system", "Aerosol Pin removal guidelines 07-02-2023.pdf"),
        "doc_type": "circular",
        "title": "Aerosol Pin Removal Guidelines (FSDS Aerosol Generator)",
        "source": "RDSO EL/7.1.108/MSSBC, 07.02.2023",
        "system": "FSDS",
        "default_oem": None,
        "coach_type": ["common"],
        "subsystem": "fire suppression",
        "issue_date": "2023-02-07",
        "revision": "",
        "letter_no": "EL/7.1.108/MSSBC",
    },
    {
        "doc_id": "CAI_RCF_MECH_LHB_064",
        "path": os.path.join("Fire system", "CAI_RCF_MECH_LHB_064.pdf"),
        "doc_type": "maintenance_instruction",
        "title": "RCF Coach Alteration Instruction CAI/RCF/MECH/LHB/064: Locking of Isolating Cock, Aspiration Fire Detection (LHB AC Coaches)",
        "source": "RCF Kapurthala CAI/RCF/MECH/LHB/064 (No. MD46111), 22.05.2024",
        "system": "FSDS",
        "default_oem": None,
        "coach_type": ["LHB"],
        "subsystem": "fire detection",
        "issue_date": "2024-05-22",
        "revision": "",
        "letter_no": "CAI/RCF/MECH/LHB/064",
    },

    # ── RDSO WSP instruction letters (Documents/wsp/Instruction letter) ───────
    # All 13 are scans whose *native* text layer is a lossy scanner-OCR: it
    # duplicates whole pages (doc 6: 32% repeated shingles), detaches table
    # values from their column headers (doc 8's AEFG2 choke table), garbles the
    # very numbers these letters exist to fix ("0.9 to l.4mm" / "0.9 to 1,4mm"
    # in the air-gap letter), and leaves the vector-drawn wiring annexures of
    # RDSO_WSP_Wrong_Connections_2019 at ~10 chars/page. So every one of them is
    # force_ocr — re-transcribed by Gemini vision rather than trusted. See
    # SME-verify note below: (*) fields are read off the scan, not a text layer.
    {
        "doc_id": "RDSO_WSP_AirGap_SpeedSensor_2012",
        "path": os.path.join("wsp", "Instruction letter",
                             "20-Air Gap setting between phonic wheel and WSP speed sensor dated 15_02_2012.pdf"),
        "doc_type": "instruction_letter",
        "title": "RDSO: Air Gap Setting between Phonic Wheel and WSP Speed Sensor — standardised 0.9–1.4 mm for both makes",
        "source": "RDSO MC/LHB/Brake, 15.02.2012",
        "system": "WSP",
        "default_oem": None,
        "coach_type": ["LHB"],
        "subsystem": "wheel slide protection",
        "issue_date": "2012-02-15",
        "revision": "",
        "letter_no": "MC/LHB/Brake",
        "force_ocr": True,
    },
    {
        "doc_id": "RDSO_WSP_FT_Equipment_Approval_2016",
        "path": os.path.join("wsp", "Instruction letter",
                             "23-Wheel Slide protection (WSP) Equipment of FT make for LHB Coaches dated-17_03_2016.pdf"),
        "doc_type": "instruction_letter",
        "title": "RDSO: Wheel Slide Protection (WSP) Equipment of Faiveley Transport make for LHB Coaches (AEFG2 approval)",
        "source": "RDSO MC/LHB/Brake, 17.03.2016",
        "system": "WSP",
        "default_oem": "FAIVELEY",
        "coach_type": ["LHB"],
        "subsystem": "wheel slide protection",
        "issue_date": "2016-03-17",
        "revision": "",
        "letter_no": "MC/LHB/Brake",
        "force_ocr": True,
    },
    {
        "doc_id": "RDSO_WSP_Performance_Feedback_2017",
        "path": os.path.join("wsp", "Instruction letter",
                             "27-Performance of WSP in LHB Coaches dated 12_07_2017.pdf"),
        "doc_type": "instruction_letter",
        "title": "RDSO: Performance of WSP in LHB Coaches — failure-reporting proforma (Annexure-I)",
        "source": "RDSO MC/LHB/Brake, 12.07.2017",
        "system": "WSP",
        "default_oem": None,
        "coach_type": ["LHB"],
        "subsystem": "wheel slide protection",
        "issue_date": "2017-07-12",
        "revision": "",
        "letter_no": "MC/LHB/Brake",
        "force_ocr": True,
    },
    {
        "doc_id": "RDSO_WSP_Maintenance_2018",
        "path": os.path.join("wsp", "Instruction letter",
                             "30- Maintenance of WSP of LHB Coaches dated-15_01_2018.pdf"),
        "doc_type": "instruction_letter",
        "title": "RDSO: Maintenance of WSP of LHB Coaches — reiterated maintenance instructions",
        "source": "RDSO MC/LHB/Brake, 15.01.2018",
        "system": "WSP",
        "default_oem": None,
        "coach_type": ["LHB"],
        "subsystem": "wheel slide protection",
        "issue_date": "2018-01-15",
        "revision": "",
        "letter_no": "MC/LHB/Brake",
        "force_ocr": True,
    },
    {
        "doc_id": "RDSO_WSP_Choke_Sizes_DumpValve_2018",
        "path": os.path.join("wsp", "Instruction letter",
                             "6- Modification in choke sizes of Dump Valves of WSP system in LHB coaches dated-19_11_2018.pdf"),
        "doc_type": "instruction_letter",
        "title": "RDSO: Modification in Choke Sizes of Dump Valves of WSP System in LHB Coaches (charging choke 9 mm, exhaust 'No Choke')",
        "source": "RDSO MC/LHB/Brake, 19.11.2018 (ref CRR report RDSO/CG/CRR-18002)",
        "system": "WSP",
        "default_oem": None,
        "coach_type": ["LHB"],
        "subsystem": "wheel slide protection",
        "issue_date": "2018-11-19",
        "revision": "",
        "letter_no": "MC/LHB/Brake",
        # NOT marked as superseded by the 2019 choke letters: the 15.04.2019
        # letter they cite is not in Documents/, so the supersession chain can't
        # be read end-to-end here. Recency tie-break already prefers the 2019
        # letters on a value clash. SME to confirm before hard-coding it.
        "supersedes": [],
        "force_ocr": True,
    },
    {
        "doc_id": "RDSO_WSP_Revised_Wiring_Scheme_2019",
        "path": os.path.join("wsp", "Instruction letter",
                             "7- Revised wiring scheme for WSP system of LHB Coaches_ dated-27_02_2019.pdf"),
        "doc_type": "instruction_letter",
        "title": "RDSO: Revised Wiring Scheme for WSP System of LHB Coaches — modified junction box drawing CG-19005 Alt.1 (6 JB → 4 JB)",
        "source": "RDSO MC/LHB/Brake, 27.02.2019",
        "system": "WSP",
        "default_oem": None,
        "coach_type": ["LHB"],
        "subsystem": "wheel slide protection",
        "issue_date": "2019-02-27",
        "revision": "",
        "letter_no": "MC/LHB/Brake",
        "force_ocr": True,
    },
    {
        "doc_id": "RDSO_WSP_Choke_Sizes_AEFG2_2019",
        "path": os.path.join("wsp", "Instruction letter",
                             "8-Choke sizes for AEFG2 model of WSP (Ms Faiveley Transport make) for LHB Coaches_ dated 10_06_19.pdf"),
        "doc_type": "instruction_letter",
        "title": "RDSO: Choke Sizes for AEFG2 Model of WSP (Faiveley Transport make) for LHB Coaches — Dump Valve DV12",
        "source": "RDSO MC/LHB/Brake, 10.06.2019 (ref even no. 15.04.2019)",
        "system": "WSP",
        "default_oem": "FAIVELEY",
        "coach_type": ["LHB"],
        "subsystem": "wheel slide protection",
        "issue_date": "2019-06-10",
        "revision": "",
        "letter_no": "MC/LHB/Brake",
        "supersedes": [],
        "force_ocr": True,
    },
    {
        "doc_id": "RDSO_WSP_SpeedSensor_Numbering_2019",
        "path": os.path.join("wsp", "Instruction letter",
                             "9-Standardization of numbering for speed sensors in LHB dated 25_07_19.pdf"),
        "doc_type": "instruction_letter",
        "title": "RDSO: Standardization of Numbering for WSP Speed Sensors in LHB Coaches (SS-1..SS-4, axle numbering from brake panel)",
        "source": "RDSO MC/LHB/Brake, 25.07.2019",
        "system": "WSP",
        "default_oem": None,
        "coach_type": ["LHB"],
        "subsystem": "wheel slide protection",
        "issue_date": "2019-07-25",
        "revision": "",
        "letter_no": "MC/LHB/Brake",
        "force_ocr": True,
    },
    {
        "doc_id": "RDSO_WSP_Electrical_Integrity_2019",
        "path": os.path.join("wsp", "Instruction letter",
                             "12-Ensuring Integrity of electrical connections of WSP System dated 27.09.2019.pdf"),
        "doc_type": "instruction_letter",
        "title": "RDSO: Ensuring Integrity of Electrical Connections of WSP System (intermittent short-circuit / broken-cable faults)",
        "source": "RDSO MC/LHB/Brake, 27.09.2019",
        "system": "WSP",
        "default_oem": None,
        "coach_type": ["LHB"],
        "subsystem": "wheel slide protection",
        "issue_date": "2019-09-27",
        "revision": "",
        "letter_no": "MC/LHB/Brake",
        "force_ocr": True,
    },
    {
        "doc_id": "RDSO_WSP_Wrong_Connections_2019",
        "path": os.path.join("wsp", "Instruction letter",
                             "13-Wheel Shelling-Wrong electrical connections in WSP system of LHB Coaches. dated 17.12.2019.pdf"),
        "doc_type": "instruction_letter",
        "title": "RDSO: Wheel Shelling — Wrong Electrical Connections in WSP System of LHB Coaches (sleep mode after 15–20 min; wiring diagrams Annexure A–F)",
        "source": "RDSO MC/LHB/Brake, 17.12.2019 (19th CMG)",
        "system": "WSP",
        "default_oem": None,
        "coach_type": ["LHB"],
        "subsystem": "wheel slide protection",
        "issue_date": "2019-12-17",
        "revision": "",
        "letter_no": "MC/LHB/Brake",
        "force_ocr": True,
    },
    {
        "doc_id": "RDSO_WSP_SpeedSensor_FS01A_2020",
        "path": os.path.join("wsp", "Instruction letter",
                             "39-Issue of procurement of Speed Sensor FS01A Ms Knorr-Bremse make WSP system of LHB dated-04_03_2020.pdf"),
        "doc_type": "instruction_letter",
        "title": "RDSO: Procurement of Speed Sensor FS01A (Knorr-Bremse make) for WSP System of LHB Coaches — Part No. STN 31450/250A18U, UIC 541-05 Appendix F3",
        "source": "RDSO MC/LHB/Brake, 04.03.2020",
        "system": "WSP",
        "default_oem": "KNORR BREMSE",
        "coach_type": ["LHB"],
        "subsystem": "wheel slide protection",
        "issue_date": "2020-03-04",
        "revision": "",
        "letter_no": "MC/LHB/Brake",
        "force_ocr": True,
    },
    {
        "doc_id": "RDSO_WSP_CB12_Card_Config_2024",
        "path": os.path.join("wsp", "Instruction letter",
                             "Letter to PUS_WSP CB-12 Card Configure_dated 03.05.2024.pdf"),
        "doc_type": "instruction_letter",
        "title": "RDSO to PUs: Configuring of CB-12 Card in Knorr-Bremse (KBI) make WSP — required for error/event data logging",
        "source": "RDSO MC/LHB/Brake, 03.05.2024",
        "system": "WSP",
        "default_oem": "KNORR BREMSE",
        "coach_type": ["LHB"],
        "subsystem": "wheel slide protection",
        "issue_date": "2024-05-03",
        "revision": "",
        "letter_no": "MC/LHB/Brake",
        "force_ocr": True,
    },
    {
        "doc_id": "RDSO_WSP_Junction_Box_Installation_2024",
        "path": os.path.join("wsp", "Instruction letter",
                             "RDSO letter dated 21.05.2024_Junction Box.pdf"),
        "doc_type": "instruction_letter",
        "title": "RDSO: Standardised Installation of WSP Junction Box & Speed Sensor in LHB Coaches (installation method, cable routing)",
        "source": "RDSO MC/LHB/Brake, 21.05.2024 (ref 27.02.2019 & 08.05.2024)",
        "system": "WSP",
        "default_oem": None,
        "coach_type": ["LHB"],
        "subsystem": "wheel slide protection",
        "issue_date": "2024-05-21",
        "revision": "",
        "letter_no": "MC/LHB/Brake",
        # newest WSP instruction in the KB — recency tie-break makes it govern on
        # installation-method conflicts with the 2019 wiring-scheme letter.
        "supersedes": [],
        "force_ocr": True,
    },
]


def full(entry):
    """Entry with all routing/provenance keys present (defaults applied)."""
    return {**_DEFAULTS, **entry}


def pdf_path(entry):
    return os.path.normpath(os.path.join(DOCUMENTS_ROOT, entry["path"]))


def blob_key(entry):
    """Object-storage key for a doc: its Documents-relative path with forward
    slashes (preserves the subfolder structure and keeps keys unique across docs
    that share a basename). Used both to build the URL and by upload_pdfs.py."""
    return entry["path"].replace(os.sep, "/").replace("\\", "/")


def download_url(entry):
    """Public URL of the source PDF, or "" when PDF_BUCKET_BASE is unset. Each
    path segment is URL-encoded (the PDFs have spaces), '/' preserved so the
    bucket mirrors Documents/."""
    if not PDF_BUCKET_BASE:
        return ""
    return f"{PDF_BUCKET_BASE}/{quote(blob_key(entry), safe='/')}"


def by_id(doc_id):
    for e in REGISTRY:
        if e["doc_id"] == doc_id:
            return e
    raise KeyError(f"unknown doc_id: {doc_id}")
