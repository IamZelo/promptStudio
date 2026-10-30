# Repository Guidelines

## Project Structure & Module Organization

- `backend/main.py` is the CLI entry point; `backend/agents.py` provides compatibility exports.
- `backend/src/` contains LangGraph orchestration (`pipeline.py`), Pydantic contracts (`schemas.py`), configuration, agent implementations, utilities, and offline mocks.
- `backend/tests/test_pipeline.py` covers orchestration, validation, and generated-file safety. Generated projects go to `backend/output/` when running from `backend/`.
- `frontend/` is a React/Vite application. Components live in `src/components/`, API and export helpers in `src/lib/`, mock streams in `src/mocks/`, and shared CSS in `src/styles/global.css`.
- The backend currently exposes a CLI; live frontend integration requires an API wrapper. Use mock mode for standalone UI development.

## Build, Test, and Development Commands

Run backend commands from `backend/`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py --mock -p "Build a note-taking CLI"
python -m pytest tests/ -q
```

These install dependencies, run an offline demo, and execute tests.

Run frontend commands from `frontend/`:

- `npm install`: install dependencies.
- `npm run dev`: start Vite at `http://localhost:5173`.
- `npm run build`: produce the production bundle in `dist/`.
- `npm run preview`: serve the built bundle locally.

## Coding Style & Naming Conventions

Use four-space indentation, snake_case functions/modules, PascalCase classes, and type annotations in Python. Use two-space indentation, double quotes, semicolons, camelCase functions, and PascalCase component filenames in JavaScript/JSX. No formatter or linter is configured; match surrounding code. Keep `frontend/src/lib/schemas.js` and consuming components aligned with changes to backend contracts.

## Testing Guidelines

Use pytest with `test_*.py` files and `test_*` functions. Prefer `tmp_path` for filesystem operations and `monkeypatch` for model clients; tests should run offline. Add regression coverage for repair routing, schema validation, and path safety. No coverage threshold or frontend test runner is configured. For UI changes, build and manually check mock streaming, file selection, preview, cancellation, and export. Pipeline syntax checks do not replace repository tests; `--run-tests` currently remains reserved for strict validation.

## Commit & Pull Request Guidelines

Existing commits use short, lowercase action summaries, such as `initialize repo`; no formal prefix scheme is established. Keep commits focused. PRs should describe behavior changes, link relevant issues, list validation commands/results, and include screenshots for UI changes.

## Security & Configuration

Copy each application's `.env.example` for local configuration. Keep Gemini keys in backend configuration; never expose secrets through `VITE_*` variables. Do not commit `.env`, generated output, virtual environments, or build artifacts. Live generation requires Gemini credentials and a running llama.cpp server.
