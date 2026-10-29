"""Critic Agent: semantic review of generated projects and QA evidence."""

from __future__ import annotations

import posixpath
import re
import time
from typing import Dict, Optional

from src.schemas import ArchitectureBlueprint, CriticReview, ReviewFinding, ValidationResult
from src.project_profile import infer_complexity, profile_guidance


CRITIC_SYSTEM_INSTRUCTION = """You are a focused semantic code reviewer for a demo pipeline.
Review only whether the existing generated files implement the original user request and acceptance criteria correctly.
Look for behavioral bugs, broken state transitions, wrong calculations, invalid import/export relationships, and runtime logic that clearly prevents the requested app from working. Only report a defect when the current code demonstrates a concrete failing path; do not report what might or could happen.
Trace at least one representative user interaction for each must-level criterion. Do not call a React state bug merely because setters are asynchronous: identify the exact handler sequence, the stale value, and the resulting wrong output.
For a simple calculator, basic arithmetic means completing one binary operation at a time unless the user or an acceptance criterion explicitly requires chained operations. Do not turn chaining into a blocking requirement on your own.
CSS Grid automatically creates additional rows when item count exceeds the declared column count. Do not report the number of buttons as overflow or broken layout without concrete CSS evidence. Treat merely aesthetic layout preferences as low or medium severity and non-blocking.

Do not review formatting, architecture style, optional features, dependency versions, test coverage, build tooling, documentation polish, or production hardening. Deterministic QA owns syntax and manifest validation.
Do not create source code, replacement file contents, patches, FileSpec objects, or new-file requests. requested_files must always be empty. You may recommend changes only to files already present in GENERATED FILES.

Every finding must:
- name exactly one existing file in file_path;
- explain what is wrong and its user-visible consequence in message;
- give a concise, implementation-level repair recommendation in suggested_fix, without writing the whole file. For state bugs, state the invariant or transition the repair must preserve instead of suggesting another ad-hoc setter;
- reference relevant criterion_ids when applicable.

Approve when there are no high or critical semantic bugs in the requested core behavior. Keep findings small and actionable. Do not request broad rewrites or invent new product behavior.
For a simple demo, prefer approval over speculative polish. CSS wrapper/grid opinions and hypothetical concurrency concerns are not blocking defects.
"""


def _resolve_local_import(
    importer: str, imported: str, files: Dict[str, str]
) -> str | None:
    if not imported.startswith("."):
        return None
    base = posixpath.normpath(posixpath.join(posixpath.dirname(importer), imported))
    candidates = [base, *[base + suffix for suffix in (".js", ".jsx", ".ts", ".tsx")]]
    candidates.extend(posixpath.join(base, "index" + suffix) for suffix in (".js", ".jsx", ".ts", ".tsx"))
    return next((candidate for candidate in candidates if candidate in files), None)


def _deterministic_semantic_findings(
    blueprint: ArchitectureBlueprint, files: Dict[str, str]
) -> list[ReviewFinding]:
    """Catch small, high-confidence startup defects that frequently produce blank pages."""
    stack = " ".join([blueprint.framework, *blueprint.tech_stack]).lower()
    if "vite" not in stack:
        return []

    findings: list[ReviewFinding] = []
    index_path = next((path for path in files if path.lower() == "index.html"), None)
    main_path = next(
        (spec.path for spec in blueprint.files if spec.path.lower().startswith("src/main.")),
        None,
    )
    if index_path and main_path:
        html = files[index_path]
        script_tags = re.findall(r"<script\b[^>]*>", html, flags=re.IGNORECASE)
        loads_entry = any(
            re.search(r"\btype\s*=\s*['\"]module['\"]", tag, re.IGNORECASE)
            and (match := re.search(r"\bsrc\s*=\s*['\"]([^'\"]+)['\"]", tag, re.IGNORECASE))
            and match.group(1).lstrip("./") == main_path.lstrip("./")
            for tag in script_tags
        )
        if not loads_entry:
            findings.append(ReviewFinding(
                severity="high",
                file_path=index_path,
                message=(
                    f"The Vite HTML entry does not load {main_path} as a module, so the "
                    "browser never executes React and displays a blank page."
                ),
                suggested_fix=(
                    f"Add a module script in the document body whose src points to /{main_path}."
                ),
            ))

    if main_path and main_path in files:
        main_code = files[main_path]
        mount_match = re.search(
            r"getElementById\(\s*['\"]([^'\"]+)['\"]\s*\)", main_code
        )
        if index_path and mount_match:
            mount_id = mount_match.group(1)
            if not re.search(
                rf"\bid\s*=\s*['\"]{re.escape(mount_id)}['\"]", files[index_path], re.IGNORECASE
            ):
                findings.append(ReviewFinding(
                    severity="high", file_path=index_path,
                    message=(
                        f"The React entry mounts to #{mount_id}, but index.html has no element "
                        "with that id, causing startup to fail."
                    ),
                    suggested_fix=f"Add the #{mount_id} mount element expected by {main_path}.",
                ))
        if "react" in stack and not re.search(r"\b(?:createRoot|render)\s*\(", main_code):
            findings.append(ReviewFinding(
                severity="high", file_path=main_path,
                message="The React entry file never creates or renders a React root, so no UI can appear.",
                suggested_fix="Mount the planned App component into the HTML root element.",
            ))

        for match in re.finditer(
            r"import\s+([A-Za-z_$][\w$]*)\s+from\s+['\"]([^'\"]+)['\"]",
            main_code,
        ):
            symbol, imported = match.groups()
            target = _resolve_local_import(main_path, imported, files)
            if target and re.search(rf"<{re.escape(symbol)}\b", main_code):
                if "export default" not in files[target]:
                    findings.append(ReviewFinding(
                        severity="high", file_path=target,
                        message=(
                            f"{main_path} default-imports and renders {symbol}, but {target} "
                            "does not provide a default export, causing React startup to fail."
                        ),
                        suggested_fix=f"Make the existing {symbol} component the default export.",
                    ))
    return findings


def _constrain_review(review: CriticReview, files: Dict[str, str]) -> CriticReview:
    """Enforce the critic's advisory-only, existing-file contract."""
    known_paths = set(files)
    findings = []
    for finding in review.findings:
        if finding.file_path not in known_paths:
            continue
        message_lower = finding.message.lower()
        speculative = (
            any(token in message_lower for token in (" may ", " might ", " could ", "potentially", "possibly"))
            or ("stale" in message_lower and any(
                token in message_lower for token in ("asynchronous", "batched", "setter")
            ))
        )
        css_layout_opinion = (
            finding.file_path.lower().endswith((".css", ".scss"))
            and any(token in message_lower for token in ("grid", "wrapper", "layout", "button"))
        )
        if speculative or css_layout_opinion:
            continue
        recommendation = finding.suggested_fix.strip()
        if "```" in recommendation:
            recommendation = recommendation.split("```", 1)[0].strip()
        if len(recommendation) > 600:
            recommendation = recommendation[:597].rstrip() + "..."
        if not recommendation:
            recommendation = "Make the smallest targeted change that corrects the described behavior."
        findings.append(finding.model_copy(update={"suggested_fix": recommendation}))
    blocking = any(finding.severity in {"high", "critical"} for finding in findings)
    return review.model_copy(update={
        "approved": not blocking,
        "findings": findings,
        "requested_files": [],
    })


def run_critic_agent(
    client: Optional[object],
    model: str,
    blueprint: ArchitectureBlueprint,
    files: Dict[str, str],
    validation: ValidationResult,
    project_prompt: str = "",
    repair_history: Dict[str, str] | None = None,
    max_retries: int = 3,
) -> CriticReview:
    """Review the complete generated project using Gemini or deterministic mock logic."""
    deterministic_findings = _deterministic_semantic_findings(blueprint, files)
    if client is None:
        findings = list(deterministic_findings)
        if not validation.passed:
            findings.append(ReviewFinding(
                severity="high",
                file_path=next(iter(files), ""),
                message=validation.output or "Validation failed",
                suggested_fix="Repair the files responsible for the validation failure.",
            ))
        review = _constrain_review(CriticReview(
            approved=not findings,
            summary=(
                "Mock critic found deterministic semantic defects."
                if findings else "Mock critic approved the validated project."
            ),
            findings=findings,
        ), files)
        if not validation.passed:
            return review.model_copy(update={"approved": False, "findings": findings})
        return review

    from google.genai import types

    file_context = "\n\n".join(
        f"--- {path} ---\n{code}" for path, code in files.items()
    )
    complexity = infer_complexity(project_prompt or blueprint.original_request)
    prompt = f"""ORIGINAL USER REQUIREMENT (authoritative):
{project_prompt or blueprint.original_request}

COMPLEXITY PROFILE: {complexity}
{profile_guidance(complexity)}

PROJECT BLUEPRINT AND ACCEPTANCE CONTRACT:
{blueprint.model_dump_json(indent=2)}

DETERMINISTIC QA:
{validation.model_dump_json(indent=2)}

GENERATED FILES:
{file_context}

REPAIR HISTORY (previous defects that must not regress):
{chr(10).join(f'--- {path} ---{chr(10)}{feedback}' for path, feedback in (repair_history or {}).items()) or 'None. This is the first review.'}

First verify that every applicable historical defect remains fixed in the current files. Report a historical defect again only if it is still present or has regressed. Then report any other high-confidence semantic defect. Do not replace resolved findings with optional feature requests.
"""
    config = types.GenerateContentConfig(
        system_instruction=CRITIC_SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=CriticReview,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.1,
    )
    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(model=model, contents=prompt, config=config)
            if getattr(response, "parsed", None):
                review = response.parsed
            else:
                review = CriticReview.model_validate_json(response.text.strip())
            combined = []
            seen = set()
            for finding in [*deterministic_findings, *review.findings]:
                key = (finding.file_path, finding.message)
                if key not in seen:
                    combined.append(finding)
                    seen.add(key)
            review = review.model_copy(update={"findings": combined})
            return _constrain_review(review, files)
        except Exception as exc:
            last_error = exc
            if attempt < max_retries:
                time.sleep(attempt * 2)
    assert last_error is not None
    raise last_error
