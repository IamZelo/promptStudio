"""Scrolling terminal presentation, with no model or filesystem side effects."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.tree import Tree
from rich.text import Text

from src.schemas import PipelineResult
from src.utils.ui import display_blueprint, display_summary_report


WORDMARK = r"""
 ____  ____   ___  __  __ ____ _____   ____ _____ _   _ ____ ___ ___
|  _ \|  _ \ / _ \|  \/  |  _ \_   _| / ___|_   _| | | |  _ \_ _/ _ \
| |_) | |_) | | | | |\/| | |_) || |   \___ \ | | | | | | | | | | | | |
|  __/|  _ <| |_| | |  | |  __/ | |    ___) || | | |_| | |_| | | |_| |
|_|   |_| \_\\___/|_|  |_|_|    |_|   |____/ |_|  \___/|____/___\___/
""".strip("\n")

COMPACT_LOGO = r"""
 .--------.
 | >_     |  PromptStudio
 '--------'
""".strip("\n")


class Renderer:
    def __init__(self, console: Console | None = None, *, debug: bool = False):
        self.console = console or Console(highlight=False)
        self.status = None
        self.debug = debug

    def text(self, message: str, style: str | None = None) -> None:
        self.console.print(message, markup=False, style=style)

    def stop(self) -> None:
        if self.status is not None:
            self.status.stop()
            self.status = None

    def banner(self, session) -> None:
        mode = "MOCK · deterministic offline demo" if session.mock else "LIVE · Gemini + llama.cpp"
        available = self.console.width - 4  # Panel borders and padding.
        if available >= max(map(len, WORDMARK.splitlines())):
            logo = WORDMARK + "\n\nPromptStudio"
        elif available >= max(map(len, COMPACT_LOGO.splitlines())):
            logo = COMPACT_LOGO
        else:
            logo = ">_ PromptStudio"
        self.console.print(Panel(
            Group(Text(logo, style="bold cyan"), Text(mode, style="dim")),
            border_style="cyan",
        ))
        self.text(f"Session {session.id} · Project: {session.project_path or 'new project'}", "dim")
        self.text("What do you want to make?  /help for commands", "cyan")

    def event(self, event: dict) -> None:
        kind = event["type"]
        if kind == "stage":
            self.stop()
            label = f"{event['stage']} · {event['detail']}"
            self.text(label, "cyan")
            if self.console.is_terminal:
                self.status = self.console.status(label)
                self.status.start()
        elif kind == "file":
            if self.debug:
                self.text(f"  ✓ [{event['index']}/{event['total']}] {event['path']}")
            elif self.status is not None:
                self.status.update(f"Developer · {event['index']}/{event['total']} files completed")
        elif kind == "log" and self.debug:
            styles = {"warning": "yellow", "error": "red", "success": "green", "info": "dim"}
            self.text(event["message"], styles.get(event["level"]))

    def plan(self, plan: dict) -> None:
        self.stop()
        blueprint = plan["blueprint"]
        self.text("\nProposed plan", "bold cyan")
        self.text(plan["summary"])
        display_blueprint(blueprint, output_console=self.console)
        # Retain explicit update/deletion information alongside the original blueprint.
        if plan["changes"]["change"] or plan["changes"]["remove"]:
            table = Table("Action", "File")
            for action, paths in plan["changes"].items():
                for path in paths:
                    table.add_row(action, path)
            self.console.print(table)

    def result(self, result: PipelineResult, previous: dict[str, str]) -> None:
        self.stop()
        if not result.approved:
            self.text(f"\n{result.status.capitalize()} · previous project preserved", "yellow")
            for error in result.errors:
                self.text(error, "red")
            if result.review:
                self.text(result.review.summary)
            if result.blueprint is not None and result.results:
                display_summary_report(
                    blueprint=result.blueprint, results=result.results,
                    total_time=result.duration, project_root=Path("."),
                    approved=False, output_console=self.console,
                )
            return
        self.text(f"\nSource approved · {result.duration:.1f}s", "bold green")
        summaries = {item["path"]: item for item in result.results}
        rows = [summaries.get(path, {
            "path": path, "lines": len(content.splitlines()), "duration": 0.0,
            "summary": "Unchanged from previous revision.",
        }) for path, content in result.files.items()]
        display_summary_report(
            blueprint=result.blueprint, results=rows, total_time=result.duration,
            project_root=Path(result.output_path), output_console=self.console,
        )
        removed = sorted(previous.keys() - result.files.keys())
        if removed:
            self.text("Removed files: " + ", ".join(removed))
        self.text("Validation: source syntax and semantic review.", "yellow")
        self.text("Application tests were not executed.", "yellow")
        if result.review:
            self.text(result.review.summary)

    def files(self, paths) -> None:
        tree = Tree("Project files")
        branches = {"": tree}
        for path in sorted(paths):
            parts = Path(path).parts
            parent = ""
            for part in parts:
                key = f"{parent}/{part}"
                if key not in branches:
                    branches[key] = branches[parent].add(Text(part))
                parent = key
        self.console.print(tree)

    def preview(self, path: str, content: str) -> None:
        if path.lower().endswith(".md"):
            self.console.print(Markdown(content))
        else:
            self.console.print(Syntax(content, Syntax.guess_lexer(path, content), line_numbers=True, word_wrap=True))
