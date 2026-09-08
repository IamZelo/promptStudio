"""Terminal UI and formatted presentation utilities using Rich with fallback."""

from __future__ import annotations

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


def log_info(message: str) -> None:
    if HAS_RICH:
        console.print(f"[cyan]ℹ[/cyan] {message}")
    else:
        print(f"[INFO] {message}")


def log_success(message: str) -> None:
    if HAS_RICH:
        console.print(f"[green]✓[/green] {message}")
    else:
        print(f"[SUCCESS] {message}")


def log_warning(message: str) -> None:
    if HAS_RICH:
        console.print(f"[yellow]⚠[/yellow] {message}")
    else:
        print(f"[WARNING] {message}")


def log_error(message: str) -> None:
    if HAS_RICH:
        console.print(f"[red]✗[/red] {message}")
    else:
        print(f"[ERROR] {message}")


def display_banner() -> None:
    banner_text = (
        "[bold cyan]Multi-Agent Software Development Pipeline[/bold cyan]\n"
        "[dim]Collaborative AI: Architect Agent ➔ Developer Agent[/dim]"
    )
    if HAS_RICH:
        console.print(Panel(banner_text, expand=False, border_style="cyan"))
    else:
        print("=" * 60)
        print(" Multi-Agent Software Development Pipeline")
        print(" Collaborative AI: Architect Agent -> Developer Agent")
        print("=" * 60)


def display_prompt(prompt: str) -> None:
    if HAS_RICH:
        console.print(Panel(f"[bold white]{prompt}[/bold white]", title="Project Specification", border_style="blue"))
    else:
        print(f"\nProject Specification:\n{prompt}\n")


def display_blueprint(blueprint: ArchitectureBlueprint) -> None:
    """Pretty prints the architecture blueprint."""
    if HAS_RICH:
        table = Table(title="Architect Blueprint: Planned Files", show_header=True, header_style="bold magenta")
        table.add_column("#", style="dim", width=4)
        table.add_column("File Path", style="cyan", width=28)
        table.add_column("Dependencies", style="yellow", width=24)
        table.add_column("Responsibilities", style="white")

        for idx, f in enumerate(blueprint.files, start=1):
            deps = ", ".join(f.dependencies) if f.dependencies else "[dim]None[/dim]"
            table.add_row(str(idx), f.path, deps, f.description)

        overview_content = (
            f"[bold]Project Name:[/bold] {blueprint.project_name}\n"
            f"[bold]Overview:[/bold] {blueprint.summary}\n"
            f"[bold]Tech Stack:[/bold] {', '.join(blueprint.tech_stack)}"
        )
        console.print(Panel(overview_content, title="Architect Design Overview", border_style="magenta"))
        console.print(table)
    else:
        print("\n--- ARCHITECTURE BLUEPRINT ---")
        print(f"Project Name: {blueprint.project_name}")
        print(f"Overview:     {blueprint.summary}")
        print(f"Tech Stack:   {', '.join(blueprint.tech_stack)}")
        print("\nPlanned Files:")
        for idx, f in enumerate(blueprint.files, start=1):
            deps = f" (deps: {', '.join(f.dependencies)})" if f.dependencies else ""
            print(f"  {idx}. {f.path}{deps}\n     {f.description}")
        print("-" * 40 + "\n")


def display_summary_report(
    blueprint: ArchitectureBlueprint,
    results: List[Dict[str, Any]],
    total_time: float,
    project_root: Path,
) -> None:
    """Displays the final summary report of the multi-agent run."""
    total_lines = sum(r["lines"] for r in results)

    if HAS_RICH:
        summary_table = Table(title="Generated Project Summary", show_header=True, header_style="bold green")
        summary_table.add_column("File", style="cyan")
        summary_table.add_column("Lines", justify="right", style="magenta")
        summary_table.add_column("Duration", justify="right", style="yellow")
        summary_table.add_column("Summary", style="white")

        for r in results:
            summary_table.add_row(r["path"], str(r["lines"]), f"{r['duration']:.2f}s", r["summary"])

        console.print("\n", summary_table)
        # Check if requirements.txt exists
        has_reqs = any("requirements" in f.path for f in blueprint.files)

        entry_hint = "python3 -m <module> --help"
        for f in blueprint.files:
            if any(k in f.path for k in ["cli.py", "main.py", "app.py"]):
                entry_hint = f"python3 {f.path} --help"
                break

        guide_steps = [
            f"  1. Navigate to the project directory:\n     [bold cyan]cd {project_root}[/bold cyan]",
        ]
        if has_reqs:
            guide_steps.extend([
                f"  2. Install project dependencies:\n     [bold cyan]pip install -r requirements.txt[/bold cyan]",
                f"  3. Run the application:\n     [bold cyan]{entry_hint}[/bold cyan]",
            ])
        else:
            guide_steps.extend([
                f"  2. Run the application:\n     [bold cyan]{entry_hint}[/bold cyan]",
            ])

        guide_text = "\n\n".join(guide_steps)

        console.print(Panel(
            f"[bold green]Pipeline Complete![/bold green]\n"
            f"• Project: [cyan]{blueprint.project_name}[/cyan]\n"
            f"• Files Created: [bold]{len(results)}[/bold] ({total_lines} total lines of code)\n"
            f"• Total Elapsed Time: [bold]{total_time:.2f}s[/bold]\n"
            f"• Location: [bold underline]{project_root.resolve()}[/bold underline]\n\n"
            f"[bold yellow]Installation & Run Guide:[/bold yellow]\n"
            f"{guide_text}",
            title="Success",
            border_style="green"
        ))
    else:
        print("\n" + "=" * 60)
        print(" PIPELINE COMPLETE")
        print(f" Project:       {blueprint.project_name}")
        print(f" Files Created: {len(results)} ({total_lines} lines)")
        print(f" Location:      {project_root.resolve()}")
        print(f" Total Time:    {total_time:.2f}s")
        print("-" * 60)
        print(" Installation & Run Guide:")
        print(f"  1. cd {project_root}")
        if any("requirements" in f.path for f in blueprint.files):
            print("  2. pip install -r requirements.txt")
            print("  3. python3 <entrypoint> --help")
        else:
            print("  2. python3 <entrypoint> --help")
        print("=" * 60)
