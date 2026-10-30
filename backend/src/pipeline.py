"""LangGraph orchestration for the hybrid multi-agent development workflow."""

from __future__ import annotations

import time
import hashlib
import re
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Literal, Optional

from langgraph.graph import END, START, StateGraph

from src.agents import run_architect_agent, run_critic_agent, run_developer_agent, run_qa_agent
from src.agents.architect import validate_blueprint, run_update_architect
from src.schemas import ArchitectureBlueprint, CriticReview, PipelineResult, ValidationResult
from src.state import ProjectState
from src.utils import (
    count_lines,
    display_blueprint,
    display_summary_report,
    log_error,
    log_info,
    log_success,
    log_warning,
    validate_generated_content,
    write_file_to_disk,
)


class MultiAgentPipeline:
    """Coordinate Gemini reasoning, local code generation, QA, and repair."""

    def __init__(
        self,
        client: Optional[object],
        model: str,
        output_dir: Path,
        interactive: bool = False,
        developer_client: Optional[object] = None,
        developer_model: str = "local-model",
        max_iterations: int = 5,
        run_tests: bool = False,
        install_dependencies: bool = False,
        overwrite: bool = False,
        test_timeout: int = 60,
        on_event: Optional[Callable[[dict], None]] = None,
        confirm_plan: Optional[Callable[[dict], bool]] = None,
    ):
        self.client = client
        self.model = model
        self.output_dir = output_dir
        self.interactive = interactive
        self.developer_client = developer_client
        self.developer_model = developer_model
        self.max_iterations = max_iterations
        self.run_tests = run_tests
        self.install_dependencies = install_dependencies
        self.overwrite = overwrite
        self.test_timeout = test_timeout
        self.on_event = on_event
        self.confirm_plan = confirm_plan
        self._baseline: Optional[ArchitectureBlueprint] = None
        self._baseline_files: dict[str, str] = {}
        self._before_publish: Optional[Callable[[], None]] = None
        self._started_at = 0.0
        self._active_workspace: Optional[Path] = None

    def _project_root(self, state: ProjectState) -> Path:
        if not state["workspace_root"]:
            raise RuntimeError("Isolated project workspace is not available")
        return Path(state["workspace_root"])

    def _final_project_root(self, state: ProjectState) -> Path:
        blueprint = state["blueprint"]
        if blueprint is None:
            raise RuntimeError("Architecture blueprint is not available")
        return self.output_dir / blueprint.project_name

    def _emit(self, kind: str, **payload) -> None:
        if self.on_event:
            self.on_event({"type": kind, **payload})

    def _architect_node(self, state: ProjectState) -> dict:
        self._emit("stage", stage="Architect", detail="Planning your request")
        log_info("Architect Agent (Gemini): designing the project...")
        try:
            summary = "Create a new project."
            if self._baseline is not None:
                plan = run_update_architect(
                    self.client, self.model, state["user_prompt"],
                    self._baseline, self._baseline_files,
                )
                blueprint = plan.blueprint
                if blueprint.project_name != self._baseline.project_name:
                    raise ValueError("Updates must preserve the project directory")
                validate_blueprint(blueprint)
                paths = {spec.path for spec in blueprint.files}
                if not set(plan.changed_files) <= paths:
                    raise ValueError("Update contains unknown changed files")
                target = self.output_dir / blueprint.project_name
                for path in paths - self._baseline_files.keys():
                    if (target / path).exists() or (target / path).is_symlink():
                        raise ValueError(f"New file collides with an unmanaged asset: {path}")
                old_specs = {spec.path: spec for spec in self._baseline.files}
                changed = set(plan.changed_files) | (paths - self._baseline_files.keys())
                changed.update(
                    spec.path for spec in blueprint.files
                    if spec.path in old_specs and spec != old_specs[spec.path]
                )
                # Regenerate dependent contracts together instead of leaving stale callers.
                while True:
                    expanded = changed | {
                        spec.path for spec in blueprint.files
                        if set(spec.internal_dependencies) & changed
                    }
                    if expanded == changed:
                        break
                    changed = expanded
                summary = plan.summary
            else:
                blueprint = run_architect_agent(self.client, self.model, state["user_prompt"])
                paths = {spec.path for spec in blueprint.files}
                changed = set(paths)
            display_blueprint(blueprint)
            target = self.output_dir / blueprint.project_name
            if target.exists() and not self.overwrite and self._baseline is None:
                advice = (
                    "Resume its session or start with a different --output-dir."
                    if self.confirm_plan else "Use --overwrite or choose a different output directory."
                )
                raise FileExistsError(f"Project destination already exists: {target}. {advice}")
            changes = {
                "create": sorted(paths - self._baseline_files.keys()),
                "change": sorted(changed & self._baseline_files.keys()),
                "remove": sorted(self._baseline_files.keys() - paths),
            }
            if self.confirm_plan is not None:
                accepted = self.confirm_plan({
                    "blueprint": blueprint, "summary": summary, "changes": changes,
                })
            elif self.interactive:
                answer = input("\nProceed with this blueprint? [Y/n]: ").strip().lower()
                accepted = not answer or answer == "y"
            else:
                accepted = True
            if not accepted:
                return {"blueprint": blueprint, "status": "cancelled", "errors": ["Plan declined."]}
            self._active_workspace = Path(
                tempfile.mkdtemp(prefix=f"agent-{blueprint.project_name}-")
            )
            files = {path: content for path, content in self._baseline_files.items() if path in paths}
            for path, content in files.items():
                write_file_to_disk(self._active_workspace, path, content)
            return {
                "blueprint": blueprint,
                "files": files,
                "pending_files": [spec.path for spec in blueprint.files if spec.path in changed],
                "workspace_root": str(self._active_workspace),
                "status": "developing",
            }
        except Exception as exc:
            log_error(f"Architect Agent failed: {exc}")
            return {"status": "failed", "errors": [f"Architect: {exc}"]}

    @staticmethod
    def _route_after_architect(state: ProjectState) -> Literal["develop", "__end__"]:
        return "develop" if state["status"] == "developing" else END

    def _developer_node(self, state: ProjectState) -> dict:
        self._emit("stage", stage="Developer", detail="Generating" if not state["iteration"] else f"Repair {state['iteration']}")
        blueprint = state["blueprint"]
        assert blueprint is not None
        project_root = self._project_root(state)
        project_root.mkdir(parents=True, exist_ok=True)
        requested = set(state["pending_files"])
        specs = [spec for spec in blueprint.files if spec.path in requested]
        files = dict(state["files"])
        candidate_files = dict(files)
        results = list(state["generation_results"])
        candidate_results = list(results)
        errors = list(state["errors"])
        new_errors = []
        generated_candidates = []

        label = "repairing" if state["iteration"] else "generating"
        log_info(
            f"Developer Agent (local {self.developer_model}): {label} "
            f"{len(specs)} file(s)..."
        )
        for index, spec in enumerate(specs, start=1):
            started = time.time()
            try:
                repair_feedback = (
                    state["file_feedback"].get(spec.path) or state["feedback"]
                )
                if state["iteration"] >= 2 and repair_feedback:
                    repair_feedback += (
                        "\n\nREPAIR ESCALATION: Multiple patch attempts exposed coupled defects. "
                        "Do not patch only the latest symptom. Rebuild the target's internal logic "
                        "around a small coherent state machine or pure calculation flow, while "
                        "preserving its declared UI and export contract. Re-check every historical "
                        "constraint above before returning."
                    )
                generated = run_developer_agent(
                    client=self.developer_client,
                    model=self.developer_model,
                    blueprint=blueprint,
                    target_file=spec,
                    existing_files=candidate_files,
                    project_prompt=state["user_prompt"],
                    feedback=repair_feedback,
                )
                if self._baseline is not None and self.client is None and self.developer_client is None and spec.path == "README.md":
                    generated = generated.model_copy(update={
                        "code": self._baseline_files.get(spec.path, generated.code)
                        + "\n\n## PromptStudio mock follow-up\n\n"
                        + state["user_prompt"].split("USER: ")[-1] + "\n",
                        "summary": "Recorded follow-up request (offline demo only).",
                    })
                validate_generated_content(spec.path, generated.code)
                candidate_files[spec.path] = generated.code
                candidate_results = [
                    item for item in candidate_results if item["path"] != spec.path
                ]
                candidate_results.append({
                    "path": spec.path,
                    "lines": count_lines(generated.code),
                    "summary": generated.summary,
                    "duration": time.time() - started,
                })
                generated_candidates.append(generated)
                self._emit("file", path=spec.path, index=index, total=len(specs))
                log_success(f"[{index}/{len(specs)}] Generated {spec.path}")
            except Exception as exc:
                message = f"Developer failed for {spec.path}: {exc}"
                errors.append(message)
                new_errors.append(message)
                log_error(message)

        # A repair set is one transaction: never leave implementation and tests
        # at different revisions when any coupled candidate failed.
        if not new_errors:
            for generated in generated_candidates:
                write_file_to_disk(project_root, generated.path, generated.code)
            files = candidate_files
            results = candidate_results
        elif generated_candidates:
            log_warning("Discarded the incomplete repair set; no candidate files were committed.")

        return {
            "files": files,
            "generation_results": results,
            "pending_files": [],
            "errors": errors,
            "generation_errors": new_errors,
            "status": "validating",
        }

    def _qa_node(self, state: ProjectState) -> dict:
        self._emit("stage", stage="QA", detail="Checking source syntax")
        blueprint = state["blueprint"]
        assert blueprint is not None
        missing = [spec.path for spec in blueprint.files if spec.path not in state["files"]]
        if state["generation_errors"]:
            validation = ValidationResult(
                passed=False,
                command="candidate generation validation",
                exit_code=1,
                output="\n".join(state["generation_errors"]),
            )
        elif missing:
            validation = ValidationResult(
                passed=False,
                command="manifest completeness check",
                exit_code=1,
                output=f"Missing generated files: {', '.join(missing)}",
            )
        else:
            validation = run_qa_agent(
                self._project_root(state),
                blueprint=blueprint,
                run_tests=self.run_tests,
                timeout=self.test_timeout,
                install_dependencies=self.install_dependencies,
            )
        if validation.passed:
            evidence = validation.output
            if len(evidence) > 6000:
                evidence = evidence[:6000] + "\n[QA output truncated for display]"
            log_success(f"QA Agent passed: {evidence}")
        else:
            log_warning(f"QA Agent failed: {self._qa_feedback(validation, 1200)}")
        return {"validation": validation, "status": "reviewing"}

    @staticmethod
    def _approval_problems(
        review: CriticReview,
        validation: ValidationResult,
        blueprint,
        files: dict[str, str],
    ) -> list[str]:
        problems = []
        if not validation.passed or not validation.verified:
            problems.append("deterministic QA is not fully verified")
        if not review.approved:
            problems.append("critic did not approve")
        if any(item.severity in {"high", "critical"} for item in review.findings):
            problems.append("critic reported high or critical findings")
        if review.requested_files:
            problems.append("critic requested missing files")
        missing = [spec.path for spec in blueprint.files if spec.path not in files]
        if missing:
            problems.append("generated snapshot is incomplete")
        return problems

    @staticmethod
    def _affected_files(blueprint, review: CriticReview) -> list[str]:
        """Return only files the critic explicitly says must change."""
        valid_paths = {spec.path for spec in blueprint.files}
        affected = set()
        for finding in review.findings:
            if finding.file_path in valid_paths:
                affected.add(finding.file_path)
            affected.update(path for path in finding.related_files if path in valid_paths)

        requested_paths = {spec.path for spec in review.requested_files}
        affected.update(requested_paths)
        if not affected:
            affected = {
                spec.path for spec in blueprint.files
                if spec.file_type in {"source", "test", "config", "manifest"}
            }
        return [spec.path for spec in blueprint.files if spec.path in affected]

    @staticmethod
    def _qa_feedback(validation: ValidationResult, limit_per_check: int = 1800) -> str:
        """Return compact failure evidence suitable for a local model prompt."""
        if validation.checks:
            failures = []
            for check in validation.checks:
                if check.passed:
                    continue
                detail = check.output.strip()
                if len(detail) > limit_per_check:
                    detail = detail[:limit_per_check] + "\n[QA output truncated]"
                failures.append(f"{check.name} ({check.command}):\n{detail}")
            return "\n\n".join(failures) or "QA reported no failed deterministic checks."
        output = validation.output.strip()
        return output[:4000] + ("\n[QA output truncated]" if len(output) > 4000 else "")

    @classmethod
    def _compact_validation(cls, validation: ValidationResult) -> ValidationResult:
        compact_checks = []
        for check in validation.checks:
            limit = 2200 if not check.passed else 400
            output = check.output
            if len(output) > limit:
                output = output[:limit] + "\n[output truncated]"
            compact_checks.append(check.model_copy(update={"output": output}))
        return validation.model_copy(update={
            "output": cls._qa_feedback(validation, 2200),
            "checks": compact_checks,
        })

    @staticmethod
    def _failure_signature(review: CriticReview, validation: ValidationResult) -> str:
        material = "\n".join([
            validation.output,
            *sorted(
                f"{item.severity}:{item.file_path}:{item.message}"
                for item in review.findings
            ),
        ])
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def _critic_node(self, state: ProjectState) -> dict:
        self._emit("stage", stage="Critic", detail="Reviewing generated source")
        blueprint = state["blueprint"]
        validation = state["validation"]
        assert blueprint is not None and validation is not None
        log_info("Critic Agent (Gemini): reviewing QA evidence and generated files...")
        try:
            review = run_critic_agent(
                self.client, self.model, blueprint, state["files"],
                self._compact_validation(validation),
                project_prompt=state["user_prompt"],
                repair_history=state["file_feedback"],
            )
        except Exception as exc:
            review = CriticReview(approved=False, summary=f"Critic Agent failed: {exc}")

        for finding in review.findings:
            location = finding.file_path or "project"
            log_warning(
                f"Critic [{finding.severity}] {location}: {finding.message} "
                f"Suggested fix: {finding.suggested_fix}"
            )
        known_paths = {spec.path for spec in blueprint.files}
        genuinely_new = [
            spec.path for spec in review.requested_files if spec.path not in known_paths
        ]
        if genuinely_new:
            log_warning(
                "Critic requested new files: "
                + ", ".join(genuinely_new)
            )

        approval_problems = self._approval_problems(
            review, validation, blueprint, state["files"]
        )
        if not approval_problems:
            log_success(f"Critic approved the generated source: {review.summary}")
            return {"review": review, "status": "approved"}

        signature = self._failure_signature(review, validation)
        if state["last_failure_signature"] == signature:
            log_error("Repair made no observable progress; stopping instead of repeating it.")
            return {"review": review, "status": "failed"}

        next_iteration = state["iteration"] + 1
        if next_iteration > state["max_iterations"]:
            log_error("Repair limit exhausted; project was not approved.")
            return {"review": review, "status": "failed"}

        existing_paths = {spec.path for spec in blueprint.files}
        requested_files = [
            spec for spec in review.requested_files if spec.path not in existing_paths
        ]
        if requested_files:
            blueprint = blueprint.model_copy(
                update={"files": [*blueprint.files, *requested_files]}
            )
            try:
                validate_blueprint(blueprint)
            except ValueError as exc:
                log_error(f"Critic proposed an invalid blueprint update: {exc}")
                return {
                    "review": review,
                    "errors": [*state["errors"], f"Invalid blueprint repair: {exc}"],
                    "status": "failed",
                }
            log_info(
                "Critic added missing blueprint files: "
                + ", ".join(spec.path for spec in requested_files)
            )

        valid_paths = {spec.path for spec in blueprint.files}
        affected = self._affected_files(blueprint, review)
        missing_paths = {
            spec.path for spec in blueprint.files if spec.path not in state["files"]
        }
        if missing_paths:
            affected = [
                spec.path for spec in blueprint.files
                if spec.path in set(affected).union(missing_paths)
            ]
        feedback_parts = [review.summary, self._qa_feedback(validation)]
        file_feedback = dict(state["file_feedback"])
        for item in review.findings:
            detail = f"{item.message} Fix: {item.suggested_fix}"
            feedback_parts.append(f"{item.file_path or 'project'}: {detail}")
            if item.file_path in valid_paths:
                previous = file_feedback.get(item.file_path, "")
                entries = [entry for entry in previous.split("\n---\n") if entry]
                if detail not in entries:
                    entries.append(detail)
                file_feedback[item.file_path] = "\n---\n".join(entries[-8:])
        for spec in requested_files:
            file_feedback[spec.path] = f"Create this missing file. {spec.description}"
        log_warning(
            f"Critic requested repair iteration {next_iteration}/"
            f"{state['max_iterations']} for {len(affected)} file(s). "
            f"Cumulative constraints retained for {len(file_feedback)} file(s)."
        )
        return {
            "review": review,
            "blueprint": blueprint,
            "pending_files": affected,
            "feedback": "\n".join(part for part in feedback_parts if part),
            "file_feedback": file_feedback,
            "iteration": next_iteration,
            "last_failure_signature": signature,
            "status": "repairing",
        }

    @staticmethod
    def _route_after_critic(state: ProjectState) -> Literal["develop", "__end__"]:
        return "develop" if state["status"] == "repairing" else END

    def _build_graph(self):
        builder = StateGraph(ProjectState)
        builder.add_node("architect", self._architect_node)
        builder.add_node("develop", self._developer_node)
        builder.add_node("qa", self._qa_node)
        builder.add_node("critic", self._critic_node)
        builder.add_edge(START, "architect")
        builder.add_conditional_edges("architect", self._route_after_architect)
        builder.add_edge("develop", "qa")
        builder.add_edge("qa", "critic")
        builder.add_conditional_edges("critic", self._route_after_critic)
        return builder.compile()

    def _publish(self, state: ProjectState) -> Path:
        """Atomically publish only manifest files from an approved in-memory snapshot."""
        target = self._final_project_root(state)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if target.exists() and not self.overwrite and self._baseline is None:
            raise FileExistsError(
                f"Refusing to replace existing project {target}. Use --overwrite or a new output directory."
            )

        publish_root = Path(tempfile.mkdtemp(
            prefix=f".{target.name}-publish-", dir=self.output_dir
        ))
        backup = target.with_name(f".{target.name}-backup-{int(time.time() * 1000)}")
        try:
            if self._before_publish:
                self._before_publish()
            if self._baseline is not None:
                # Preserve untracked assets and installed dependencies during managed updates.
                shutil.copytree(target, publish_root, dirs_exist_ok=True, symlinks=True)
                for path in self._baseline_files.keys() - state["files"].keys():
                    removed = publish_root / path
                    if not removed.resolve().is_relative_to(publish_root.resolve()):
                        raise ValueError(f"Unsafe removed path: {path}")
                    removed.unlink(missing_ok=True)
            for path, content in state["files"].items():
                write_file_to_disk(publish_root, path, content)
            publish_error = self._published_snapshot_error(
                state["blueprint"], publish_root, state["files"]
            )
            if publish_error:
                raise RuntimeError(publish_error)
            if self._before_publish:
                self._before_publish()
            if target.exists():
                if not self.overwrite and self._baseline is None:
                    raise FileExistsError(f"Project destination appeared during generation: {target}")
                target.rename(backup)
            publish_root.rename(target)
        except BaseException:
            if target.exists() and backup.exists():
                shutil.rmtree(target)
            if backup.exists():
                backup.rename(target)
            if publish_root.exists():
                shutil.rmtree(publish_root)
            raise
        # The rename committed successfully. Cleanup must never trigger rollback
        # from a partially deleted backup or misreport a committed run as cancelled.
        try:
            if backup.exists():
                shutil.rmtree(backup, ignore_errors=True)
        except KeyboardInterrupt:
            pass
        return target

    @staticmethod
    def _published_snapshot_error(blueprint, root: Path, expected: dict[str, str]) -> str | None:
        """Verify the bytes written to the publish staging root before atomic rename."""
        for path, content in expected.items():
            written = root / path
            if not written.is_file():
                return f"Published snapshot is missing generated file: {path}"
            if written.read_bytes() != content.encode("utf-8"):
                return f"Published snapshot changed generated file contents: {path}"

        stack = " ".join([blueprint.framework, *blueprint.tech_stack]).lower()
        if "vite" not in stack:
            return None
        main_path = next(
            (spec.path for spec in blueprint.files if spec.path.lower().startswith("src/main.")),
            None,
        )
        index = root / "index.html"
        if not main_path or not index.is_file():
            return None
        html = index.read_text(encoding="utf-8")
        scripts = re.findall(r"<script\b[^>]*>", html, flags=re.IGNORECASE)
        if not any(
            re.search(r"\btype\s*=\s*['\"]module['\"]", tag, re.IGNORECASE)
            and (match := re.search(r"\bsrc\s*=\s*['\"]([^'\"]+)['\"]", tag, re.IGNORECASE))
            and match.group(1).lstrip("./") == main_path.lstrip("./")
            for tag in scripts
        ):
            return (
                f"Published Vite index.html does not load the generated entry {main_path}; "
                "refusing to publish a potentially blank app."
            )
        return None

    def run(self, project_prompt: str) -> bool:
        """Compatibility entry point for the existing one-shot CLI."""
        return self.execute(project_prompt).approved

    def execute(
        self, project_prompt: str,
        baseline: Optional[ArchitectureBlueprint] = None,
        files: Optional[dict[str, str]] = None,
        before_publish: Optional[Callable[[], None]] = None,
    ) -> PipelineResult:
        """Execute a creation/update transaction and return a structured outcome."""
        from contextlib import nullcontext
        from src.utils.ui import presentation_events

        self._baseline = baseline
        self._baseline_files = dict(files or {})
        self._before_publish = before_publish
        self._started_at = time.time()
        scope = presentation_events(self.on_event) if self.on_event else nullcontext()
        try:
            with scope:
                return self._execute(project_prompt)
        finally:
            if self._active_workspace is not None:
                shutil.rmtree(self._active_workspace, ignore_errors=True)
                self._active_workspace = None
            self._baseline = None
            self._baseline_files = {}
            self._before_publish = None

    def _execute(self, project_prompt: str) -> PipelineResult:
        initial_state: ProjectState = {
            "user_prompt": project_prompt,
            "blueprint": None,
            "files": {},
            "pending_files": [],
            "generation_results": [],
            "validation": None,
            "review": None,
            "feedback": "",
            "file_feedback": {},
            "iteration": 0,
            "max_iterations": self.max_iterations,
            "errors": [],
            "generation_errors": [],
            "workspace_root": "",
            "last_failure_signature": "",
            "status": "starting",
        }
        final = self._build_graph().invoke(
            initial_state, config={"recursion_limit": 6 + (self.max_iterations * 4)}
        )
        blueprint = final.get("blueprint")
        approved = final["status"] == "approved"
        project_root = self.output_dir / blueprint.project_name if blueprint else self.output_dir
        if approved:
            try:
                project_root = self._publish(final)
            except Exception as exc:
                approved = False
                final["status"] = "failed"
                final["errors"] = [*final["errors"], f"Publish failed: {exc}"]
                log_error(f"Approved snapshot could not be published: {exc}")
        if blueprint is not None:
            display_summary_report(
                blueprint=blueprint, results=final["generation_results"],
                total_time=time.time() - self._started_at,
                project_root=project_root, approved=approved,
            )
        if not approved:
            log_error(f"Pipeline finished with status: {final['status']}")
        return PipelineResult(
            status=final["status"], blueprint=blueprint,
            files=final["files"] if approved else {},
            results=final["generation_results"], validation=final["validation"],
            review=final["review"], errors=final["errors"],
            output_path=str(project_root.resolve()) if approved else None,
            duration=time.time() - self._started_at,
        )
