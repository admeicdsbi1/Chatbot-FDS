# Project Context — [icd-sbi-chatbot]
> This file connects this project folder to the central second brain wiki.

---

## Identity
**Project Name:** icd-sbi-chatbot
**Project Page:** `C:\Users\icdsa\OneDrive\Desktop\Github+obsicidian\second-brain\wiki\projects\icd-sbi-chatbot.md`
**Vault Root:** `C:\Users\icdsa\OneDrive\Desktop\Github+obsicidian`

---

## Session Start Protocol
When starting a session in this project, execute these steps silently before responding:

1. Read the global schema from vault root:
   `C:\Users\icdsa\OneDrive\Desktop\Github+obsicidian\CLAUDE.md`

2. Read this project's wiki page:
   `C:\Users\icdsa\OneDrive\Desktop\Github+obsicidian\second-brain\wiki\projects\[project-name].md`
   - Load: current status, architecture, open problems, recent session history

3. Read the last 3 session pages listed in the project's Session History

4. Read the wiki index to identify any concepts linked to this project:
   `C:\Users\icdsa\OneDrive\Desktop\Github+obsicidian\second-brain\index.md`

5. Confirm to the user:
   > "Wiki loaded for [Project Name]. Last session: [date] — [one-line summary]. Open threads: [list or 'none']."

If no project page exists yet:
   > "No wiki page found for [Project Name]. I'll create one at session end."

---

## Session End Protocol
When user says "wrap up":

1. Write session page to:
   `C:\Users\icdsa\OneDrive\Desktop\Github+obsicidian\second-brain\wiki\sessions\YYYY-MM-DD-[slug].md`

2. Update project page at:
   `C:\Users\icdsa\OneDrive\Desktop\Github+obsicidian\second-brain\wiki\projects\[project-name].md`

3. Create or update any concept/learning pages touched this session

4. Append to log:
   `C:\Users\icdsa\OneDrive\Desktop\Github+obsicidian\second-brain\log.md`

5. Update index:
   `C:\Users\icdsa\OneDrive\Desktop\Github+obsicidian\second-brain\index.md`

---

## Cross-Project Knowledge
When working on this project, actively check for relevant knowledge from other projects:

- Before implementing a pattern, search concept pages for prior art:
  `C:\Users\icdsa\OneDrive\Desktop\Github+obsicidian\second-brain\wiki\concepts\`
- If a solution from another project applies here, note it in the session page under "Related"
- If a new reusable concept emerges, create a concept page immediately — don't defer

This is how knowledge compounds across projects.

---

## Project-Specific Context
- Stack: Next.js 14 PWA (`frontend/`, Vercel) + FastAPI (`backend/`, Render free 512MB) + in-repo ingestion (`ingest/`, PyMuPDF + Gemini-vision OCR)
- KB: `backend/data/chunks_merged.jsonl` + `embeddings.npy` are COMMITTED artifacts — always regenerate and commit them together; `GEMINI_EMBED_DIM=768` must match on Render
- LLM: gemini-3.5-flash (2.5-flash 404s for new API keys) — `thinkingBudget: 0` is required or responses come back empty
- Key constraints: must stay free (~20-30 users); Render RAM 512MB (no torch/faiss); heavy Gemini vision usage exhausts daily free quota (use gemini-3.1-flash-lite for OCR)
- Sensitive areas: `gradio/` is the retired legacy app (reference only); `Documents/` PDFs are gitignored source material — new manuals go there + `ingest/doc_registry.py`
