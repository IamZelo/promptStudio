// Offline mock event stream, mirroring backend/src/mocks/demo_data.py.
// Lets the entire frontend (agent panels, blueprint tree, code preview, export)
// be developed and demoed without a running FastAPI backend or Gemini API key.
//
// Consumers call runMockPipeline(prompt, onEvent) and receive the same event
// shapes the real SSE endpoint would emit:
//   { type: "agent_status", agent, status }
//   { type: "agent_chunk",  agent, chunk }
//   { type: "blueprint",    blueprint }
//   { type: "file_done",    file: { path, content, language } }
//   { type: "pipeline_done", readme }
//   { type: "error", message }

const MOCK_BLUEPRINT = {
  project_name: "markdown-note-cli",
  summary:
    "A command-line markdown note-taking tool with add/list/search commands, storing notes as timestamped .md files.",
  files: [
    { path: "main.py", description: "CLI entry point using argparse subcommands.", language: "python" },
    { path: "notes/store.py", description: "Note persistence: read/write/search markdown files on disk.", language: "python" },
    { path: "notes/models.py", description: "Pydantic v2 Note schema.", language: "python" },
    { path: "requirements.txt", description: "Third-party dependencies.", language: "plaintext" },
    { path: "README.md", description: "Install and run instructions.", language: "markdown" },
  ],
  requirements: ["pydantic>=2.0", "rich>=13.0"],
};

const MOCK_FILES = [
  {
    path: "notes/models.py",
    language: "python",
    content: `from datetime import datetime
from pydantic import BaseModel, Field


class Note(BaseModel):
    title: str
    body: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def to_markdown(self) -> str:
        return f"# {self.title}\\n\\n{self.body}\\n"

    def to_json(self) -> str:
        # Pydantic v2 syntax (not the deprecated .json())
        return self.model_dump_json(indent=2)
`,
  },
  {
    path: "notes/store.py",
    language: "python",
    content: `from pathlib import Path
from .models import Note

NOTES_DIR = Path("notes_data")


def save_note(note: Note) -> Path:
    NOTES_DIR.mkdir(exist_ok=True)
    slug = note.title.lower().replace(" ", "-")
    path = NOTES_DIR / f"{note.created_at:%Y%m%d%H%M%S}-{slug}.md"
    path.write_text(note.to_markdown(), encoding="utf-8")
    return path


def search_notes(query: str) -> list[Path]:
    if not NOTES_DIR.exists():
        return []
    return [p for p in NOTES_DIR.glob("*.md") if query.lower() in p.read_text().lower()]
`,
  },
  {
    path: "main.py",
    language: "python",
    content: `import argparse
from notes.models import Note
from notes.store import save_note, search_notes


def main():
    parser = argparse.ArgumentParser(prog="notecli")
    sub = parser.add_subparsers(dest="command", required=True)

    add_p = sub.add_parser("add")
    add_p.add_argument("title")
    add_p.add_argument("body")

    search_p = sub.add_parser("search")
    search_p.add_argument("query")

    args = parser.parse_args()

    if args.command == "add":
        note = Note(title=args.title, body=args.body)
        path = save_note(note)
        print(f"Saved note to {path}")
    elif args.command == "search":
        results = search_notes(args.query)
        for r in results:
            print(r)


if __name__ == "__main__":
    main()
`,
  },
  {
    path: "requirements.txt",
    language: "plaintext",
    content: `pydantic>=2.0
rich>=13.0
`,
  },
  {
    path: "README.md",
    language: "markdown",
    content: `# markdown-note-cli

## Install
\\\`\\\`\\\`bash
cd output/markdown-note-cli
pip install -r requirements.txt
\\\`\\\`\\\`

## Run
\\\`\\\`\\\`bash
python3 main.py add "My title" "My body text"
python3 main.py search "title"
\\\`\\\`\\\`
`,
  },
];

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function runMockPipeline(prompt, onEvent, { signal } = {}) {
  const check = () => {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  };

  try {
    onEvent({ type: "agent_status", agent: "architect", status: "started" });
    const architectNarration = [
      `Analyzing prompt: "${prompt}"`,
      "Decomposing requirements into modules...",
      "Drafting file structure (main.py, notes/store.py, notes/models.py)...",
      "Finalizing requirements.txt entries...",
    ];
    for (const line of architectNarration) {
      check();
      await delay(350);
      onEvent({ type: "agent_chunk", agent: "architect", chunk: line + "\n" });
    }
    check();
    await delay(300);
    onEvent({ type: "agent_status", agent: "architect", status: "done" });
    onEvent({ type: "blueprint", blueprint: MOCK_BLUEPRINT });

    onEvent({ type: "agent_status", agent: "developer", status: "started" });
    for (const file of MOCK_FILES) {
      check();
      onEvent({ type: "agent_chunk", agent: "developer", chunk: `Writing ${file.path}...\n` });
      await delay(450);
      check();
      onEvent({ type: "file_done", file });
    }
    onEvent({ type: "agent_status", agent: "developer", status: "done" });

    await delay(200);
    onEvent({
      type: "pipeline_done",
      readme: MOCK_FILES.find((f) => f.path === "README.md").content,
    });
  } catch (err) {
    if (err.name === "AbortError") return;
    onEvent({ type: "error", message: String(err) });
  }
}
