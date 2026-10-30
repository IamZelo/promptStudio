"""Terminal UI and formatted presentation utilities using Rich with fallback."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import List, Dict, Any
from src.schemas import ArchitectureBlueprint

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    console = Console()
    HAS_RICH = True
except ImportError:
    console = None
    HAS_RICH = False


# Context-local routing keeps legacy CLI output intact and avoids global stdout capture.
_EVENT_SINK = ContextVar("promptstudio_event_sink", default=None)


@contextmanager
def presentation_events(sink):
    token = _EVENT_SINK.set(sink)
    try:
        yield
    finally:
        _EVENT_SINK.reset(token)


def _route(kind: str, **payload) -> bool:
    sink = _EVENT_SINK.get()
    if sink is None:
        return False
    sink({"type": kind, **payload})
    return True


def log_info(message: str) -> None:
    if _route("log", level="info", message=message):
        return
    if HAS_RICH:
        console.print(f"[cyan]ℹ[/cyan] {message}")
    else:
        print(f"[INFO] {message}")


def log_success(message: str) -> None:
    if _route("log", level="success", message=message):
        return
    if HAS_RICH:
        console.print(f"[green]✓[/green] {message}")
    else:
        print(f"[SUCCESS] {message}")


def log_warning(message: str) -> None:
    if _route("log", level="warning", message=message):
        return
    if HAS_RICH:
        console.print(f"[yellow]⚠[/yellow] {message}")
    else:
        print(f"[WARNING] {message}")


def log_error(message: str) -> None:
    if _route("log", level="error", message=message):
        return
    if HAS_RICH:
        console.print(f"[red]✗[/red] {message}")
    else:
        print(f"[ERROR] {message}")


def display_banner() -> None:
    banner_text = (
        "[bold cyan]Multi-Agent Software Development Pipeline[/bold cyan]\n"
        "[dim]Gemini Architect -> llama.cpp Developer -> QA -> Gemini Critic[/dim]"
    )
    if HAS_RICH:
        console.print(Panel(banner_text, expand=False, border_style="cyan"))
    else:
        print("=" * 60)
        print(" Multi-Agent Software Development Pipeline")
        print(" Gemini Architect -> llama.cpp Developer -> QA -> Gemini Critic")
        print("=" * 60)


def display_prompt(prompt: str) -> None:
    if HAS_RICH:
        console.print(Panel(f"[bold white]{prompt}[/bold white]", title="Project Specification", border_style="blue"))
    else:
        print(f"\nProject Specification:\n{prompt}\n")


def display_blueprint(blueprint: ArchitectureBlueprint, *, output_console=None) -> None:
    """Pretty prints the architecture blueprint."""
    if output_console is None and _route("blueprint", blueprint=blueprint):
        return
    target_console = output_console if output_console is not None else console
    if HAS_RICH:
        table = Table(title="Architect Blueprint: Planned Files", show_header=True, header_style="bold magenta")
        table.add_column("#", style="dim", width=4)
        table.add_column("File Path", style="cyan", width=28)
        table.add_column("Dependencies", style="yellow", width=24)
        table.add_column("Responsibilities", style="white")

        for idx, f in enumerate(blueprint.files, start=1):
            deps = ", ".join(f.internal_dependencies) if f.internal_dependencies else "[dim]None[/dim]"
            table.add_row(str(idx), f.path, deps, f.description)

        overview_content = (
            f"[bold]Project Name:[/bold] {blueprint.project_name}\n"
            f"[bold]Overview:[/bold] {blueprint.summary}\n"
            f"[bold]Language:[/bold] {blueprint.primary_language}\n"
            f"[bold]Framework:[/bold] {blueprint.framework}\n"
            f"[bold]Package Manager:[/bold] {blueprint.package_manager}\n"
            f"[bold]Tech Stack:[/bold] {', '.join(blueprint.tech_stack)}\n"
            f"[bold]Acceptance Criteria:[/bold] {len(blueprint.acceptance_criteria)}"
        )
        target_console.print(Panel(overview_content, title="Architect Design Overview", border_style="magenta"))
        target_console.print(table)
    else:
        print("\n--- ARCHITECTURE BLUEPRINT ---")
        print(f"Project Name: {blueprint.project_name}")
        print(f"Overview:     {blueprint.summary}")
        print(f"Language:     {blueprint.primary_language}")
        print(f"Framework:    {blueprint.framework}")
        print(f"Tech Stack:   {', '.join(blueprint.tech_stack)}")
        print("\nPlanned Files:")
        for idx, f in enumerate(blueprint.files, start=1):
            deps = (
                f" (deps: {', '.join(f.internal_dependencies)})"
                if f.internal_dependencies else ""
            )
            print(f"  {idx}. {f.path}{deps}\n     {f.description}")
        print("-" * 40 + "\n")


def display_summary_report(
    blueprint: ArchitectureBlueprint,
    results: List[Dict[str, Any]],
    total_time: float,
    project_root: Path,
    approved: bool = True,
    *,
    output_console=None,
) -> None:
    """Displays the final summary report of the multi-agent run."""
    if output_console is None and _route("summary", blueprint=blueprint, results=results, approved=approved):
        return
    total_lines = sum(r["lines"] for r in results)

    target_console = output_console if output_console is not None else console
    if HAS_RICH:
        summary_table = Table(title="Generated Project Summary", show_header=True, header_style="bold green")
        summary_table.add_column("File", style="cyan")
        summary_table.add_column("Lines", justify="right", style="magenta")
        summary_table.add_column("Duration", justify="right", style="yellow")
        summary_table.add_column("Summary", style="white")

        for r in results:
            summary_table.add_row(r["path"], str(r["lines"]), f"{r['duration']:.2f}s", r["summary"])

        target_console.print("\n", summary_table)
        if approved:
            stack = " ".join([blueprint.framework, *blueprint.tech_stack]).lower()
            guide_steps = [
                f"  1. Navigate to the project directory:\n     [bold cyan]cd {project_root}[/bold cyan]",
                f"  2. Install project dependencies:\n     [bold cyan]{blueprint.install_command}[/bold cyan]",
                f"  3. Run the application:\n     [bold cyan]{blueprint.run_command}[/bold cyan]",
            ]
            next_step = 4
            if "vite" in stack:
                guide_steps.append(
                    "  4. Open the localhost URL printed by Vite.\n"
                    "     [bold red]Do not open index.html directly; browsers cannot run the Vite/JSX source.[/bold red]"
                )
                next_step = 5
            if blueprint.test_command.strip():
                guide_steps.append(
                    f"  {next_step}. Run the tests:\n     [bold cyan]{blueprint.test_command}[/bold cyan]"
                )
            location_text = f"• Location: [bold underline]{project_root.resolve()}[/bold underline]"
            guide_text = "[bold yellow]Installation & Run Guide:[/bold yellow]\n" + "\n\n".join(guide_steps)
            guide_text += (
                "\n\n[bold yellow]Source approval does not install project dependencies. "
                "Run the commands above in order.[/bold yellow]"
            )
        else:
            location_text = "• Location: [yellow]Not published; isolated staging snapshot was discarded.[/yellow]"
            guide_text = "Fix the reported validation failures and run the pipeline again."

        status_text = "Pipeline Source Approved" if approved else "Pipeline Finished Without Approval"
        status_style = "green" if approved else "red"
        target_console.print(Panel(
            f"[bold {status_style}]{status_text}[/bold {status_style}]\n"
            f"• Project: [cyan]{blueprint.project_name}[/cyan]\n"
            f"• Files Created: [bold]{len(results)}[/bold] ({total_lines} total lines of code)\n"
            f"• Total Elapsed Time: [bold]{total_time:.2f}s[/bold]\n"
            f"{location_text}\n\n"
            f"{guide_text}",
            title="Source Ready" if approved else "Incomplete",
            border_style=status_style,
        ))
    else:
        print("\n" + "=" * 60)
        print(" PIPELINE SOURCE APPROVED" if approved else " PIPELINE FINISHED WITHOUT APPROVAL")
        print(f" Project:       {blueprint.project_name}")
        print(f" Files Created: {len(results)} ({total_lines} lines)")
        if approved:
            print(f" Location:      {project_root.resolve()}")
        else:
            print(" Location:      Not published; staging snapshot discarded")
        print(f" Total Time:    {total_time:.2f}s")
        print("-" * 60)
        if approved:
            stack = " ".join([blueprint.framework, *blueprint.tech_stack]).lower()
            print(" Installation & Run Guide:")
            print(f"  1. cd {project_root}")
            print(f"  2. {blueprint.install_command}")
            print(f"  3. {blueprint.run_command}")
            next_step = 4
            if "vite" in stack:
                print("  4. Open the localhost URL printed by Vite")
                print("     Do not open index.html directly")
                next_step = 5
            if blueprint.test_command.strip():
                print(f"  {next_step}. {blueprint.test_command}")
            print(" Source approval does not install project dependencies.")
        else:
            print(" Fix the reported validation failures and run the pipeline again.")
        print("=" * 60)
