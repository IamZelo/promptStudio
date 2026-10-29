"""File management utilities for writing and persisting generated code."""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def write_file_to_disk(base_dir: Path, rel_path: str, code: str) -> Path:
    """Writes code to disk, creating parent directories if needed.

    Args:
        base_dir: Root directory of the generated project
        rel_path: Relative path of the file to write
        code: String content of the source code

    Returns:
        The resolved Path object where the file was written.
    """
    if not rel_path or Path(rel_path).is_absolute():
        raise ValueError(f"Generated file path must be relative: {rel_path!r}")

    base_path = base_dir.resolve()
    target_path = (base_path / rel_path).resolve()
    if not target_path.is_relative_to(base_path):
        raise ValueError(f"Generated file path escapes project directory: {rel_path!r}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(code, encoding="utf-8")
    return target_path


def count_lines(content: str) -> int:
    """Counts the number of lines in a text string."""
    return len(content.splitlines())


def validate_generated_content(rel_path: str, content: str, timeout: int = 10) -> None:
    """Validate a generated candidate before it can replace an existing file."""
    suffix = Path(rel_path).suffix.lower()
    if not content.strip():
        raise ValueError(f"Generated content for {rel_path} is empty")

    if suffix == ".json":
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON for {rel_path}: {exc}") from exc
        return

    if suffix == ".py":
        try:
            ast.parse(content, filename=rel_path)
        except SyntaxError as exc:
            raise ValueError(f"Invalid Python for {rel_path}: {exc}") from exc
        return

    if suffix in {".js", ".mjs", ".cjs"} and shutil.which("node"):
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=suffix, encoding="utf-8", delete=False
            ) as handle:
                handle.write(content)
                temp_path = Path(handle.name)
            result = subprocess.run(
                ["node", "--check", str(temp_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if result.returncode != 0:
                detail = (result.stdout + result.stderr).strip()
                raise ValueError(f"Invalid JavaScript for {rel_path}: {detail}")
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
