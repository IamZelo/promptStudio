"""Offline behavior tests for terminal sessions and transactional follow-ups."""

import io
import json
import os
from pathlib import Path

import pytest
from rich.console import Console

from src.pipeline import MultiAgentPipeline
from src.schemas import FileSpec, PipelineResult, ProjectUpdatePlan
from src.studio.cli import Chat, parse_args
from src.studio.render import Renderer
from src.studio.session import Session, SessionStore, project_hashes


def pipeline(tmp_path, **kwargs):
    return MultiAgentPipeline(
        client=None, model="mock", output_dir=tmp_path / "output",
        on_event=lambda event: None, confirm_plan=lambda plan: True, **kwargs,
    )


def create(tmp_path):
    result = pipeline(tmp_path).execute("Build a note-taking CLI")
    assert result.approved, result.errors
    return result


def chat_for(tmp_path, session=None, answers=()):
    stream = io.StringIO()
    renderer = Renderer(Console(file=stream, width=80, color_system=None))
    replies = iter(answers)

    def read(prompt):
        return next(replies)

    def factory(active, events, confirm):
        return MultiAgentPipeline(
            client=None, model="mock", output_dir=Path(active.output_dir),
            on_event=events, confirm_plan=confirm,
        )

    session = session or Session(output_dir=str(tmp_path / "output"), mock=True)
    return Chat(session, SessionStore(tmp_path / "sessions"), factory, renderer, read), stream


def test_structured_result_and_progress(tmp_path):
    events = []
    runner = pipeline(tmp_path)
    runner.on_event = events.append
    result = runner.execute("Build a note-taking CLI")
    assert result.approved and result.files and result.validation.passed
    assert result.review.approved and Path(result.output_path).is_dir()
    assert [e["stage"] for e in events if e["type"] == "stage"] == ["Architect", "Developer", "QA", "Critic"]
    assert any(e["type"] == "file" for e in events)
    assert runner._active_workspace is None


def test_declining_plan_does_not_generate(tmp_path, monkeypatch):
    runner = pipeline(tmp_path)
    runner.confirm_plan = lambda plan: False
    monkeypatch.setattr("src.pipeline.run_developer_agent", lambda **kwargs: pytest.fail("Must not generate"))
    result = runner.execute("Build a note-taking CLI")
    assert result.status == "cancelled"
    assert not (tmp_path / "output").exists()


def test_mock_followup_preserves_unchanged_files_and_assets(tmp_path):
    first = create(tmp_path)
    root = Path(first.output_path)
    (root / "logo.bin").write_bytes(b"\x00\xff")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "keep").write_text("installed")
    runner = pipeline(tmp_path)
    plans = []
    runner.confirm_plan = lambda plan: plans.append(plan) or True
    updated = runner.execute("USER: Build notes\n\nUSER: Add dark mode", first.blueprint, first.files)
    assert updated.approved
    assert "Add dark mode" in updated.files["README.md"]
    assert plans[0]["changes"]["change"] == ["README.md"]
    for path in first.files.keys() - {"README.md"}:
        assert updated.files[path] == first.files[path]
    assert (root / "logo.bin").read_bytes() == b"\x00\xff"
    assert (root / "node_modules" / "keep").read_text() == "installed"


def test_failed_update_preserves_last_project(tmp_path, monkeypatch):
    first = create(tmp_path)
    monkeypatch.setattr("src.pipeline.run_developer_agent", lambda **kwargs: (_ for _ in ()).throw(ValueError("model failed")))
    result = pipeline(tmp_path, max_iterations=0).execute("Update README", first.blueprint, first.files)
    assert not result.approved and not result.files
    assert (Path(first.output_path) / "README.md").read_text() == first.files["README.md"]


def test_update_uses_source_and_regenerates_dependents(tmp_path, monkeypatch):
    first = create(tmp_path)
    original_developer = __import__("src.pipeline", fromlist=["run_developer_agent"]).run_developer_agent
    seen = []

    def plan(client, model, prompt, baseline, files):
        assert files == first.files and baseline == first.blueprint
        assert "Add a feature" in prompt
        return ProjectUpdatePlan(blueprint=baseline, changed_files=["quicknote/models.py"], summary="Update model")

    def develop(**kwargs):
        seen.append(kwargs["target_file"].path)
        return original_developer(**kwargs)

    monkeypatch.setattr("src.pipeline.run_update_architect", plan)
    monkeypatch.setattr("src.pipeline.run_developer_agent", develop)
    result = pipeline(tmp_path).execute("Add a feature", first.blueprint, first.files)
    assert result.approved
    assert {"quicknote/models.py", "quicknote/storage.py", "quicknote/cli.py"} <= set(seen)
    assert "requirements.txt" not in seen


def test_explicit_removal_published_without_deleting_unmanaged_files(tmp_path, monkeypatch):
    first = create(tmp_path)
    # Add a disposable managed documentation file to the starting snapshot.
    first.blueprint.files.append(FileSpec(path="old.md", description="Old docs", file_type="documentation"))
    first.files["old.md"] = "old docs"
    (Path(first.output_path) / "old.md").write_text("old docs")
    revised = first.blueprint.model_copy(update={"files": [s for s in first.blueprint.files if s.path != "old.md"]})
    monkeypatch.setattr("src.pipeline.run_update_architect", lambda *args: ProjectUpdatePlan(blueprint=revised, changed_files=[], summary="Remove old docs"))
    result = pipeline(tmp_path).execute("Remove old docs", first.blueprint, first.files)
    assert result.approved and "old.md" not in result.files
    assert not (Path(first.output_path) / "old.md").exists()


def test_cancellation_cleans_staging(tmp_path, monkeypatch):
    first = create(tmp_path)
    runner = pipeline(tmp_path)

    def interrupt(**kwargs):
        assert runner._active_workspace.is_dir()
        raise KeyboardInterrupt

    monkeypatch.setattr("src.pipeline.run_developer_agent", interrupt)
    with pytest.raises(KeyboardInterrupt):
        runner.execute("Update", first.blueprint, first.files)
    assert runner._active_workspace is None
    assert (Path(first.output_path) / "README.md").read_text() == first.files["README.md"]


def test_publish_interruption_restores_previous_project(tmp_path, monkeypatch):
    first = create(tmp_path)
    original_rename = Path.rename

    def rename(path, target):
        if "-publish-" in path.name:
            raise KeyboardInterrupt
        return original_rename(path, target)

    monkeypatch.setattr(Path, "rename", rename)
    runner = pipeline(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        runner.execute("Update", first.blueprint, first.files)
    assert (Path(first.output_path) / "README.md").read_text() == first.files["README.md"]
    assert not list((tmp_path / "output").glob(".*-backup-*"))
    assert not list((tmp_path / "output").glob(".*-publish-*"))


def test_edit_during_generation_blocks_publish(tmp_path):
    first = create(tmp_path)
    root = Path(first.output_path)
    expected = project_hashes(root)
    runner = pipeline(tmp_path)

    def confirm(plan):
        (root / "README.md").write_text("user edit during generation")
        return True

    def verify():
        if project_hashes(root) != expected:
            raise ValueError("External change")

    runner.confirm_plan = confirm
    result = runner.execute("Update", first.blueprint, first.files, verify)
    assert not result.approved
    assert (root / "README.md").read_text() == "user edit during generation"


def test_session_roundtrip_and_path_validation(tmp_path):
    result = create(tmp_path)
    session = Session(output_dir=str(tmp_path / "output"), mock=True)
    session.messages.append({"role": "user", "content": "Build notes"})
    session.record(result)
    store = SessionStore(tmp_path / "sessions")
    store.save(session)
    loaded = store.load(session.id)
    assert loaded == session
    assert "USER: Build notes" in loaded.context()
    assert not list(store.root.glob("tmp*"))
    with pytest.raises(ValueError):
        store.load("../escape")


def test_external_edits_require_explicit_acceptance(tmp_path):
    result = create(tmp_path)
    session = Session(output_dir=str(tmp_path / "output"), mock=True)
    session.record(result)
    root = Path(session.project_path)
    (root / "README.md").write_text("user edit")
    chat, _ = chat_for(tmp_path, session, ["n", "y"])
    assert not chat.check_external()
    assert session.files["README.md"] != "user edit"
    assert chat.check_external()
    assert session.files["README.md"] == "user edit"
    assert chat.store.load(session.id).hashes == project_hashes(root)


def test_external_additions_and_deletions_are_adopted(tmp_path):
    result = create(tmp_path)
    session = Session(output_dir=str(tmp_path / "output"), mock=True)
    session.record(result)
    root = Path(session.project_path)
    (root / "extra.py").write_text("answer = 42")
    (root / "README.md").unlink()
    (root / ".env").write_text("SECRET=not-for-context")
    (root / "image.bin").write_bytes(b"\xff")
    session.adopt_external(project_hashes(root))
    assert session.files["extra.py"] == "answer = 42"
    assert not {"README.md", ".env", "image.bin"} & session.files.keys()
    assert "extra.py" in {s.path for s in session.blueprint.files}


def test_symlink_edits_rejected(tmp_path):
    result = create(tmp_path)
    session = Session(output_dir=str(tmp_path / "output"), mock=True)
    session.record(result)
    root = Path(session.project_path)
    (root / "README.md").unlink()
    (root / "README.md").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="symlink"):
        session.adopt_external(project_hashes(root))


def test_chat_generation_followup_and_resume(tmp_path):
    chat, output = chat_for(tmp_path, answers=["y", "y"])
    chat.generate("Build notes")
    assert chat.session.last_outcome["status"] == "approved"
    chat.generate("Add dark mode")
    assert "Add dark mode" in chat.session.files["README.md"]
    loaded = chat.store.load(chat.session.id)
    assert len(loaded.messages) == 4 and loaded.project_path
    assert "Source approved" in output.getvalue()
    assert "tests were not executed" in output.getvalue()
    resumed, _ = chat_for(tmp_path, loaded)
    assert resumed.command("/status") and resumed.command("/files")
    assert resumed.command("/show README.md")
    assert resumed.command("/help") and resumed.command("/unknown")
    assert not resumed.command("/exit")


def test_retry_decline_and_new_session(tmp_path):
    chat, _ = chat_for(tmp_path, answers=["n", "y"])
    original_id = chat.session.id
    chat.generate("Build notes")
    assert chat.session.last_outcome["status"] == "cancelled"
    chat.command("/retry")
    assert chat.session.last_outcome["status"] == "approved"
    assert len([m for m in chat.session.messages if m["role"] == "user"]) == 1
    chat.command("/new")
    assert chat.session.id != original_id
    assert not chat.session.files
    assert chat.store.load(original_id).project_path


def test_empty_input_ctrl_c_and_eof(tmp_path):
    chat, output = chat_for(tmp_path)
    answers = iter(["", KeyboardInterrupt(), EOFError()])

    def read(prompt):
        value = next(answers)
        if isinstance(value, BaseException):
            raise value
        return value

    chat.read = read
    assert chat.run() == 0
    assert not chat.session.messages
    assert "resume with" in " ".join(output.getvalue().split())


def test_promptstudio_args_independent_of_legacy_cli():
    args = parse_args(["--mock", "--output-dir", "/tmp/demo", "--llama-timeout", "7"])
    assert args.mock and args.output_dir == Path("/tmp/demo") and args.llama_timeout == 7


def test_update_architect_retries_invalid_project_identity(tmp_path):
    from types import SimpleNamespace
    from src.agents.architect import run_update_architect

    first = create(tmp_path)
    bad = ProjectUpdatePlan(
        blueprint=first.blueprint.model_copy(update={"project_name": "different"}),
        changed_files=["README.md"], summary="Bad rename",
    )
    good = ProjectUpdatePlan(blueprint=first.blueprint, changed_files=["README.md"], summary="Update docs")
    replies = iter([bad, good])
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(parsed=next(replies))

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    plan = run_update_architect(client, "test", "USER: Update docs", first.blueprint, first.files)
    assert plan.summary == "Update docs" and len(calls) == 2
    assert first.files["quicknote/cli.py"] in json.loads(
        calls[0]["contents"].split("EXISTING SOURCE (JSON data):\n")[1]
    ).values()
    assert "preserve project_name" in calls[1]["contents"]


def test_unmanaged_binary_asset_cannot_be_overwritten_by_new_file(tmp_path, monkeypatch):
    first = create(tmp_path)
    root = Path(first.output_path)
    (root / "asset.dat").write_bytes(b"\xff")
    revised = first.blueprint.model_copy(deep=True)
    revised.files.append(FileSpec(path="asset.dat", description="New asset", file_type="asset"))
    monkeypatch.setattr("src.pipeline.run_update_architect", lambda *args: ProjectUpdatePlan(
        blueprint=revised, changed_files=["asset.dat"], summary="Add asset",
    ))
    result = pipeline(tmp_path).execute("Add asset", first.blueprint, first.files)
    assert not result.approved
    assert "unmanaged asset" in result.errors[0]
    assert (root / "asset.dat").read_bytes() == b"\xff"


def test_narrow_plain_terminal_result_and_preview(tmp_path):
    result = create(tmp_path)
    stream = io.StringIO()
    ui = Renderer(Console(file=stream, width=42, color_system=None))
    ui.result(result, {})
    ui.files(result.files)
    ui.preview("quicknote/models.py", result.files["quicknote/models.py"])
    text = " ".join(stream.getvalue().split())
    assert "Source approved" in text and "tests were not executed" in text
    assert "\x1b[" not in text


def test_missing_credentials_returns_setup_error_without_mock(tmp_path):
    import os
    import subprocess
    import sys

    environment = {**os.environ, "GEMINI_API_KEY": ""}
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "promptstudio.py")],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=10,
    )
    assert completed.returncode == 2
    assert "GEMINI_API_KEY" in completed.stdout
    assert not (tmp_path / ".promptstudio").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX signal integration test")
@pytest.mark.parametrize("when", ["confirmation", "generation"])
def test_real_sigint_returns_to_chat(tmp_path, when):
    """Exercise OS signals, not just a mocked KeyboardInterrupt in a node."""
    import os
    import select
    import signal
    import subprocess
    import sys
    import time

    backend = Path(__file__).resolve().parents[1]
    script = '''
import time
import src.pipeline
from src.studio.cli import main

def slow_model(**kwargs):
    print("MODEL_CALL_STARTED", flush=True)
    time.sleep(30)

src.pipeline.run_developer_agent = slow_model
raise SystemExit(main(["--mock"]))
'''
    environment = {**os.environ, "PYTHONPATH": str(backend), "NO_COLOR": "1"}
    process = subprocess.Popen(
        [sys.executable, "-c", script], cwd=tmp_path, env=environment,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    def until(marker):
        data = b""
        deadline = time.monotonic() + 10
        while marker not in data and time.monotonic() < deadline:
            ready, _, _ = select.select([process.stdout], [], [], 0.1)
            if ready:
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    break
                data += chunk
        assert marker in data, data.decode(errors="replace")
        return data

    try:
        until(b"You >")
        process.stdin.write(b"Build notes\n")
        process.stdin.flush()
        until(b"Build this plan?")
        if when == "generation":
            process.stdin.write(b"y\n")
            process.stdin.flush()
            until(b"MODEL_CALL_STARTED")
        os.kill(process.pid, signal.SIGINT)
        assert b"Cancelled" in until(b"You >")
        process.stdin.write(b"/exit\n")
        process.stdin.flush()
        process.communicate(timeout=10)
        assert process.returncode == 0
        assert not (tmp_path / "output").exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def test_external_source_is_preserved_byte_for_byte_on_followup(tmp_path):
    first = create(tmp_path)
    session = Session(output_dir=str(tmp_path / "output"), mock=True)
    session.record(first)
    root = Path(first.output_path)
    content = b"answer = 42\r\n"
    (root / "helper.py").write_bytes(content)
    chat, _ = chat_for(tmp_path, session, answers=["y", "y"])
    chat.generate("Update the README")
    assert session.last_outcome["status"] == "approved", session.last_outcome
    assert session.files["helper.py"] == content.decode()
    assert (root / "helper.py").read_bytes() == content


def test_renderer_reuses_detailed_legacy_blueprint_and_summary(tmp_path):
    from src.utils.ui import presentation_events

    result = create(tmp_path)
    output = io.StringIO()
    ui = Renderer(Console(file=output, width=160, color_system=None))
    events = []
    with presentation_events(events.append):
        ui.plan({
            "blueprint": result.blueprint, "summary": "Create project",
            "changes": {"create": list(result.files), "change": [], "remove": []},
        })
        ui.result(result, {})
    text = " ".join(output.getvalue().split())
    for label in ["Architect Design Overview", "Architect Blueprint: Planned Files",
                  "Dependencies", "Responsibilities", "Generated Project Summary",
                  "Lines", "Duration", "Summary", "Installation & Run Guide"]:
        assert label in text
    assert result.blueprint.files[0].description in text
    assert result.results[0]["summary"] in text
    assert not events  # Explicit rendering must not loop back into the event sink.


@pytest.mark.parametrize("debug", [False, True])
def test_generation_is_quiet_unless_debug_enabled(debug):
    stream = io.StringIO()
    ui = Renderer(Console(file=stream, width=100, color_system=None), debug=debug)
    ui.event({"type": "stage", "stage": "Developer", "detail": "Generating"})
    ui.event({"type": "file", "path": "app.py", "index": 1, "total": 2})
    for level in ["info", "success", "warning", "error"]:
        ui.event({"type": "log", "level": level, "message": f"Detailed {level} diagnostic"})
    text = stream.getvalue()
    assert "Developer" in text
    assert ("app.py" in text) is debug
    for level in ["info", "success", "warning", "error"]:
        assert (f"Detailed {level} diagnostic" in text) is debug
    assert parse_args(["--debug"]).debug
    assert not parse_args([]).debug
