"""Multi-Agent Pipeline Orchestrator.

Manages the sequential workflow:
User Requirements ➔ Architect Agent ➔ Developer Agent ➔ Disk Persistence.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, Optional

from src.agents import run_architect_agent, run_developer_agent
from src.schemas import ArchitectureBlueprint
from src.utils import (
    write_file_to_disk,
    count_lines,
    log_info,
    log_success,
    log_warning,
    log_error,
    display_blueprint,
    display_summary_report,
)


class MultiAgentPipeline:
    """Orchestrates the collaborative software development workflow between agents."""

    def __init__(
        self,
        client: Optional[object],
        model: str,
        output_dir: Path,
        interactive: bool = False,
    ):
        self.client = client
        self.model = model
        self.output_dir = output_dir
        self.interactive = interactive

    def run(self, project_prompt: str) -> bool:
        """Executes the complete multi-agent development workflow.

        Args:
            project_prompt: The natural language specification for the software.

        Returns:
            True if pipeline completed successfully, False otherwise.
        """
        start_time = time.time()

        # -------------------------------------------------------------------
        # Step 1: Architect Agent Phase
        # -------------------------------------------------------------------
        log_info("Stage 1/2: Invoking [bold magenta]Architect Agent[/bold magenta]...")
        arch_start = time.time()

        try:
            blueprint = run_architect_agent(
                client=self.client,
                model=self.model,
                project_prompt=project_prompt,
            )
        except Exception as e:
            log_error(f"Architect Agent encountered an error: {e}")
            return False

        arch_duration = time.time() - arch_start
        log_success(f"Architect completed blueprint in {arch_duration:.2f}s ({len(blueprint.files)} files planned).")
        display_blueprint(blueprint)

        # Optional Human-In-The-Loop review step
        if self.interactive:
            confirm = input("\nProceed to Developer Agent to implement these files? [Y/n]: ").strip().lower()
            if confirm and confirm != "y":
                log_warning("Execution halted by user.")
                return False

        # -------------------------------------------------------------------
        # Step 2: Developer Agent Phase
        # -------------------------------------------------------------------
        project_root = self.output_dir / blueprint.project_name
        project_root.mkdir(parents=True, exist_ok=True)
        log_info(f"Stage 2/2: Invoking [bold green]Developer Agent[/bold green] (Output: [cyan]{project_root}[/cyan])...")

        existing_files: Dict[str, str] = {}
        results = []

        for idx, file_spec in enumerate(blueprint.files, start=1):
            log_info(f"[{idx}/{len(blueprint.files)}] Developing [bold cyan]{file_spec.path}[/bold cyan]...")
            dev_start = time.time()

            try:
                gen_file = run_developer_agent(
                    client=self.client,
                    model=self.model,
                    blueprint=blueprint,
                    target_file=file_spec,
                    existing_files=existing_files,
                )
            except Exception as e:
                log_error(f"Failed generating {file_spec.path}: {e}")
                continue

            dev_duration = time.time() - dev_start
            write_file_to_disk(project_root, gen_file.path, gen_file.code)
            existing_files[gen_file.path] = gen_file.code
            lines = count_lines(gen_file.code)

            results.append({
                "path": gen_file.path,
                "lines": lines,
                "summary": gen_file.summary,
                "duration": dev_duration,
            })
            log_success(f"Generated [cyan]{gen_file.path}[/cyan] ({lines} lines, {dev_duration:.2f}s): {gen_file.summary}")

        # -------------------------------------------------------------------
        # Step 3: Summary and Review
        # -------------------------------------------------------------------
        total_time = time.time() - start_time
        display_summary_report(
            blueprint=blueprint,
            results=results,
            total_time=total_time,
            project_root=project_root,
        )
        return True
