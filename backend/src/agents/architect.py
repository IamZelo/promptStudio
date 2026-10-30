"""Architect Agent: System Design and File Planning.

Analyzes user requirements to generate a structured project blueprint.
"""

from __future__ import annotations

import time
from typing import Optional
from src.schemas import ArchitectureBlueprint, FileSpec
from src.mocks.demo_data import get_mock_blueprint
from src.project_profile import infer_complexity, profile_guidance

ARCHITECT_SYSTEM_INSTRUCTION = """You are a language-agnostic Principal Software Architect.
Your task is to analyze user requirements and produce a fit-for-purpose blueprint whose complexity is proportional to the request.

Guidelines:
1. Infer the best ecosystem from the request. Honor any language, framework, runtime, database, or deployment constraints explicitly requested by the user.
2. If the user leaves the stack open, choose a mature, well-supported framework that fits the product instead of defaulting automatically to Python.
3. Set primary_language, framework, package_manager, install_command, run_command, and test_command to mutually compatible values.
4. Use the ecosystem's canonical project layout and dependency manifest: package.json for Node, pyproject.toml or requirements.txt for Python, Cargo.toml for Rust, go.mod for Go, pom.xml/build.gradle for Java, composer.json for PHP, and equivalent native conventions elsewhere.
5. Include framework bootstrap/configuration files required for the project to actually run. Never mix manifests, commands, syntax, or conventions from different ecosystems.
6. Convert the request into explicit functional_requirements and stable, observable acceptance_criteria. Record every product decision made to resolve ambiguity in assumptions; do not leave UI labels, state transitions, edge cases, or error behavior for the Developer to invent.
7. Break the system into cohesive modules and explicit interfaces. Every FileSpec must define public_contract, exact internal_dependencies (blueprint paths only), external_dependencies (dependency_inventory names only), and the acceptance criterion IDs it implements or verifies.
8. Plan a focused but complete project, normally 4 to 12 files, and include README.md. Automated tests are optional in the demo workflow and should be omitted unless the user explicitly asks for them. Every must-level acceptance criterion must be implemented by a non-test file; the Critic performs lightweight semantic review.
9. Order files by dependency: manifests/configuration and domain contracts first, implementations next, entry points and tests after their dependencies, then documentation. Internal dependencies must appear earlier than their consumers.
10. Select compatible package versions and list every third-party package in dependency_inventory. The generated native manifest must be responsible for exactly that inventory.
11. Provide non-interactive typecheck_command and build_command when the selected ecosystem supports them. If tests are planned, their command must terminate after one run and must not use watch mode. Otherwise use an empty test_command.
12. Keep the project CLI, service, library, or application shape requested by the user; do not introduce a web frontend unless requested.
13. Treat public_contract as mandatory for every manifest, configuration, source, and test file. A test file's implements list must cover every must-level criterion it verifies.
14. For a Vite project, always include root index.html, package.json, the framework plugin/configuration, and src/main.*. The index.html contract must explicitly require both the root mount element and a body script with type="module" whose src is the exact /src/main.* path. The package manifest FileSpec.external_dependencies must contain every dependency_inventory package because it owns their installation.
15. Respect the supplied complexity profile. For a simple project, choose the smallest conventional structure, prefer JavaScript unless TypeScript was explicitly requested, and do not introduce custom hooks, service layers, state libraries, or speculative features merely to appear modular.
16. Do not add Vitest, Testing Library, jsdom, jest-dom, test setup files, or test files to a simple UI demo unless the user explicitly requests automated tests.
17. For a simple calculator request, define basic arithmetic as one binary operation followed by equals. Treat chained operations, expression parsing, keyboard input, memory keys, and scientific functions as out of scope unless explicitly requested. This keeps the acceptance contract small and prevents later agents from inventing requirements.
18. For Vite project documentation, require a prominent warning that source approval does not install dependencies and that users must not open index.html directly; they must run the install and development commands and use Vite's localhost URL.
"""


def complete_blueprint_metadata(
    blueprint: ArchitectureBlueprint,
    project_prompt: str,
) -> ArchitectureBlueprint:
    """Fill safe structural metadata without inventing application behavior."""
    files = list(blueprint.files)
    stack = " ".join([blueprint.framework, *blueprint.tech_stack]).lower()
    package_names = [item.name for item in blueprint.dependency_inventory]
    must_criteria = {
        item.id for item in blueprint.acceptance_criteria if item.priority == "must"
    }

    if "vite" in stack and not any(spec.path.lower() == "index.html" for spec in files):
        index_spec = FileSpec(
            path="index.html",
            description="Vite HTML entry document containing the root application mount element.",
            internal_dependencies=[],
            external_dependencies=[],
            implements=[],
            public_contract="Provides div#root and loads the planned src/main entry module.",
            file_type="config",
        )
        insertion = next(
            (index for index, spec in enumerate(files) if spec.file_type == "source"),
            len(files),
        )
        files.insert(insertion, index_spec)

    app_paths = [
        spec.path for spec in files
        if spec.path.lower().startswith("src/app.") and spec.file_type == "source"
    ]
    main_paths = [
        spec.path for spec in files if spec.path.lower().startswith("src/main.")
    ]
    test_specs = [spec for spec in files if spec.file_type == "test"]
    covered_by_tests = {
        criterion_id for spec in test_specs for criterion_id in spec.implements
    }
    uncovered = must_criteria - covered_by_tests

    completed = []
    for spec in files:
        updates = {}
        if "vite" in stack and spec.path.lower() == "index.html" and main_paths:
            updates["public_contract"] = (
                "Provides the React root mount element and loads "
                f"/{main_paths[0]} using a type=\"module\" script inside the body."
            )
        if spec.file_type in {"source", "test", "config", "manifest"}:
            if not spec.public_contract.strip() and "public_contract" not in updates:
                updates["public_contract"] = spec.description
        if spec.file_type == "manifest" and package_names:
            updates["external_dependencies"] = package_names
        if spec.file_type == "test":
            implements = list(dict.fromkeys([*spec.implements, *sorted(uncovered)]))
            if implements != spec.implements:
                updates["implements"] = implements
            if not spec.internal_dependencies:
                implementations = [
                    item.path for item in files
                    if item.file_type == "source"
                    and set(item.implements).intersection(implements)
                ]
                if implementations:
                    updates["internal_dependencies"] = implementations
        if spec.path.lower().startswith("src/main.") and not spec.internal_dependencies:
            earlier_apps = [
                path for path in app_paths
                if next(i for i, item in enumerate(files) if item.path == path)
                < next(i for i, item in enumerate(files) if item.path == spec.path)
            ]
            if earlier_apps:
                updates["internal_dependencies"] = [earlier_apps[0]]
        completed.append(spec.model_copy(update=updates) if updates else spec)

    return blueprint.model_copy(update={
        "original_request": project_prompt,
        "files": completed,
    })


def validate_blueprint(blueprint: ArchitectureBlueprint) -> None:
    """Reject structurally incomplete plans before code generation begins."""
    ordered_paths = [file.path for file in blueprint.files]
    paths = {path.lower() for path in ordered_paths}
    stack = " ".join([blueprint.framework, *blueprint.tech_stack]).lower()
    problems = []
    complexity = infer_complexity(blueprint.original_request)

    if not blueprint.original_request.strip():
        problems.append("original_request must be preserved")
    if not blueprint.functional_requirements:
        problems.append("functional_requirements must not be empty")
    if not blueprint.acceptance_criteria:
        problems.append("acceptance_criteria must not be empty")
    if len(paths) != len(ordered_paths):
        problems.append("file paths must be unique (case-insensitive)")
    if complexity == "simple":
        request = blueprint.original_request.lower()
        if "typescript" not in request and (
            blueprint.primary_language.lower().startswith("typescript")
            or any(path.endswith((".ts", ".tsx")) for path in paths)
        ):
            problems.append(
                "simple projects must prefer JavaScript unless TypeScript was explicitly requested"
            )
        if any(path.startswith("src/use") for path in paths):
            problems.append(
                "simple projects should keep local feature logic in the component instead of a custom hook"
            )
        if len(blueprint.files) > 8:
            problems.append("simple projects should normally use no more than 8 planned files")
        if "calculator" in request and not any(
            marker in request
            for marker in ("chain", "chained", "consecutive", "precedence", "expression")
        ):
            acceptance_text = " ".join(
                criterion.description.lower()
                for criterion in blueprint.acceptance_criteria
            )
            if any(
                marker in acceptance_text
                for marker in ("chain", "chained", "consecutive operations", "operator precedence")
            ):
                problems.append(
                    "simple calculator criteria must not require chained operations unless requested"
                )

    criterion_ids = [criterion.id for criterion in blueprint.acceptance_criteria]
    known_criteria = set(criterion_ids)
    if len(known_criteria) != len(criterion_ids):
        problems.append("acceptance criterion IDs must be unique")
    package_names = {package.name for package in blueprint.dependency_inventory}
    if len(package_names) != len(blueprint.dependency_inventory):
        problems.append("dependency inventory names must be unique")
    path_positions = {path: index for index, path in enumerate(ordered_paths)}

    implementation_coverage = {criterion_id: set() for criterion_id in known_criteria}
    test_coverage = {criterion_id: set() for criterion_id in known_criteria}
    for index, file in enumerate(blueprint.files):
        if file.file_type in {"source", "test", "config", "manifest"} and not file.public_contract.strip():
            problems.append(f"{file.path} is missing public_contract")
        for dependency in file.internal_dependencies:
            if dependency not in path_positions:
                problems.append(f"{file.path} references unknown internal dependency {dependency}")
            elif dependency == file.path:
                problems.append(f"{file.path} cannot depend on itself")
            elif path_positions[dependency] >= index:
                problems.append(
                    f"{file.path} must appear after internal dependency {dependency}"
                )
        for dependency in file.external_dependencies:
            if dependency not in package_names:
                problems.append(f"{file.path} references unknown package {dependency}")
        for criterion_id in file.implements:
            if criterion_id not in known_criteria:
                problems.append(f"{file.path} references unknown criterion {criterion_id}")
            elif file.file_type == "test":
                test_coverage[criterion_id].add(file.path)
            else:
                implementation_coverage[criterion_id].add(file.path)
        if file.file_type == "test" and not file.internal_dependencies:
            problems.append(f"{file.path} must declare the implementation files it tests")

    for criterion in blueprint.acceptance_criteria:
        if criterion.priority != "must":
            continue
        if not implementation_coverage[criterion.id]:
            problems.append(f"{criterion.id} has no implementation file")

    manifest_packages = {
        dependency
        for file in blueprint.files if file.file_type == "manifest"
        for dependency in file.external_dependencies
    }
    if manifest_packages != package_names:
        missing = sorted(package_names - manifest_packages)
        extra = sorted(manifest_packages - package_names)
        if missing:
            problems.append("manifest specs omit packages: " + ", ".join(missing))
        if extra:
            problems.append("manifest specs reference undeclared packages: " + ", ".join(extra))

    if "readme.md" not in paths:
        problems.append("README.md is required")
    if not any(file.file_type == "manifest" for file in blueprint.files):
        problems.append("the native dependency manifest is missing")
    if "vite" in stack:
        if "package.json" not in paths:
            problems.append("Vite requires package.json")
        if "index.html" not in paths:
            problems.append("Vite requires index.html at the project root")
        if not any(path.startswith("src/main.") for path in paths):
            problems.append("Vite requires a src/main.* entry point")
        if not blueprint.build_command.strip():
            problems.append("Vite requires a non-interactive build_command")
    if "typescript" in stack or blueprint.primary_language.lower().startswith("typescript"):
        if not blueprint.typecheck_command.strip():
            problems.append("TypeScript requires a typecheck_command")
    if "css-module" in stack or "css module" in stack:
        if not any(".module.css" in path for path in paths):
            problems.append("CSS Modules were selected but no *.module.css file was planned")

    if problems:
        raise ValueError("Incomplete architecture blueprint: " + "; ".join(problems))


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
        blueprint = complete_blueprint_metadata(
            get_mock_blueprint(project_prompt), project_prompt
        )
        validate_blueprint(blueprint)
        return blueprint

    from google.genai import types

    complexity = infer_complexity(project_prompt)

    prompt = f"""Design a complete software project based on the following requirements:

REQUIREMENTS:
{project_prompt}

COMPLEXITY PROFILE: {complexity}
{profile_guidance(complexity)}

Preserve the requirement verbatim in original_request. Produce a structured, testable architectural contract containing every file needed to install, type-check, build, run, and test the project. Resolve ambiguities explicitly in assumptions, use stable acceptance-criterion IDs, define exact file contracts and dependency edges, and always include README.md.
"""

    config = types.GenerateContentConfig(
        system_instruction=ARCHITECT_SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=ArchitectureBlueprint,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.2,
    )

    last_error = None
    retry_feedback = ""
    for attempt in range(1, max_retries + 1):
        candidate: Optional[ArchitectureBlueprint] = None
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt + retry_feedback,
                config=config,
            )

            if hasattr(response, "parsed") and response.parsed:
                candidate = response.parsed
            else:
                raw_text = response.text.strip()
                candidate = ArchitectureBlueprint.model_validate_json(raw_text)

            blueprint = complete_blueprint_metadata(candidate, project_prompt)
            validate_blueprint(blueprint)
            return blueprint
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                rejected = (
                    candidate.model_dump_json(indent=2)
                    if candidate is not None
                    else "<response could not be parsed>"
                )
                retry_feedback = (
                    "\n\nYOUR PREVIOUS BLUEPRINT WAS REJECTED:\n"
                    f"{e}\n\nPREVIOUS REJECTED BLUEPRINT:\n{rejected}\n\n"
                    "Return the entire corrected blueprint, preserving valid decisions while "
                    "resolving every listed issue. Do not merely explain the corrections. "
                    "Re-check acceptance coverage, public contracts, dependency inventory "
                    "ownership, dependency ordering, and framework bootstrap files before responding."
                )
                sleep_time = attempt * 2
                time.sleep(sleep_time)

    raise last_error


def run_update_architect(
    client, model: str, project_prompt: str,
    baseline: ArchitectureBlueprint, files: dict[str, str],
) -> "ProjectUpdatePlan":
    """Plan a follow-up against actual source, preserving the project identity."""
    import json
    from src.schemas import ProjectUpdatePlan

    if client is None:
        return ProjectUpdatePlan(
            blueprint=baseline.model_copy(deep=True),
            changed_files=["README.md"],
            summary="Offline demonstration: append this request to README.md; no feature implementation is simulated.",
        )
    from google.genai import types

    prompt = (
        "Update the existing project for the conversation below. Preserve all earlier "
        "requirements unless explicitly superseded. Return a complete revised blueprint "
        "and changed_files listing every new or modified file (including affected dependents). "
        "Omit deleted files from the revised blueprint. Preserve project_name. "
        "Keep unchanged file contracts exactly as supplied. Do not rename unrelated files.\n"
        f"CONVERSATION:\n{project_prompt}\n"
        f"BASELINE BLUEPRINT:\n{baseline.model_dump_json()}\n"
        f"EXISTING SOURCE (JSON data):\n{json.dumps(files)}"
    )
    config = types.GenerateContentConfig(
        system_instruction=ARCHITECT_SYSTEM_INSTRUCTION,
        response_mime_type="application/json", response_schema=ProjectUpdatePlan,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.2,
    )
    feedback = ""
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model, contents=prompt + feedback, config=config,
            )
            plan = ProjectUpdatePlan.model_validate(
                response.parsed if response.parsed is not None
                else json.loads(response.text)
            )
            if plan.blueprint.project_name != baseline.project_name:
                raise ValueError("Updates must preserve project_name")
            validate_blueprint(plan.blueprint)
            paths = {spec.path for spec in plan.blueprint.files}
            if not set(plan.changed_files) <= paths:
                raise ValueError("changed_files must reference revised blueprint paths")
            return plan
        except Exception as exc:
            if attempt == 2:
                raise
            feedback = f"\nPrevious update plan was rejected: {exc}. Return a corrected complete plan."
    raise RuntimeError("No update plan returned")
