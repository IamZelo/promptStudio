"""File management utilities for writing and persisting generated code."""

from __future__ import annotations

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
    target_path = base_dir / rel_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(code, encoding="utf-8")
    return target_path


def count_lines(content: str) -> int:
    """Counts the number of lines in a text string."""
    return len(content.splitlines())
