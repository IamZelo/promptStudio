# Current Conversation Context Summary

## Project Overview
* **Project Name:** Collaborative Multi-Agent Research and Writing Assistant / Coding Project Orchestrator (Main focus: Multi-agent software development pipeline)
* **Goal:** Build an automated multi-agent system where specialized roles (Architect, Developer) collaborate to design, plan, and write code based on user prompts.

## Key Decisions & Progress
1. **Scope:** Starting with a simple 2-agent setup (Architect & Developer) using the official `google-genai` SDK (`gemini-2.5-flash`), with plans to scale up complexity (adding QA critics and feedback loops) later.
2. **Tech Stack:** Python, Google GenAI SDK, and modular script files (`agents.py`, `main.py`).
3. **Current State:** Modularized the codebase and enhanced agent instructions:
   - Separated data contracts (`src/schemas.py`), agent roles (`src/agents/architect.py`, `src/agents/developer.py`), pipeline orchestrator (`src/pipeline.py`), configuration (`src/config.py`), UI/file utilities (`src/utils/`), and mock demo data (`src/mocks/`).
   - Architect Agent is strictly instructed to always include `requirements.txt` in the blueprint.
   - Developer Agent is strictly instructed to:
     - Output accurate `requirements.txt` containing all third-party libraries.
     - Always use modern Pydantic v2 syntax (`model.model_dump_json(indent=2)` and `model.model_dump()`) instead of deprecated v1 methods.
     - Always include copy-pasteable installation & run steps in the generated `README.md`.
   - UI summary report prints a prominent, step-by-step user guide (`cd output/<project>`, `pip install -r requirements.txt`, `python3 <entrypoint>`).
   - Agent verification strictly uses `--mock` mode; live Gemini API calls are reserved for user testing.

* **`backend/main.py`**: Clean CLI entry point and execution trigger.
* **`backend/src/schemas.py`**: Strongly typed Pydantic models (`ArchitectureBlueprint`, `FileSpec`, `GeneratedFile`) defining agent communication contracts.
* **`backend/src/agents/architect.py`**: Architect Agent for requirement decomposition and file structuring.
* **`backend/src/agents/developer.py`**: Developer Agent for context-aware code synthesis.
* **`backend/src/pipeline.py`**: Workflow coordinator managing handoffs, human review, and artifact persistence.
* **`backend/src/config.py`**: Centralized environment configuration and GenAI client instantiation.
* **`backend/src/mocks/demo_data.py`**: Offline demo data provider for offline/dry-run evaluations.
* **`backend/src/utils/ui.py` & `backend/src/utils/file_manager.py`**: Terminal display and disk writing utilities.
* **`frontend/`**: Dedicated folder for the future frontend web interface.
* **`README.md`**: Monorepo overview, quickstart, and structure documentation.

## Next Milestones
1. **QA / Critic Agent**: Implement a code reviewer agent to inspect generated files for errors or code smells.
2. **Execution Feedback Loop**: Automatically run unit tests or syntax checks on generated files and feed errors back to the Developer Agent for self-healing.
3. **Web / Streamlit UI**: Optional graphical interface for project demonstration.