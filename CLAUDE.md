# Project Context — icd-sbi-chatbot

> Bridge file: connects this project folder to the central second brain wiki.
> Generated from `second-brain/raw/PROJECT-CLAUDE-TEMPLATE.md` on 2026-09-02.

---

## Identity

**Project Name:** `icd-sbi-chatbot`
**Vault Root:** `C:\Users\icdsa\OneDrive\Desktop\Github+obsicidian`
**Project Page:** `C:\Users\icdsa\OneDrive\Desktop\Github+obsicidian\second-brain\wiki\projects\icd-sbi-chatbot.md`

Everywhere below, **Project Page** means the path above — stated once, on purpose. Do not re-inline
it into the steps: a path written in several places is one that falls out of sync, which is how six
of these seven bridge files came to point at a literal `[project-name].md` that no longer existed.

---

## Session Start Protocol

Execute silently before responding to the user's first task:

1. Read the global schema: `C:\Users\icdsa\OneDrive\Desktop\Github+obsicidian\CLAUDE.md` — it governs; this file only extends it.
2. Read **Project Page**. Load current status, architecture, open problems, session history.
   If it has a `## Pattern Proposals` section, surface those lines once (at most 3); if the user
   does not engage, drop it for the session.
3. Read the last 3 session pages named in its Session History.
4. Read `C:\Users\icdsa\OneDrive\Desktop\Github+obsicidian\second-brain\index.md` for concepts linked to this project.
5. Confirm in one line:
   > "Wiki loaded for icd-sbi-chatbot. Last session: [date] — [one-line summary]. Open threads: [list or 'none']."

If **Project Page** does not exist:
   > "No wiki page found for icd-sbi-chatbot. I'll create one at session end."

---

## Session End Protocol

Triggered by "wrap up", "end session", "close out", or task completion.

1. Write session page → `C:\Users\icdsa\OneDrive\Desktop\Github+obsicidian\second-brain\wiki\sessions\YYYY-MM-DD-[3-word-slug].md`
2. Update **Project Page**
3. Create or update concept/learning pages touched this session
4. Append to `C:\Users\icdsa\OneDrive\Desktop\Github+obsicidian\second-brain\log.md` (**newest first**, directly below the header block)
5. Update `C:\Users\icdsa\OneDrive\Desktop\Github+obsicidian\second-brain\index.md`

Confirm: "Session wrapped. Created: [...]. Updated: [...]. Log appended."

---

## Cross-Project Knowledge

Before implementing anything non-trivial, check for prior art — a concept or learning page from a
different project may already hold the answer:

- `C:\Users\icdsa\OneDrive\Desktop\Github+obsicidian\second-brain\wiki\concepts\`
- `C:\Users\icdsa\OneDrive\Desktop\Github+obsicidian\second-brain\wiki\learnings\`

If a solution from another project applies, note it under "Related" in the session page. If a new
reusable concept emerges, write the page immediately — don't defer. This is how knowledge compounds.

### Coding Behavior
Any session that writes or edits code must also read
`C:\Users\icdsa\OneDrive\Desktop\Github+obsicidian\second-brain\raw\coding-guidelines.md`.

---

## Project-Specific Context
- Stack: Next.js 14 PWA (`frontend/`, Vercel) + FastAPI (`backend/`, Render free 512MB) + in-repo ingestion (`ingest/`, PyMuPDF + Gemini-vision OCR)
- KB: `backend/data/chunks_merged.jsonl` + `embeddings.npy` are COMMITTED artifacts — always regenerate and commit them together; `GEMINI_EMBED_DIM=768` must match on Render
- LLM: gemini-3.5-flash (2.5-flash 404s for new API keys) — `thinkingBudget: 0` is required or responses come back empty
- Key constraints: must stay free (~20-30 users); Render RAM 512MB (no torch/faiss); heavy Gemini vision usage exhausts daily free quota (use gemini-3.1-flash-lite for OCR)
- Sensitive areas: `gradio/` is the retired legacy app (reference only); `Documents/` PDFs are gitignored source material — new manuals go there + `ingest/doc_registry.py`
