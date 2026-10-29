# Collaborative Multi-Agent Software Development Pipeline

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
├── frontend/                   # Web interface directory (planned Next.js / Streamlit)
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
