# Eidetix — Integrated UI + Memory Backend

This folder combines the Eidetix web UI with the uploaded HackHydra memory backend.

## Architecture

Browser → Vite → `backend_api.py` → existing `member2` HydraStorage / retrieval + existing `memory` ReasoningEngine → HydraDB.

The UI no longer uses the old demo Express memory implementation.

## Run on Windows

### 1. Install Python dependencies

```powershell
python -m pip install -r requirements.txt
```

### 2. Install Node dependencies

```powershell
npm install
```

### 3. Start both servers

```powershell
npm run dev
```

Vite prints a Local URL (usually `http://localhost:5173`, or 5174 if 5173 is busy). The Python backend listens on `http://localhost:8787`.

## HydraDB

Set these environment variables if you have a live HydraDB node:

- `HYDRA_HTTP_ADDR`
- `HYDRA_TOKEN`
- `HYDRA_NAMESPACE`
- `HYDRA_CELL_ID` (optional)

The backend performs a real HTTP probe. The UI only shows **Connected** when that probe succeeds. If HydraDB is unavailable, the repository's existing fake/in-memory storage fallback is used for development and the UI says **Not connected**.

## Main flows

- Signup / login / forgot password
- Ingest pasted AI conversations
- Ingest public conversation URLs when the page exposes readable conversation text
- Detect Qwen / ChatGPT / Claude / Gemini / Copilot
- Store conversations and messages
- Extract memories with the repository's `FactExtractor` (LLM when configured, rules otherwise)
- Write memory/session/entity relationships through the repository's HydraStorage
- Track temporal supersession with `SUPERSEDES`
- Ask Memory using the repository's `member2.retrieve` + `memory.ReasoningEngine`
- Abstain when evidence is insufficient
- Recent searches, pinned conversations, timeline, memory graph, voice input

Private/login-only AI URLs cannot be scraped without provider authorization/API support; the URL ingestor does not pretend otherwise.
