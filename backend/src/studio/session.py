"""Versioned local sessions and optimistic project conflict detection."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4

from pydantic import BaseModel, Field

from src.schemas import ArchitectureBlueprint, FileSpec, PipelineResult

# Runtime artifacts are preserved on disk, but are not conversation context.
IGNORED_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", "dist", "build", ".next", ".promptstudio"}


def project_hashes(root: Path) -> dict[str, str]:
    """Hash source/assets, including external additions, without following symlinks."""
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"Project directory is missing or unsafe: {root}")
    hashes = {}
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name not in IGNORED_DIRS)
        for name in dirs + names:
            path = Path(directory) / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                hashes[rel] = "symlink:" + os.readlink(path)
            elif path.is_file():
                hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))


class Session(BaseModel):
    version: int = 1
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    output_dir: str
    mock: bool = False
    messages: list[dict[str, str]] = Field(default_factory=list)
    blueprint: ArchitectureBlueprint | None = None
    files: dict[str, str] = Field(default_factory=dict)
    hashes: dict[str, str] = Field(default_factory=dict)
    project_path: str | None = None
    last_request: str | None = None
    last_outcome: dict = Field(default_factory=dict)

    def context(self) -> str:
        return "\n\n".join(
            f"{message['role'].upper()}: {message['content']}"
            for message in self.messages if message["role"] == "user"
        )

    def adopt_external(self, hashes: dict[str, str]) -> None:
        """Explicitly accept local edits; binary assets stay on disk only."""
        if self.blueprint is None or self.project_path is None:
            return
        root = Path(self.project_path)
        specs = {spec.path: spec for spec in self.blueprint.files}
        files = {}
        for path, digest in hashes.items():
            if digest.startswith("symlink:"):
                raise ValueError(f"Replace the symlink with a regular project file before updating: {path}")
            # Configuration secrets are never added to the session context.
            if Path(path).name == ".env" or Path(path).name.startswith(".env."):
                if path not in self.files:
                    continue
            try:
                with (root / path).open(encoding="utf-8", newline="") as handle:
                    content = handle.read()
            except UnicodeDecodeError:
                if path in self.files:
                    raise ValueError(f"Managed text file became binary: {path}")
                continue
            files[path] = content
            if path not in specs:
                specs[path] = FileSpec(
                    path=path,
                    description="User-added project file; preserve unless explicitly changed.",
                    public_contract="Preserve existing user-supplied contents unless the request changes this file.",
                    file_type="documentation" if path.endswith(".md") else "source",
                )
        self.files = files
        self.blueprint = self.blueprint.model_copy(update={
            "files": [spec for path, spec in specs.items() if path in files],
        })
        self.hashes = hashes

    def record(self, result: PipelineResult) -> None:
        self.last_outcome = result.model_dump(mode="json", exclude={"files", "blueprint"})
        if result.approved:
            self.blueprint = result.blueprint
            self.files = result.files
            self.project_path = result.output_path
            self.hashes = project_hashes(Path(result.output_path))
        self.messages.append({
            "role": "assistant",
            "content": f"{result.status}: {result.review.summary if result.review else '; '.join(result.errors)}",
        })


class SessionStore:
    def __init__(self, root: Path):
        self.root = root

    def path(self, session_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{12}", session_id):
            raise ValueError("Session ID must be the 12-character ID printed by PromptStudio")
        return self.root / f"{session_id}.json"

    def save(self, session: Session) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.path(session.id)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.root, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(session.model_dump_json(indent=2))
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def load(self, session_id: str) -> Session:
        data = json.loads(self.path(session_id).read_text(encoding="utf-8"))
        if data.get("version") != 1:
            raise ValueError("Unsupported session version")
        session = Session.model_validate(data)
        if session.id != session_id:
            raise ValueError("Session ID does not match its file")
        # Revalidate saved paths before they become generation or preview context.
        for path in session.files:
            FileSpec(path=path, description="Session file", file_type="source")
        return session
