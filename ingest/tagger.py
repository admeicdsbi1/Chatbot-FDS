"""
tagger.py — keyword-rule tagging + OEM detection per chunk.

Emits the same tag vocabulary the old KB used, because backend/rag.py boosts
'procedure'/'testing' and demotes 'overview'/'general information' at query
time, and every tag is indexed as a keyword. OEM regexes mirror
rag.detect_query_oem exactly so the x1.8 OEM boost lines up.
"""
import re

MAX_TAGS = 10

# (tag, pattern-on-text, pattern-on-section-title-or-None)
_RULES = [
    ("procedure",       re.compile(r"\bstep\s*[-–]?\s*\d|\bprocedure\b|\bfollow(ing)?\s+steps\b|^\s*\d+[.)]\s", re.I | re.M),
                        re.compile(r"procedure|method|how to|steps", re.I)),
    ("testing",         re.compile(r"\btest(ing|ed)?\b|\bcheck(ing)?\b|\bverify\b|\bmeasure\b", re.I),
                        re.compile(r"test|check", re.I)),
    ("troubleshooting", re.compile(r"\btroubleshoot|\bfault\b|\bfailure\b|\bdefect|\bremedy\b|\berror\b|not working", re.I),
                        re.compile(r"troubleshoot|fault|failure", re.I)),
    ("fault code",      re.compile(r"\b(fault|failure|error)\s*codes?\b|\bK\d{2}\b|\bcode\s*\d+\.\d\b", re.I), None),
    ("maintenance",     re.compile(r"\bmaintenance\b|\boverhaul\b|\bservicing\b", re.I),
                        re.compile(r"maintenance", re.I)),
    ("maintenance schedule", re.compile(r"\bschedule\b.{0,40}\b(maintenance|examination)|\b(daily|monthly|quarterly|yearly|trip)\s+(schedule|examination|maintenance)\b", re.I), None),
    ("installation",    re.compile(r"\binstall(ation|ed|ing)?\b|\bmounting\b|\bfitment\b", re.I), None),
    ("inspection",      re.compile(r"\binspect(ion|ed)?\b|\bvisual(ly)? check", re.I), None),
    ("safety",          re.compile(r"\bwarning\b|\bcaution\b|\bdanger\b|\bsafety\b|power\s+off|remove\s+fuse", re.I), None),
    ("overview",        None, re.compile(r"introduction|overview|scope|about|preface|foreword", re.I)),
    ("general information", None, re.compile(r"general", re.I)),
    ("technical specs", re.compile(r"\bspecificat|\brating\b|\btolerance\b|\bdimensions?\b|\b\d+\s*(V|Vdc|VDC|mA|bar|mm|kg|Hz|ohm)\b", re.I),
                        re.compile(r"specification|technical data", re.I)),
    ("wiring",          re.compile(r"\bwiring\b|\bcable\b|\bconnector\b|\bterminal\b|\bpin\s*(out|no)\b", re.I), None),
    ("power supply",    re.compile(r"\bpower\s+supply\b|\b110\s*V\b|\bbattery\s+voltage\b|\bMCB\b", re.I), None),
    ("spare parts",     re.compile(r"\bspares?\b|\bpart\s*(no|number)s?\b|\bbill of material|\bBOM\b", re.I), None),
    ("alarm levels",    re.compile(r"\balarm\s+(level|stage|threshold)|\balert\b.{0,60}\baction\b|\bobs/m\b", re.I), None),
    ("fire alarm",      re.compile(r"\bfire\s+alarm\b|\bsmoke\s+detect", re.I), None),
    ("fire suppression", re.compile(r"\bsuppression\b|\bextinguish|\bnitrogen\b|\bwater\s+mist\b|\baerosol\b", re.I), None),
    ("aerosol generator", re.compile(r"\baerosol\s+generator", re.I), None),
    ("water mist",      re.compile(r"\bwater\s+mist\b", re.I), None),
    ("dump valve",      re.compile(r"\bdump\s+valve\b|\banti[- ]?skid\s+valve\b", re.I), None),
    ("speed sensor",    re.compile(r"\bspeed\s+sensor\b|\btacho|\bTG\d\b", re.I), None),
    ("phonic wheel",    re.compile(r"\bphonic\s+wheel\b|\bpole\s+wheel\b|\btoothed\s+wheel\b", re.I), None),
    ("MMI display",     re.compile(r"\bMMI\b|\bdisplay\s+(unit|panel|reading)|\bseven\s+segment\b", re.I), None),
    ("brake cylinder",  re.compile(r"\bbrake\s+cylinder\b", re.I), None),
    ("brake valve",     re.compile(r"\bbrake\s+valve\b", re.I), None),
    ("CPU",             re.compile(r"\bCPU\b|\bprocessor\s+card\b", re.I), None),
    ("battery",         re.compile(r"\bbattery\b", re.I), None),
    ("air gap",         re.compile(r"\bair\s*gap\b", re.I), None),
    ("diagnostic software", re.compile(r"\bdiagnostic\b|\bGUI\b|\bdata\s+download\b|\blaptop\b|\bsoftware\b", re.I), None),
    ("data download",   re.compile(r"\bdata\s+(download|record|log)|\bdownload\s+(the\s+)?data\b", re.I), None),
    ("electrical fault", re.compile(r"\bshort\s+circuit\b|\bearth\s+fault\b|\belectrical\s+fault\b", re.I), None),
    ("relay",           re.compile(r"\brelay\b", re.I), None),
    ("components",      re.compile(r"\bcomponents?\b.{0,40}\b(list|description)|\bmajor\s+components\b", re.I), None),
    ("Vande Bharat",    re.compile(r"\bvande\s*bharat\b|\bamrit\s*bharat\b", re.I), None),
    ("LHB coaches",     re.compile(r"\bLHB\b", re.I), None),
    # Vande Bharat trainset vocabulary — every tag is indexed as a keyword, so
    # these are what let a depot's own wording ("CTRB", "SS-2", "RMPU") hit the
    # keyword arm of retrieval as well as the semantic one.
    ("CTRB",            re.compile(r"\bCTRB\b|cartridge\s+tapered\s+roller", re.I), None),
    ("bearing",         re.compile(r"\bbearing[s]?\b|\baxle\s*box\b", re.I), None),
    ("wheel profile",   re.compile(r"re-?profil|\bwheel\s+(diameter|turning|profile)\b|\btyre\s+defect", re.I), None),
    ("shop schedule",   re.compile(r"\bSS-?[12]\b|\bIOH\b|\bPOH\b|shop\s+schedule|\btrip\s+schedule\b", re.I), None),
    ("trainset",        re.compile(r"\btrainset\b|\brake\b\s+(of|no)|\bDTC\b|\bMC\s*car\b", re.I), None),
    ("RMPU",            re.compile(r"\bRMPU\b|\bCPA\b|roof\s+mounted", re.I), None),
    ("VCB",             re.compile(r"\bVCB\b|vacuum\s+circuit\s+breaker", re.I), None),
]

# OEM detection — query-side patterns mirror backend/rag.py detect_query_oem
_WSP_OEMS = [
    ("FAIVELEY",       re.compile(r"\bfaiveley\b|\bwabtec\b|\bAEF\b|\bSWKP\b|\bDV12\b|\bWBI\b", re.I)),
    ("KNORR BREMSE",   re.compile(r"\bknorr\b|\bbremse\b|\bMGS2\b|\bESRA\b|\bMB04\b|\bPB03\b|\bEB01\b", re.I)),
    ("ESCORTS KUBOTA", re.compile(r"\bescorts?\b|\bkubota\b|\bEKL\b", re.I)),
]
# Vande Bharat component makes. Without these every VB chunk carries oem=None, so
# rag.py's x1.8 OEM boost / x0.3 mismatch demotion never fires on a query naming a
# bearing or wheel maker — and "SKF CTRB" vs "Timken CTRB" is a real distinction in
# these letters (SKF bearings are withheld; Timken ones are not).
_VB_OEMS = [
    ("SKF",    re.compile(r"\bSKF\b", re.I)),
    ("TIMKEN", re.compile(r"\btimken\b", re.I)),
    ("NEI",    re.compile(r"\bNEI\b|\bnational\s+engineering\b", re.I)),
    ("KLW",    re.compile(r"\bKLW\b", re.I)),
    ("MEDHA",  re.compile(r"\bmedha\b", re.I)),
]
_FDSS_OEMS = [
    ("HOCHIKI",  re.compile(r"\bhochiki\b", re.I)),
    ("XTRAILIS", re.compile(r"\bxtralis\b|\bxtrailis\b|\bvesda\b", re.I)),
    ("WAGNER",   re.compile(r"\bwagner\b|\btitanus\b", re.I)),
    ("FOGTECH",  re.compile(r"\bfogtech\b", re.I)),
    ("QUARTAS",  re.compile(r"\bquartas\b", re.I)),
    ("FIREPRO",  re.compile(r"\bfirepro\b", re.I)),
    ("PYROGEN",  re.compile(r"\bpyrogen\b", re.I)),
    ("STAT-X",   re.compile(r"\bstat[- ]?x\b", re.I)),
    ("SANROK",   re.compile(r"\bsanrok\b", re.I)),
]


def tag_chunk(text, section, entry):
    """-> (tags list, oem or None)"""
    tags = []
    for tag, text_pat, sec_pat in _RULES:
        hit = (text_pat is not None and text_pat.search(text)) or \
              (sec_pat is not None and sec_pat.search(section))
        if hit:
            tags.append(tag)
        if len(tags) >= MAX_TAGS:
            break

    system = entry.get("system")
    if system == "VB":
        for t in ("Vande Bharat", "VB"):
            if t not in tags:
                tags.insert(0, t)
    elif system == "WSP" and "WSP" not in tags:
        tags.insert(0, "WSP")
    elif system == "FSDS":
        for t in ("FSDS", "FDSS"):
            if t not in tags and re.search(rf"\b{t}\b", text + " " + section):
                tags.insert(0, t)
        if "FSDS" not in tags and "FDSS" not in tags:
            tags.insert(0, "FSDS")

    oem_rules = {"WSP": _WSP_OEMS, "VB": _VB_OEMS}.get(system, _FDSS_OEMS)
    best, best_hits = None, 0
    for name, pat in oem_rules:
        hits = len(pat.findall(text))
        if hits > best_hits:
            best, best_hits = name, hits
    oem = best or entry.get("default_oem")
    if oem and oem not in tags and len(tags) < MAX_TAGS + 2:
        tags.append(oem)
    return tags[:MAX_TAGS + 2], oem
