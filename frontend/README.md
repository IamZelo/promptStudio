# Frontend — Multi-Agent Coding Orchestrator

React + Vite frontend implementing the five planned features on top of the
`backend/src/pipeline.py` Architect/Developer pipeline.

## Features implemented

1. **Prompt input & template selector** — `src/components/PromptPanel.jsx`
2. **Live streaming Architect/Developer output** — `src/components/AgentStreamPanel.jsx`
   fed by `src/lib/apiClient.js` (SSE parsing)
3. **Blueprint inspector & file tree explorer** — `src/components/BlueprintInspector.jsx`,
   `src/components/FileTree.jsx`
4. **In-browser code preview with syntax highlighting** — `src/components/CodePreview.jsx`
   (Monaco Editor via `@monaco-editor/react`)
5. **Zip / local export** — `src/lib/exportProject.js` (JSZip + file-saver, or the
   File System Access API for folder export)

## Running standalone (mock mode, no backend needed)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The "Run in --mock mode" checkbox is on by
default, so the whole UI is demoable using `src/mocks/mockPipelineStream.js`
— no FastAPI backend or Gemini API key required, matching the backend's
`--mock` CLI flag philosophy.

## Wiring to the real backend

The backend currently exposes a CLI (`backend/main.py -p "..."`). To drive
this frontend for real:

1. Add a thin FastAPI wrapper around `backend/src/pipeline.py` exposing:
   - `POST /api/generate` — body `{ prompt, mock }`, response `text/event-stream`
     emitting one JSON object per SSE frame:
     `{"type": "agent_status", "agent": "architect", "status": "started"}`,
     `{"type": "agent_chunk", "agent": "architect", "chunk": "..."}`,
     `{"type": "blueprint", "blueprint": {...ArchitectureBlueprint...}}`,
     `{"type": "file_done", "file": {...GeneratedFile...}}`,
     `{"type": "pipeline_done", "readme": "..."}`.
   - `GET /api/templates` — optional; returns `[{id, label, prompt}]`. Falls
     back to a static list in `apiClient.js` if absent.
2. Copy `.env.example` to `.env` and set `VITE_API_BASE_URL` to the FastAPI
   server's URL.
3. Uncheck "Run in --mock mode" in the UI, or pass `mock: false` — this maps
   directly to the backend's `--mock` flag.

If the backend is unreachable, `apiClient.js` automatically falls back to
the local mock stream so frontend development is never blocked on backend
availability.

## Schema contract

`src/lib/schemas.js` mirrors `backend/src/schemas.py`
(`ArchitectureBlueprint`, `FileSpec`, `GeneratedFile`). Keep both in sync —
if you add/rename a Pydantic field, update the JSDoc comment and any
consuming component (`BlueprintInspector.jsx`, `FileTree.jsx`,
`CodePreview.jsx`).
