"""Architect Agent: System Design and File Planning.

Analyzes user requirements to generate a structured project blueprint.
"""

from __future__ import annotations

import time
from typing import Optional
from src.schemas import ArchitectureBlueprint
from src.mocks.demo_data import get_mock_blueprint

ARCHITECT_SYSTEM_INSTRUCTION = """You are a Principal Software Architect.
Your task is to analyze user requirements and produce a clean, modular, production-ready architectural blueprint.

Guidelines:
1. Break down the system into cohesive, single-responsibility modules.
2. Keep the architecture lean, practical, and focused: design between 4 to 7 essential files total (e.g., models/storage, core business logic, cli/entrypoint, tests, requirements.txt, README.md). Avoid creating excessive micro-files.
3. Order the files logically: core utilities/models first, followed by business logic, entry point/CLI, tests, requirements.txt, and README.md.
4. Provide crisp, unambiguous descriptions for each file so that an autonomous developer agent can implement it without confusion.
5. Specify any third-party libraries needed in the tech stack.
6. MANDATORY: ALWAYS include a 'requirements.txt' file in the blueprint listing all third-party dependencies with version constraints (e.g. pydantic>=2.0.0, click>=8.0.0, rich>=13.0.0).
"""


def run_architect_agent(
    client: Optional[object],
    model: str,
    project_prompt: str,
    max_retries: int = 3,
) -> ArchitectureBlueprint:
    """Invokes the Architect Agent to generate an ArchitectureBlueprint.

    Args:
        client: google.genai.Client instance or None (for mock simulation)
        model: Model name string (e.g. 'gemini-3.6-flash')
        project_prompt: The user's specification or description of the software
        max_retries: Number of retries on transient API errors

    Returns:
        ArchitectureBlueprint containing project overview and file specifications.
    """
    if client is None:
        return get_mock_blueprint(project_prompt)

    from google.genai import types

    prompt = f"""Design a complete software project based on the following requirements:

REQUIREMENTS:
{project_prompt}

Produce a structured architectural blueprint with all necessary files (4 to 6 files total, ALWAYS including 'requirements.txt' and 'README.md'), their responsibilities, and dependencies.
"""

    config = types.GenerateContentConfig(
        system_instruction=ARCHITECT_SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=ArchitectureBlueprint,
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
            return ArchitectureBlueprint.model_validate_json(raw_text)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                sleep_time = attempt * 2
                time.sleep(sleep_time)

    raise last_error
