"""load_env.py — populate os.environ from a local .env, on import.

Import this FIRST in an entry point, before any project module: embed.py,
llm.py, stt.py and rerank.py all read os.environ at *import* time, so a .env
loaded after those imports would have no effect.

    import load_env  # noqa: F401  — must precede `import rag` etc.

Precedence is real-environment-wins (override=False). On Render the API keys come
from the dashboard, and a stale .env that happened to ship must never silently
replace them; locally there is no such environment, so the file supplies them.
The .env is searched for from the current directory upwards, so it works whether
a script is run from the repo root or from backend/.

.env is gitignored (see .env.example for the variable list). Keep real keys only
there or in the Render dashboard — never in a tracked file.
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
