"""load_env.py — populate os.environ from a local .env, on import.

Import this FIRST in an ingestion entry point, before doc_registry or any module
that reads configuration: doc_registry reads PDF_BUCKET_BASE at *import* time, so
a .env loaded afterwards would silently produce a KB with no download links.

    import load_env  # noqa: F401  — must precede `from doc_registry import ...`

Deliberately duplicated from backend/load_env.py rather than shared: backend/ is
what deploys to Render and must not import anything from ingest/, which is a
local-only build tool. Both are the same dozen lines; neither has logic worth
coupling the two deployables over.

Precedence is real-environment-wins (override=False), so an explicit
`GEMINI_API_KEY=... python ingest/build_kb.py` still overrides the file.
"""
import os

_LOADED = False

try:
    from dotenv import find_dotenv, load_dotenv
except ImportError:  # dotenv is optional: real environments set vars directly
    find_dotenv = load_dotenv = None


def load(verbose=False):
    """Load .env once. Returns the path used, or "" if none was found/loaded."""
    global _LOADED
    if _LOADED or load_dotenv is None:
        return ""
    _LOADED = True
    path = find_dotenv(usecwd=True)
    if path:
        load_dotenv(path, override=False)
        if verbose or os.environ.get("ENV_DEBUG"):
            print(f"load_env: loaded {path} (existing environment takes precedence)")
    return path


load()
