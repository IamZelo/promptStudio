"""Developer Agent: Context-Aware Code Generation.

Generates complete, runnable source code for individual blueprint files,
referencing previously generated files to guarantee seamless imports and signatures.
"""

from __future__ import annotations

import time
from typing import Dict, Optional
from src.schemas import ArchitectureBlueprint, FileSpec, GeneratedFile
from src.mocks.demo_data import get_mock_file

DEVELOPER_SYSTEM_INSTRUCTION = """You are a Senior Software Developer.
Your task is to implement the exact source code for a specified file according to the Architecture Blueprint.

Strict Rules:
1. Write 100% complete, working, production-grade code.
2. NEVER use placeholders like '# TODO', 'pass', or '...'. All functions, methods, and error handlers must be fully implemented.
3. STRICT INTERFACE CONSISTENCY: Always inspect the method names, parameter signatures, and return types of classes in previously generated files. Match those exact signatures when calling them from other files.
4. MODERN PYDANTIC V2 USAGE: When using Pydantic, NEVER use deprecated v1 methods like `model.json()`, `model.dict()`, or `dumps_kwargs`. ALWAYS use Pydantic v2 methods: `model.model_dump_json(indent=2)` and `model.model_dump()`.
5. REQUIREMENTS.TXT: If the file is 'requirements.txt', list EVERY third-party library imported across the project with lower-bound version specifiers (e.g., `click>=8.0.0`, `rich>=13.0.0`, `pydantic>=2.0.0`, `pytest>=7.0.0`). Do not include standard library packages.
6. USER INSTALLATION & RUN GUIDE IN README: In 'README.md', always provide a prominent, step-by-step Quickstart guide showing the user exactly how to set up a virtual environment, install dependencies (`pip install -r requirements.txt`), and execute the CLI commands with concrete examples.
7. Include clear docstrings, typing annotations, and defensive error handling.
8. If writing tests, ensure comprehensive test cases with assertions.
"""


def _format_existing_files_context(existing_files: Dict[str, str], dependencies: list[str]) -> str:
    """Builds a concise formatted summary of relevant generated files for context injection."""
    if not existing_files:
        return "None yet (this is the first file)."

    context_sections = []
    # Prioritize files in dependencies, then recent files
    for f_path, f_code in existing_files.items():
        f_lines = f_code.strip().splitlines()
        # Keep compact outline: up to 60 lines for dependencies, 30 for others
        limit = 60 if any(dep in f_path for dep in dependencies) else 30
        preview = "\n".join(f_lines[:limit])
        if len(f_lines) > limit:
            preview += f"\n# ... [omitted remaining {len(f_lines) - limit} lines for brevity] ..."
        context_sections.append(f"--- File: {f_path} ---\n{preview}")

    return "\n\n".join(context_sections[-5:])  # Limit to last 5 relevant files max


def run_developer_agent(
    client: Optional[object],
    model: str,
    blueprint: ArchitectureBlueprint,
    target_file: FileSpec,
    existing_files: Dict[str, str],
    max_retries: int = 3,
) -> GeneratedFile:
    """Invokes the Developer Agent to implement a single file based on the blueprint.

    Args:
        client: google.genai.Client instance or None (for mock simulation)
        model: Model name string (e.g. 'gemini-3.6-flash')
        blueprint: Full architectural blueprint
        target_file: The specific FileSpec to implement
        existing_files: Dict mapping relative paths to source code of files generated so far
        max_retries: Number of retries on transient API errors

    Returns:
        GeneratedFile containing the path, full code, and summary.
    """
    if client is None:
        return get_mock_file(target_file)

    from google.genai import types

    existing_context = _format_existing_files_context(existing_files, target_file.dependencies)

    prompt = f"""PROJECT OVERVIEW:
Name: {blueprint.project_name}
Summary: {blueprint.summary}
Tech Stack: {', '.join(blueprint.tech_stack)}

FULL FILE LIST IN BLUEPRINT:
{chr(10).join([f"- {f.path}: {f.description}" for f in blueprint.files])}

ALREADY IMPLEMENTED FILES IN THIS PROJECT:
{existing_context}

YOUR CURRENT ASSIGNMENT:
Generate the complete code for the file: '{target_file.path}'
Description: {target_file.description}
Dependencies: {', '.join(target_file.dependencies) if target_file.dependencies else 'None'}

Return a structured JSON matching GeneratedFile with the full, runnable code.
"""

    config = types.GenerateContentConfig(
        system_instruction=DEVELOPER_SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=GeneratedFile,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.2,
    )

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )

            if hasattr(response, "parsed") and response.parsed:
                return response.parsed

            raw_text = response.text.strip()
            return GeneratedFile.model_validate_json(raw_text)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                sleep_time = attempt * 2
                time.sleep(sleep_time)

    raise last_error
