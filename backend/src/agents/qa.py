"""Fast, deterministic syntax validation for the demo pipeline."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from src.schemas import ArchitectureBlueprint, ValidationCheck, ValidationResult


def _run(command: list[str], project_root: Path, timeout: int, name: str) -> ValidationCheck:
    """Run one local parser without installing or executing project dependencies."""
    try:
        result = subprocess.run(
            command, cwd=project_root, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return ValidationCheck(
            name=name, passed=False, command=" ".join(command), exit_code=124,
            output=f"Syntax validation timed out after {timeout}s: {exc}",
        )
    except FileNotFoundError:
        return ValidationCheck(
            name=name, passed=False, command=" ".join(command), exit_code=127,
            output=f"Required syntax checker is not installed: {command[0]}",
        )
    return ValidationCheck(
        name=name, passed=result.returncode == 0, command=" ".join(command),
        exit_code=result.returncode,
        output=(result.stdout + result.stderr).strip() or "Syntax is valid.",
    )


def _delimiter_error(source: str) -> str | None:
    """Find common truncation in JSX/TypeScript without framework packages."""
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[tuple[str, int]] = []
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    index = 0
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
            index += 1
            continue
        if block_comment:
            if char == "*" and following == "/":
                block_comment = False
                index += 2
            else:
                index += 1
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char == "/" and following == "/":
            line_comment = True
            index += 2
            continue
        if char == "/" and following == "*":
            block_comment = True
            index += 2
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char in "([{":
            stack.append((char, index))
        elif char in ")]}":
            if not stack or stack[-1][0] != pairs[char]:
                return f"Unexpected {char!r} at character {index}."
            stack.pop()
        index += 1
    if quote:
        return f"Unterminated {quote} string."
    if block_comment:
        return "Unterminated block comment."
    if stack:
        delimiter, position = stack[-1]
        return f"Unclosed {delimiter!r} opened at character {position}."
    return None


def _source_syntax_checks(
    project_root: Path, blueprint: ArchitectureBlueprint, timeout: int
) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    node = shutil.which("node")
    lightweight_extensions = {".jsx", ".ts", ".tsx", ".css"}
    for spec in blueprint.files:
        path = project_root / spec.path
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".py":
            checks.append(_run(
                [sys.executable, "-m", "py_compile", str(path.resolve())],
                project_root, timeout, f"Python syntax: {spec.path}",
            ))
        elif suffix in {".js", ".mjs", ".cjs"}:
            if node:
                checks.append(_run(
                    [node, "--check", str(path.resolve())],
                    project_root, timeout, f"JavaScript syntax: {spec.path}",
                ))
            else:
                error = _delimiter_error(path.read_text(encoding="utf-8", errors="replace"))
                checks.append(ValidationCheck(
                    name=f"JavaScript syntax: {spec.path}", passed=error is None,
                    command="lightweight delimiter check", exit_code=0 if error is None else 1,
                    output=error or "Basic syntax structure is valid.",
                ))
        elif suffix in lightweight_extensions:
            source = path.read_text(encoding="utf-8", errors="replace")
            error = "File is empty." if not source.strip() else _delimiter_error(source)
            checks.append(ValidationCheck(
                name=f"Basic syntax: {spec.path}", passed=error is None,
                command="lightweight delimiter check", exit_code=0 if error is None else 1,
                output=error or "Basic syntax structure is valid.",
            ))
    return checks


def run_qa_agent(
    project_root: Path,
    blueprint: ArchitectureBlueprint,
    run_tests: bool,
    timeout: int,
    install_dependencies: bool = False,
) -> ValidationResult:
    """Validate syntax only; never install, build, or run app tests.

    The two execution flags remain in the signature for caller compatibility, but the
    demo QA intentionally ignores them.
    """
    del run_tests, install_dependencies
    checks: list[ValidationCheck] = []
    for spec in blueprint.files:
        if Path(spec.path).suffix.lower() != ".json":
            continue
        path = project_root / spec.path
        if not path.is_file():
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
            error = None
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            error = str(exc)
        checks.append(ValidationCheck(
            name=f"JSON syntax: {spec.path}", passed=error is None,
            command=f"parse {spec.path}", exit_code=0 if error is None else 1,
            output=error or "Valid strict JSON.",
        ))
    checks.extend(_source_syntax_checks(project_root, blueprint, timeout))
    passed = all(check.passed for check in checks if check.required)
    evidence = [
        f"[{'PASS' if check.passed else 'FAIL'}] {check.name}: {check.output}"
        for check in checks
    ]
    evidence.append(
        "[INFO] Demo QA scope is syntax only; dependency installation, builds, and tests were not run."
    )
    return ValidationResult(
        passed=passed, verified=True, command="syntax-only demo validation",
        exit_code=0 if passed else 1, output="\n".join(evidence), checks=checks,
    )
