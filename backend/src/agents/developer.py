"""Developer Agent: Context-Aware Code Generation.

Generates complete, runnable source code for individual blueprint files,
referencing previously generated files to guarantee seamless imports and signatures.
"""

from __future__ import annotations

import time
import re
from pathlib import Path
from typing import Dict, Optional
from src.schemas import ArchitectureBlueprint, FileSpec, GeneratedFile
from src.mocks.demo_data import get_mock_file
from src.project_profile import infer_complexity, profile_guidance
from src.utils.file_manager import validate_generated_content
from src.utils.ui import log_warning

DEVELOPER_SYSTEM_INSTRUCTION = """You are a language-agnostic Senior Software Developer.
Your task is to implement one exact file using the language, framework, and ecosystem selected in the Architecture Blueprint.

Strict Rules:
1. Write 100% complete, working, production-grade code.
2. Never use TODOs, empty stubs, placeholder implementations, or omitted sections. Implement all declared behavior.
3. STRICT INTERFACE CONSISTENCY: Always inspect the method names, parameter signatures, and return types of classes in previously generated files. Match those exact signatures when calling them from other files.
4. Follow the selected language's idioms and the framework's current stable APIs, lifecycle, configuration, routing, dependency injection, state management, and testing conventions. Do not translate Python patterns mechanically into another language.
5. For dependency manifests, include every directly imported or tool-required third-party package using valid syntax and compatible versions. The architecture inventory is a required baseline, not a ban on necessary type packages, DOM test environments, or matcher libraries. Never list standard-library modules as dependencies.
6. For framework configuration, include all required scripts, plugins, compiler options, environment examples, and entry points. Keep secrets out of source control and use environment variables where appropriate.
7. README.md must use the blueprint's exact install and run commands and include concrete usage examples. Include a test command only when the blueprint actually plans tests.
8. Use the ecosystem's normal documentation and type system: docstrings, JSDoc, Rustdoc, JavaDoc, static types, interfaces, or equivalent where they improve maintainability.
9. When a test file is explicitly planned, use the framework's established test tooling and keep the suite focused on core requested behavior.
10. Return only the requested file. Do not wrap source code in Markdown fences inside the code field.
11. On repair, return one clean replacement for the target file. Never concatenate the previous file with a new version, duplicate test suites, or copy the contents of a reference file into the target.
12. Preserve the target file's declared export contract. Before returning a component or module, verify its default/named exports agree with every shown importer and test.
13. In Vitest files, explicitly import describe, it/test, and expect from 'vitest' unless globals are demonstrably configured. For simple projects, prefer built-in assertions such as checking an input's value; do not use jest-dom matchers unless jest-dom is declared and initialized.
14. In React event handlers, treat state setters as asynchronous and batched. Compute dependent values locally or with functional updates; never assume a setter changes the state variable later in the same handler.
15. For a Vite README, explicitly state that index.html must not be opened directly. Tell the user to run the install command, then the run command, and open the localhost URL printed by Vite.
"""


def normalize_generated_code(code: str) -> str:
    """Remove one surrounding Markdown code fence without altering inner code."""
    stripped = code.strip()
    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[0].strip().startswith("```") and lines[-1].strip() == "```":
        opening = lines[0].strip()
        if " " not in opening and opening.count("```") == 1:
            return "\n".join(lines[1:-1]).strip() + "\n"
    return code


def _target_format_constraints(
    target_file: FileSpec, blueprint: ArchitectureBlueprint
) -> str:
    if Path(target_file.path).suffix.lower() == ".json":
        return (
            "STRICT JSON REQUIREMENTS: The code value must contain raw strict JSON. Its first "
            "non-whitespace character must be '{' and its last must be '}'. Do not use Markdown "
            "fences, comments, trailing commas, JSONC, or explanatory prose."
        )
    base = (
        "The code value must contain only the literal file contents with no surrounding Markdown "
        "fence or explanatory prose."
    )
    stack = " ".join([blueprint.framework, *blueprint.tech_stack]).lower()
    if target_file.path.lower() == "index.html" and "vite" in stack:
        main_path = next(
            (spec.path for spec in blueprint.files if spec.path.lower().startswith("src/main.")),
            "src/main.jsx",
        )
        return (
            f"{base} This is a Vite entry document: it must contain the React mount element "
            f"and <script type=\"module\" src=\"/{main_path}\"></script> inside the body."
        )
    return base


def _validate_blueprint_file_contract(
    blueprint: ArchitectureBlueprint, target_file: FileSpec, code: str
) -> None:
    """Reject high-confidence framework wiring mistakes before accepting a candidate."""
    stack = " ".join([blueprint.framework, *blueprint.tech_stack]).lower()
    if target_file.path.lower() != "index.html" or "vite" not in stack:
        return
    main_path = next(
        (spec.path for spec in blueprint.files if spec.path.lower().startswith("src/main.")),
        None,
    )
    if not main_path:
        return
    script_tags = re.findall(r"<script\b[^>]*>", code, flags=re.IGNORECASE)
    if not any(
        re.search(r"\btype\s*=\s*['\"]module['\"]", tag, re.IGNORECASE)
        and (match := re.search(r"\bsrc\s*=\s*['\"]([^'\"]+)['\"]", tag, re.IGNORECASE))
        and match.group(1).lstrip("./") == main_path.lstrip("./")
        for tag in script_tags
    ):
        raise ValueError(
            f"Vite index.html must load /{main_path} with a type=\"module\" script"
        )


def _preview(value: str, limit: int = 180) -> str:
    compact = value[:limit].replace("\n", "\\n").replace("\r", "\\r")
    return compact + ("..." if len(value) > limit else "")


def _context_paths(
    blueprint: ArchitectureBlueprint,
    target_file: FileSpec,
    existing_files: Dict[str, str],
) -> list[str]:
    """Select context by dependency and acceptance relationships, never insertion order."""
    selected: list[str] = []

    def add(path: str) -> None:
        if path in existing_files and path not in selected:
            selected.append(path)

    # Repairs must always see the complete current candidate first.
    add(target_file.path)
    for path in target_file.internal_dependencies:
        add(path)
    for spec in blueprint.files:
        if target_file.path in spec.internal_dependencies:
            add(spec.path)
    target_criteria = set(target_file.implements)
    if target_criteria:
        for spec in blueprint.files:
            if target_criteria.intersection(spec.implements):
                add(spec.path)
    for spec in blueprint.files:
        if spec.file_type in {"manifest", "config"}:
            add(spec.path)
    return selected


def _format_existing_files_context(
    blueprint: ArchitectureBlueprint,
    target_file: FileSpec,
    existing_files: Dict[str, str],
    character_budget: int = 16000,
) -> str:
    """Format graph-relevant files while preserving the current target and interfaces."""
    if not existing_files:
        return "None yet (this is the first file)."

    context_sections = []
    used = 0
    for f_path in _context_paths(blueprint, target_file, existing_files):
        f_code = existing_files[f_path]
        header = f"--- File: {f_path} ---\n"
        remaining = character_budget - used - len(header)
        if remaining <= 0:
            break
        preview = f_code if len(f_code) <= remaining else f_code[:remaining] + "\n[truncated]"
        section = header + preview
        context_sections.append(section)
        used += len(section)

    return "\n\n".join(context_sections) or "No relevant implemented files yet."


def run_developer_agent(
    client: Optional[object],
    model: str,
    blueprint: ArchitectureBlueprint,
    target_file: FileSpec,
    existing_files: Dict[str, str],
    project_prompt: str = "",
    feedback: str = "",
    max_retries: int = 3,
) -> GeneratedFile:
    """Invokes the Developer Agent to implement a single file based on the blueprint.

    Args:
        client: LlamaCppClient instance or None (for mock simulation)
        model: Model alias accepted by the llama.cpp server
        blueprint: Full architectural blueprint
        target_file: The specific FileSpec to implement
        existing_files: Dict mapping relative paths to source code of files generated so far
        max_retries: Number of retries on transient API errors

    Returns:
        GeneratedFile containing the path, full code, and summary.
    """
    if client is None:
        return get_mock_file(target_file)

    existing_context = _format_existing_files_context(
        blueprint, target_file, existing_files
    )
    criteria = "\n".join(
        f"- {item.id} [{item.priority}]: {item.description} Verification: {item.verification}"
        for item in blueprint.acceptance_criteria
    ) or "None supplied."
    packages = "\n".join(
        f"- {item.name} {item.version} ({item.scope}): {item.purpose}"
        for item in blueprint.dependency_inventory
    ) or "None."
    complexity = infer_complexity(project_prompt or blueprint.original_request)

    related_specs = [
        spec for spec in blueprint.files
        if spec.path == target_file.path
        or spec.path in target_file.internal_dependencies
        or target_file.path in spec.internal_dependencies
    ]
    file_contracts = "\n".join(
        f"- {spec.path} [{spec.file_type}] imports={spec.internal_dependencies}; "
        f"exports/contract: {spec.public_contract or spec.description}"
        for spec in related_specs
    ) or f"- {target_file.path}: {target_file.public_contract or target_file.description}"

    prompt = f"""TARGET FILE (generate this path and no other): {target_file.path}

ORIGINAL USER REQUIREMENT (authoritative):
{project_prompt or blueprint.original_request}

ARCHITECTURAL CONTRACT:
Name: {blueprint.project_name}
Summary: {blueprint.summary}
Complexity Profile: {complexity}
Complexity Guidance: {profile_guidance(complexity)}
Assumptions: {chr(10).join(f'- {item}' for item in blueprint.assumptions) or 'None.'}
Functional Requirements: {chr(10).join(f'- {item}' for item in blueprint.functional_requirements) or 'None.'}
Acceptance Criteria:
{criteria}
Tech Stack: {', '.join(blueprint.tech_stack)}
Dependency Inventory:
{packages}
Primary Language: {blueprint.primary_language}
Framework: {blueprint.framework}
Package Manager: {blueprint.package_manager}
Install Command: {blueprint.install_command}
Run Command: {blueprint.run_command}
Test Command: {blueprint.test_command}

RELEVANT FILE CONTRACTS:
{file_contracts}

ALREADY IMPLEMENTED FILES IN THIS PROJECT:
{existing_context}

YOUR CURRENT ASSIGNMENT:
Generate the complete code for the file: '{target_file.path}'
Description: {target_file.description}
File Type: {target_file.file_type}
Public Contract: {target_file.public_contract}
Acceptance Criteria Implemented: {', '.join(target_file.implements) or 'None'}
Internal Dependencies: {', '.join(target_file.internal_dependencies) or 'None'}
External Dependencies: {', '.join(target_file.external_dependencies) or 'None'}
Output Constraints: {_target_format_constraints(target_file, blueprint)}

QA / CRITIC FEEDBACK TO ADDRESS:
{feedback or 'None. This is the initial implementation.'}

Repair feedback is cumulative: every listed issue is a constraint, including issues found in earlier iterations. Fix the newest issue without reintroducing any earlier one. Mentally trace the relevant user interactions after the change.
The original requirement and acceptance criteria are authoritative. Keep all files consistent with the shared repair feedback. Do not invent contradictory UI behavior or change tests to hide an implementation defect.
Before returning, verify again that the path is exactly '{target_file.path}', the content fulfills its File Type and Public Contract, contains no duplicated old/new implementation, and preserves exports used by the shown project files.

Return a structured JSON matching GeneratedFile with the full, runnable code.
"""

    last_error = None
    retry_instruction = ""
    for attempt in range(1, max_retries + 1):
        candidate_preview = ""
        raw_text = ""
        try:
            raw_text = client.generate(
                model=model,
                system=DEVELOPER_SYSTEM_INSTRUCTION,
                prompt=prompt + retry_instruction,
                schema=GeneratedFile.model_json_schema(),
            )
            generated = GeneratedFile.model_validate_json(raw_text)
            candidate_preview = _preview(generated.code)
            if generated.path != target_file.path:
                raise ValueError(
                    f"Model returned {generated.path!r}; expected exactly {target_file.path!r}"
                )
            generated.code = normalize_generated_code(generated.code)
            validate_generated_content(target_file.path, generated.code)
            _validate_blueprint_file_contract(blueprint, target_file, generated.code)
            previous_code = existing_files.get(target_file.path)
            if feedback and previous_code is not None and generated.code.strip() == previous_code.strip():
                raise ValueError(
                    "repair candidate is unchanged and does not demonstrate progress on the feedback"
                )
            return generated
        except Exception as e:
            if not candidate_preview:
                candidate_preview = _preview(raw_text)
            detail = f"{e}. Rejected preview: {candidate_preview or '<unavailable>'}"
            last_error = ValueError(detail)
            log_warning(
                f"Developer candidate rejected for {target_file.path} "
                f"(attempt {attempt}/{max_retries}): {detail}"
            )
            if attempt < max_retries:
                retry_instruction = (
                    "\n\nPREVIOUS RESPONSE REJECTED:\n"
                    f"{detail}\nRegenerate only '{target_file.path}'. The path field must match "
                    "exactly. Correct the rejected content rather than returning prose or a different file.\n"
                    f"{_target_format_constraints(target_file, blueprint)}"
                )
                sleep_time = attempt * 2
                time.sleep(sleep_time)

    raise last_error
