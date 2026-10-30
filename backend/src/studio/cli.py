"""PromptStudio entry point. The original main.py CLI remains independent."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from src.schemas import PipelineResult
from src.studio.render import Renderer
from src.studio.session import Session, SessionStore, changed_paths, project_hashes

HELP = """Write a request to create or update your current project.
/help          Show commands
/new           Save this session and start a new conversation
/status        Show project, mode, and latest outcome
/files         Show the current project file tree
/show <path>   Preview a managed file
/retry         Retry the last failed, declined, or interrupted request
/exit          Save and exit (Ctrl+D also exits)

Each plan needs approval before generation. Follow-ups update the same project.
Mock mode always creates the Quicknote demo; follow-ups append to its README.
"""


class Chat:
    def __init__(self, session, store, factory, renderer=None, read=None):
        self.session = session
        self.store = store
        self.factory = factory
        self.ui = renderer or Renderer()
        self.read = read or input

    def confirm(self, question: str) -> bool:
        try:
            return self.read(question).strip().lower() in {"y", "yes"}
        except (EOFError, KeyboardInterrupt):
            return False

    def confirm_plan(self, plan: dict) -> bool:
        self.ui.plan(plan)
        return self.confirm("Build this plan? [y/N] ")

    def check_external(self) -> bool:
        if not self.session.project_path:
            return True
        root = Path(self.session.project_path)
        current = project_hashes(root)
        changes = changed_paths(self.session.hashes, current)
        if not changes:
            return True
        self.ui.text("External project changes detected:", "yellow")
        for path in changes:
            self.ui.text(f"  {path}")
        if not self.confirm("Accept these edits as the new baseline? [y/N] "):
            self.ui.text("Update cancelled; local files preserved.")
            return False
        self.session.adopt_external(current)
        self.store.save(self.session)
        return True

    def generate(self, request: str, retry: bool = False) -> None:
        if not self.check_external():
            return
        if not retry:
            self.session.messages.append({"role": "user", "content": request})
        self.session.last_request = request
        self.session.last_outcome = {"status": "interrupted", "errors": ["Run did not finish; use /retry."]}
        self.store.save(self.session)
        previous = dict(self.session.files)
        expected_hashes = dict(self.session.hashes)

        def verify_baseline():
            if self.session.project_path:
                current = project_hashes(Path(self.session.project_path))
                changed = changed_paths(expected_hashes, current)
                if changed:
                    raise ValueError("Project changed during generation: " + ", ".join(changed))

        try:
            pipeline = self.factory(self.session, self.ui.event, self.confirm_plan)
            result = pipeline.execute(
                self.session.context(), baseline=self.session.blueprint,
                files=self.session.files, before_publish=verify_baseline,
            )
        except KeyboardInterrupt:
            result = PipelineResult(status="cancelled", errors=["Run interrupted."])
        except Exception as exc:
            result = PipelineResult(status="failed", errors=[str(exc)])
        finally:
            self.ui.stop()
        self.session.record(result)
        self.ui.result(result, previous)
        self.store.save(self.session)

    def command(self, text: str) -> bool:
        command, _, argument = text.partition(" ")
        argument = argument.strip()
        if command == "/exit":
            return False
        if command == "/help":
            self.ui.text(HELP)
        elif command == "/new":
            self.store.save(self.session)
            self.ui.text(f"Saved {self.session.id}. Resume with promptstudio --resume {self.session.id}")
            self.session = Session(output_dir=self.session.output_dir, mock=self.session.mock)
            self.store.save(self.session)
            self.ui.banner(self.session)
        elif command == "/status":
            self.ui.text(f"Session: {self.session.id}\nMode: {'mock' if self.session.mock else 'live'}\nProject: {self.session.project_path or 'none'}\nLatest outcome: {self.session.last_outcome.get('status', 'none')}")
        elif command == "/files":
            self.ui.files(self.session.files)
        elif command == "/show":
            if argument not in self.session.files or not self.session.project_path:
                self.ui.text("Use /show with a managed path from /files.", "yellow")
            else:
                root = Path(self.session.project_path).resolve()
                path = root / argument
                if path.is_symlink() or not path.resolve().is_relative_to(root):
                    raise ValueError("Refusing to preview a symlink outside the project")
                self.ui.preview(argument, path.read_text(encoding="utf-8"))
        elif command == "/retry":
            if self.session.last_request and self.session.last_outcome.get("status") != "approved":
                self.generate(self.session.last_request, retry=True)
            else:
                self.ui.text("No unsuccessful request to retry. Write a follow-up instead.")
        else:
            self.ui.text("Unknown command. Use /help.", "yellow")
        return True

    def run(self) -> int:
        self.ui.banner(self.session)
        if self.session.messages:
            self.ui.text(f"Resumed {len(self.session.messages)} saved messages. Use /status or /files.", "dim")
            for message in self.session.messages[-4:]:
                self.ui.text(f"{message['role']}: {message['content']}")
        self.store.save(self.session)
        if self.session.project_path:
            try:
                self.check_external()
            except (ValueError, OSError) as exc:
                self.ui.text(str(exc), "red")
        try:
            while True:
                try:
                    text = self.read("You > ").strip()
                except EOFError:
                    break
                except KeyboardInterrupt:
                    self.ui.text("")
                    continue
                if not text:
                    continue
                try:
                    if text.startswith("/"):
                        if not self.command(text):
                            break
                    else:
                        self.generate(text)
                except (ValueError, OSError) as exc:
                    self.ui.stop()
                    self.ui.text(str(exc), "red")
        finally:
            self.ui.stop()
            self.store.save(self.session)
            self.ui.text(f"Saved session {self.session.id}. From {Path.cwd()}, resume with:")
            self.ui.text(f"promptstudio --resume {self.session.id}")
        return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="promptstudio", description="PromptStudio — create and refine projects in terminal chat.")
    parser.add_argument("--mock", action="store_true", help="Use the deterministic offline Quicknote demo")
    parser.add_argument("--resume", metavar="SESSION_ID")
    parser.add_argument("--debug", action="store_true", help="Show detailed agent logs and per-file generation progress")
    parser.add_argument("-o", "--output-dir", type=Path)
    parser.add_argument("-m", "--model")
    parser.add_argument("--llama-model")
    parser.add_argument("--llama-url")
    parser.add_argument("--llama-timeout", type=int)
    parser.add_argument("--max-repair-attempts", type=int, default=5)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    # Load before importing config: its dataclass defaults read the environment at import.
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    from src.config import AppConfig, LlamaCppClient, get_genai_client
    from src.pipeline import MultiAgentPipeline

    config = AppConfig()
    ui = Renderer(debug=args.debug)
    store = SessionStore(Path.cwd() / ".promptstudio" / "sessions")
    try:
        if args.resume:
            session = store.load(args.resume)
            if args.output_dir and str(args.output_dir.resolve()) != session.output_dir:
                raise ValueError("Resuming uses the saved output directory; omit --output-dir.")
            if args.mock and not session.mock:
                raise ValueError("Cannot switch a live session to mock mode. Start a new --mock session.")
        else:
            session = Session(output_dir=str((args.output_dir or config.default_output_dir).resolve()), mock=args.mock)
        if not session.mock and not config.has_valid_api_key:
            ui.text("Live mode requires GEMINI_API_KEY in backend/.env or your environment. Start llama-server for code generation. Use --mock for an offline demo.", "red")
            return 2
        client = None if session.mock else get_genai_client(config.gemini_api_key)
        developer = None if session.mock else LlamaCppClient(
            args.llama_url or config.llama_cpp_base_url,
            timeout=max(1, args.llama_timeout or config.llama_cpp_timeout),
            max_tokens=config.llama_cpp_max_tokens,
        )

        def factory(active, on_event, confirm_plan):
            return MultiAgentPipeline(
                client=client, model=args.model or config.gemini_model,
                output_dir=Path(active.output_dir), developer_client=developer,
                developer_model=args.llama_model or config.llama_cpp_model,
                max_iterations=max(0, args.max_repair_attempts),
                on_event=on_event, confirm_plan=confirm_plan,
            )

        try:
            import readline
            readline.set_history_length(500)  # Memory only; no global history file.
        except ImportError:
            pass
        return Chat(session, store, factory, renderer=ui).run()
    except (ValueError, OSError) as exc:
        ui.text(str(exc), "red")
        return 2


if __name__ == "__main__":
    sys.exit(main())
