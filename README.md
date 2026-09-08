# Collaborative Multi-Agent Software Development Pipeline

A multi-agent AI system where specialized agents (**Architect** and **Developer**) collaborate to design, plan, and implement complete software applications from requirements.

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
│       ├── pipeline.py         # Multi-agent workflow orchestrator
│       ├── agents/
│       │   ├── architect.py    # Architect Agent
│       │   └── developer.py    # Developer Agent
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
GEMINI_MODEL=gemini-3.6-flash
```
Then execute:
```bash
python main.py -p "Create a CLI Pomodoro timer with task tracking"
```

For more detailed technical documentation on the backend agents and schemas, see [`backend/README.md`](file:///home/zelo/Documents/College/AI/Project/backend/README.md).
