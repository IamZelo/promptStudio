# PromptStudio

Create and refine software projects through a scrolling terminal chat, powered by
Gemini, llama.cpp, and the existing LangGraph pipeline. PromptStudio asks what you
want to make, shows a plan for approval, displays agent progress, and presents the
generated files and commands to run your project. Follow-up messages update the
same project; saved conversations can be resumed later.

## Start PromptStudio

From the repository root:

```bash
python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -e ./backend
promptstudio --mock
```

Without installing the console command, use
`python backend/promptstudio.py --mock` after installing `backend/requirements.txt`.
Mock mode always creates the Quicknote demonstration; follow-ups append the
request to its README rather than implementing arbitrary features.

For live generation, configure `backend/.env` from `backend/.env.example`, set
`GEMINI_API_KEY`, start your llama.cpp server, and run `promptstudio` without
`--mock`. Missing credentials produce setup instructions, not a simulated run.

```text
You > Build a simple calculator in React
... proposed architecture and file changes ...
Build this plan? [y/N] y
... Architect → Developer → QA → Critic ...
You > Add keyboard support
... proposed update to the same project ...
```

Architect plans and final file summaries use the detailed original CLI tables,
including dependencies, responsibilities, line counts, generation times, and file
summaries. During generation, output stays brief: stage updates and a live file
count. Use `promptstudio --debug` (or `promptstudio --mock --debug`) to show
per-file progress and detailed agent diagnostics.

Commands: `/help`, `/new`, `/status`, `/files`, `/show <path>`, `/retry`, `/exit`.
Empty input is ignored; Ctrl+C interrupts a run; Ctrl+D saves and exits.

Sessions are stored in `.promptstudio/sessions/` under the directory where you
launch the app. Resume **from that same directory** with
`promptstudio --resume <session-id>`. Project output defaults to `./output/`;
use `--output-dir /path/to/projects` when starting a session to change it.
External edits require explicit acceptance before an update. Failed or cancelled
updates preserve the previous published project. Source approval does not mean
application tests were executed, and generated install/run commands are displayed
for you to execute manually.

The React frontend remains available as an optional standalone mock interface.
The original `backend/main.py` and its arguments remain available for testing:

```bash
cd backend
python main.py --mock -p "Build a note-taking CLI"
python -m pytest tests/ -q
```

See [backend documentation](backend/README.md) for configuration and architecture.

---

## Pipeline Reference

A CLI-first hybrid multi-agent system where Gemini and a local llama.cpp model design, implement, validate, review, and repair software projects from natural-language requirements.

---

## 📁 Repository Organization

```
.
├── backend/                    # Python Multi-Agent AI Core & Orchestrator
│   ├── main.py                 # CLI entry point
│   ├── agents.py               # Compatibility forwarder
│   ├── requirements.txt        # Backend dependencies (google-genai, pydantic, rich, etc.)
│   ├── .env.example            # Backend environment template
│   ├── output/                 # Destination for generated software projects
│   └── src/
│       ├── config.py           # API configuration & Gemini client factory
│       ├── schemas.py          # Pydantic communication schemas
│       ├── pipeline.py         # LangGraph workflow and repair routing
│       ├── state.py            # Shared LangGraph project state
│       ├── agents/
│       │   ├── architect.py    # Architect Agent
│       │   ├── developer.py    # Local llama.cpp Developer Agent
│       │   ├── critic.py       # Gemini Critic Agent
│       │   └── qa.py           # Deterministic validation agent
│       ├── mocks/
│       │   └── demo_data.py    # Simulation/mock data for offline demos
│       └── utils/
│           ├── file_manager.py # Disk persistence
│           └── ui.py           # Rich terminal formatting & status guides
│
├── frontend/                   # Optional React/Vite interface
│   └── README.md               # Frontend roadmap and architecture notes
│
├── context.md                  # Project context and milestone tracker
├── .gitignore                  # Repository-wide ignore rules
└── README.md                   # Repository overview
```

---

## 🚀 Quickstart: Running the Backend

### 1. Enter the Backend Directory
```bash
cd backend
```

### 2. Setup Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Run in Mock Demo Mode (No API Key Required)
```bash
python main.py --mock -p "Build a markdown note-taking CLI tool"
```

### 4. Run with Live Gemini API
Configure your API key in `backend/.env`:
```env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.8-flash
LLAMA_CPP_BASE_URL=http://localhost:8080
LLAMA_CPP_MODEL=local-model
```
Then execute:
```bash
python main.py -p "Create a CLI Pomodoro timer with task tracking"
```

The live workflow expects `llama-server` to be running with your GGUF model. Add `--run-tests` to execute generated pytest suites; this is opt-in because generated tests execute generated code on your machine. Mock mode exercises the same LangGraph without external model calls.

For more detailed technical documentation on the backend agents and schemas, see [`backend/README.md`](file:///home/zelo/Documents/College/AI/Project/backend/README.md).
