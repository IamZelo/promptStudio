"""Mock data providers for offline demonstrations and dry-run simulations.

Provides high-quality realistic outputs when API keys are not provided.
"""

from __future__ import annotations

from src.schemas import ArchitectureBlueprint, FileSpec, GeneratedFile


def get_mock_blueprint(prompt: str) -> ArchitectureBlueprint:
    """Returns a realistic simulated ArchitectureBlueprint for demonstration."""
    return ArchitectureBlueprint(
        project_name="quicknote-cli",
        summary="A lightweight command-line markdown note-taking and search tool with tag management.",
        tech_stack=["Python 3.10+", "argparse", "json", "pathlib"],
        files=[
            FileSpec(
                path="quicknote/models.py",
                description="Data model for Note with id, title, tags, content, and timestamp, including JSON serialization.",
                dependencies=["dataclasses", "datetime", "typing"]
            ),
            FileSpec(
                path="quicknote/storage.py",
                description="Storage manager class to create, read, list, search, and delete notes stored as JSON.",
                dependencies=["quicknote/models.py", "pathlib", "json"]
            ),
            FileSpec(
                path="quicknote/cli.py",
                description="Command-line interface with subcommands: add, list, search, and delete.",
                dependencies=["quicknote/storage.py", "quicknote/models.py", "argparse", "sys"]
            ),
            FileSpec(
                path="quicknote/__init__.py",
                description="Package initialization exporting public classes.",
                dependencies=["quicknote/models.py", "quicknote/storage.py"]
            ),
            FileSpec(
                path="requirements.txt",
                description="List of external package dependencies with pinned versions.",
                dependencies=[]
            ),
            FileSpec(
                path="README.md",
                description="Project documentation detailing setup, installation guide, command examples, and architecture.",
                dependencies=["requirements.txt"]
            ),
        ]
    )


def get_mock_file(target_file: FileSpec) -> GeneratedFile:
    """Returns realistic mock source code for demo project components."""
    if target_file.path == "quicknote/models.py":
        code = '''"""Data models for QuickNote."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Any
import uuid


@dataclass
class Note:
    """Represents a single note in the system."""
    title: str
    content: str
    tags: List[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert note instance to dictionary for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Note":
        """Reconstruct Note instance from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            title=data.get("title", ""),
            content=data.get("content", ""),
            tags=data.get("tags", []),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )
'''
        summary = "Defined Note dataclass with UUID identifier, timestamping, and JSON serialization methods."

    elif target_file.path == "quicknote/storage.py":
        code = '''"""Persistence layer for QuickNote."""

import json
from pathlib import Path
from typing import List, Optional
from quicknote.models import Note


class NoteStorage:
    """Handles local disk storage of notes as JSON."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or (Path.home() / ".quicknote")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.data_file = self.storage_dir / "notes.json"
        self._ensure_file()

    def _ensure_file(self) -> None:
        if not self.data_file.exists():
            self.data_file.write_text("[]", encoding="utf-8")

    def _load_all(self) -> List[Note]:
        try:
            raw = json.loads(self.data_file.read_text(encoding="utf-8"))
            return [Note.from_dict(item) for item in raw]
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_all(self, notes: List[Note]) -> None:
        raw = [note.to_dict() for note in notes]
        self.data_file.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    def add_note(self, title: str, content: str, tags: List[str]) -> Note:
        """Create and persist a new note."""
        note = Note(title=title, content=content, tags=tags)
        notes = self._load_all()
        notes.append(note)
        self._save_all(notes)
        return note

    def list_notes(self) -> List[Note]:
        """Return all notes sorted by creation time descending."""
        notes = self._load_all()
        return sorted(notes, key=lambda n: n.created_at, reverse=True)

    def search_notes(self, query: str) -> List[Note]:
        """Search notes by title, content, or tags."""
        q = query.lower()
        notes = self._load_all()
        return [
            n for n in notes
            if q in n.title.lower() or q in n.content.lower() or any(q in t.lower() for t in n.tags)
        ]

    def delete_note(self, note_id: str) -> bool:
        """Delete a note by ID. Returns True if deleted, False otherwise."""
        notes = self._load_all()
        initial_len = len(notes)
        notes = [n for n in notes if n.id != note_id]
        if len(notes) < initial_len:
            self._save_all(notes)
            return True
        return False
'''
        summary = "Implemented NoteStorage with atomic JSON file persistence, search, listing, and deletion."

    elif target_file.path == "quicknote/cli.py":
        code = '''"""Command Line Interface for QuickNote."""

import argparse
import sys
from quicknote.storage import NoteStorage


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="quicknote",
        description="QuickNote: CLI Markdown note-taking and search tool"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Add command
    add_parser = subparsers.add_parser("add", help="Add a new note")
    add_parser.add_argument("title", help="Note title")
    add_parser.add_argument("content", help="Note body text")
    add_parser.add_argument("-t", "--tags", nargs="*", default=[], help="Tags for classification")

    # List command
    subparsers.add_parser("list", help="List all notes")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search notes by keyword")
    search_parser.add_argument("query", help="Search term")

    # Delete command
    del_parser = subparsers.add_parser("delete", help="Delete note by ID")
    del_parser.add_argument("id", help="Note ID to delete")

    args = parser.parse_args()
    storage = NoteStorage()

    if args.command == "add":
        note = storage.add_note(title=args.title, content=args.content, tags=args.tags)
        print(f"✓ Created note [{note.id}]: {note.title}")

    elif args.command == "list":
        notes = storage.list_notes()
        if not notes:
            print("No notes found. Run 'quicknote add' to create one.")
            return
        print(f"Found {len(notes)} note(s):")
        print()
        for n in notes:
            tags_str = f" [{', '.join(n.tags)}]" if n.tags else ""
            print(f"  • [{n.id}] {n.title}{tags_str} ({n.created_at[:10]})")
            print(f"    {n.content[:60]}...")
            print()

    elif args.command == "search":
        results = storage.search_notes(args.query)
        print(f"Search results for '{args.query}': {len(results)} match(es)")
        print()
        for n in results:
            print(f"  • [{n.id}] {n.title} - {n.content}")

    elif args.command == "delete":
        if storage.delete_note(args.id):
            print(f"✓ Deleted note [{args.id}]")
        else:
            print(f"✗ Note [{args.id}] not found", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
'''
        summary = "Implemented CLI parser with subcommands for adding, listing, searching, and deleting notes."

    elif target_file.path == "quicknote/__init__.py":
        code = '''"""QuickNote package initialization."""

from quicknote.models import Note
from quicknote.storage import NoteStorage

__version__ = "0.1.0"
__all__ = ["Note", "NoteStorage"]
'''
        summary = "Package exports and version string."

    elif target_file.path == "requirements.txt":
        code = '''# QuickNote Project Dependencies
pydantic>=2.0.0
pytest>=7.0.0
'''
        summary = "Defined project dependency specifications."

    elif target_file.path == "README.md":
        code = '''# QuickNote CLI

A modular, lightweight command-line note-taking and search tool with tag management.

## Installation & Setup Guide

Follow these steps to set up and run the application:

1. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

```bash
# Add a note
python3 -m quicknote.cli add "Project Ideas" "Explore agentic AI workflows" --tags ai productivity

# List all notes
python3 -m quicknote.cli list

# Search notes
python3 -m quicknote.cli search agentic

# Delete note
python3 -m quicknote.cli delete <id>
```

## Architecture
Built with Python 3, featuring clean separation of concerns:
- `quicknote/models.py`: Data models and JSON serialization
- `quicknote/storage.py`: Local JSON persistence and search index
- `quicknote/cli.py`: Command-line interface with argparse
- `requirements.txt`: Package dependency definitions
'''
        summary = "Created documentation with step-by-step installation guide, usage, and architecture overview."

    else:
        code = f"# Source code for {target_file.path}\n# {target_file.description}\n"
        summary = f"Generated stub for {target_file.path}"

    return GeneratedFile(
        path=target_file.path,
        code=code,
        summary=summary,
    )
