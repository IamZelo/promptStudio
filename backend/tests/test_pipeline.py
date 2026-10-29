"""Tests for graph orchestration and generated-file safety."""

from pathlib import Path
import json

import pytest

from src.pipeline import MultiAgentPipeline
from src.config import LlamaCppClient
from src.agents.critic import (
    _constrain_review,
    _deterministic_semantic_findings,
    run_critic_agent,
)
from src.agents.qa import run_qa_agent
from src.agents.architect import (
    ARCHITECT_SYSTEM_INSTRUCTION,
    complete_blueprint_metadata,
    run_architect_agent,
    validate_blueprint,
)
from src.agents.developer import (
    DEVELOPER_SYSTEM_INSTRUCTION,
    _context_paths,
    _validate_blueprint_file_contract,
    normalize_generated_code,
    run_developer_agent,
)
from src.schemas import (
    AcceptanceCriterion,
    ArchitectureBlueprint,
    CriticReview,
    FileSpec,
    PackageDependency,
    ReviewFinding,
    ValidationResult,
)
from src.utils.file_manager import validate_generated_content, write_file_to_disk


def test_file_writer_rejects_path_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes project directory"):
        write_file_to_disk(tmp_path, "../outside.py", "print('no')")


def test_blueprint_rejects_unsafe_project_name() -> None:
    with pytest.raises(ValueError, match="single directory"):
        ArchitectureBlueprint(
            project_name="../outside",
            summary="unsafe",
            tech_stack=[],
            primary_language="Go 1.24",
            framework="standard library",
            package_manager="Go modules",
            install_command="go mod download",
            run_command="go run .",
            test_command="go test ./...",
            files=[FileSpec(path="main.go", description="entry point", file_type="source")],
        )


def test_mock_langgraph_pipeline_is_approved(tmp_path: Path) -> None:
    pipeline = MultiAgentPipeline(
        client=None,
        model="mock-gemini",
        developer_client=None,
        developer_model="mock-local",
        output_dir=tmp_path,
    )

    assert pipeline.run("Build a note-taking CLI") is True
    assert (tmp_path / "quicknote-cli" / "quicknote" / "cli.py").is_file()


def test_pipeline_defaults_to_five_repair_attempts(tmp_path: Path) -> None:
    pipeline = MultiAgentPipeline(client=None, model="mock", output_dir=tmp_path)

    assert pipeline.max_iterations == 5


def test_qa_reports_invalid_python(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("def broken(:\n", encoding="utf-8")

    blueprint = ArchitectureBlueprint(
        project_name="broken",
        summary="broken Python project",
        tech_stack=["Python"],
        primary_language="Python 3.14",
        framework="standard library",
        package_manager="pip",
        install_command="pip install -r requirements.txt",
        run_command="python broken.py",
        test_command="python -m pytest",
        files=[FileSpec(path="broken.py", description="broken source", file_type="source")],
    )
    result = run_qa_agent(tmp_path, blueprint=blueprint, run_tests=False, timeout=10)

    assert result.passed is False
    assert "SyntaxError" in result.output


def test_mock_critic_cannot_approve_failed_validation() -> None:
    blueprint = ArchitectureBlueprint(
        project_name="example",
        summary="example",
        tech_stack=["Python"],
        primary_language="Python 3.14",
        framework="standard library",
        package_manager="pip",
        install_command="pip install -r requirements.txt",
        run_command="python main.py",
        test_command="python -m pytest",
        files=[FileSpec(path="main.py", description="entry point", file_type="source")],
    )
    validation = ValidationResult(
        passed=False,
        command="python -m py_compile",
        exit_code=1,
        output="SyntaxError",
    )

    review = run_critic_agent(None, "mock", blueprint, {}, validation)

    assert review.approved is False
    assert review.findings[0].severity == "high"


def test_llama_cpp_client_uses_chat_completions(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self) -> bytes:
            return json.dumps({
                "choices": [{"message": {"content": '{"answer":"ok"}'}}]
            }).encode("utf-8")

    def fake_urlopen(http_request, timeout):
        captured["url"] = http_request.full_url
        captured["payload"] = json.loads(http_request.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("src.config.request.urlopen", fake_urlopen)
    client = LlamaCppClient("http://localhost:8080")

    content = client.generate(
        model="local-model",
        system="system",
        prompt="prompt",
        schema={"type": "object"},
    )

    assert content == '{"answer":"ok"}'
    assert captured["url"].endswith("/v1/chat/completions")
    assert captured["payload"]["response_format"]["schema"] == {"type": "object"}
    assert captured["payload"]["max_tokens"] >= 8192
    assert captured["payload"]["temperature"] <= 0.1


def test_agent_instructions_are_ecosystem_agnostic() -> None:
    assert "package.json" in ARCHITECT_SYSTEM_INSTRUCTION
    assert "Cargo.toml" in ARCHITECT_SYSTEM_INSTRUCTION
    assert "go.mod" in ARCHITECT_SYSTEM_INSTRUCTION
    assert "selected language's idioms" in DEVELOPER_SYSTEM_INSTRUCTION
    assert "requirements.txt" not in DEVELOPER_SYSTEM_INSTRUCTION


def test_vite_blueprint_requires_framework_bootstrap_files() -> None:
    blueprint = ArchitectureBlueprint(
        project_name="react-app",
        summary="React application",
        tech_stack=["React", "Vite", "CSS Modules"],
        primary_language="JavaScript",
        framework="React with Vite",
        package_manager="npm",
        install_command="npm install",
        run_command="npm run dev",
        test_command="npm test",
        files=[
            FileSpec(path="package.json", description="manifest", file_type="manifest"),
            FileSpec(path="src/main.jsx", description="entry", file_type="source"),
            FileSpec(path="src/app.test.jsx", description="tests", file_type="test"),
            FileSpec(path="README.md", description="docs", file_type="documentation"),
        ],
    )

    with pytest.raises(ValueError, match="index.html"):
        validate_blueprint(blueprint)


def test_candidate_validation_rejects_css_as_package_json() -> None:
    with pytest.raises(ValueError, match="Invalid JSON"):
        validate_generated_content("package.json", ".calculator { display: grid; }")


def test_developer_retries_wrong_file_without_renaming(monkeypatch: pytest.MonkeyPatch) -> None:
    blueprint = ArchitectureBlueprint(
        project_name="web-app",
        summary="web app",
        tech_stack=["JavaScript"],
        primary_language="JavaScript",
        framework="Vite",
        package_manager="npm",
        install_command="npm install",
        run_command="npm run dev",
        test_command="npm test",
        files=[FileSpec(path="package.json", description="manifest", file_type="manifest")],
    )
    responses = iter([
        '{"path":"styles.css","code":"body {}","summary":"styles"}',
        '{"path":"package.json","code":"{\\"scripts\\":{}}","summary":"manifest"}',
    ])

    class FakeClient:
        def generate(self, **kwargs):
            return next(responses)

    monkeypatch.setattr("src.agents.developer.time.sleep", lambda _seconds: None)
    result = run_developer_agent(
        FakeClient(), "local", blueprint, blueprint.files[0], {}, max_retries=2
    )

    assert result.path == "package.json"
    assert result.summary == "manifest"


def test_developer_normalizes_fenced_json_before_validation() -> None:
    fenced = "```json\n{\n  \"compilerOptions\": {}\n}\n```"

    normalized = normalize_generated_code(fenced)

    assert normalized.startswith("{")
    assert normalized.rstrip().endswith("}")
    validate_generated_content("tsconfig.json", normalized)


def test_developer_retries_invalid_json_with_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    blueprint = ArchitectureBlueprint(
        project_name="web-app",
        summary="web app",
        tech_stack=["TypeScript"],
        primary_language="TypeScript",
        framework="Vite",
        package_manager="npm",
        install_command="npm install",
        run_command="npm run dev",
        test_command="npm test",
        files=[FileSpec(path="tsconfig.json", description="config", file_type="config")],
    )
    responses = iter([
        '{"path":"tsconfig.json","code":"Here is the config","summary":"bad"}',
        '{"path":"tsconfig.json","code":"```json\\n{\\n  \\\"compilerOptions\\\": {}\\n}\\n```","summary":"fixed"}',
    ])
    prompts = []

    class FakeClient:
        def generate(self, **kwargs):
            prompts.append(kwargs["prompt"])
            return next(responses)

    monkeypatch.setattr("src.agents.developer.time.sleep", lambda _seconds: None)
    result = run_developer_agent(
        FakeClient(), "local", blueprint, blueprint.files[0], {}, max_retries=2
    )

    assert result.summary == "fixed"
    assert result.code.startswith("{")
    assert "Here is the config" in prompts[1]
    assert "Do not use Markdown fences" in prompts[1]


def _contract_blueprint(*, test_dependencies: list[str] | None = None) -> ArchitectureBlueprint:
    return ArchitectureBlueprint(
        project_name="contract-app",
        summary="Small contract-driven application",
        original_request="Build a greeting application",
        assumptions=["The greeting is plain text."],
        functional_requirements=["Return a greeting."],
        acceptance_criteria=[AcceptanceCriterion(
            id="APP-01", description="The app returns hello.",
            verification="An automated test asserts the returned value.",
        )],
        tech_stack=["Python 3.10+"],
        primary_language="Python 3.10+",
        framework="standard library",
        package_manager="pip",
        install_command="python -m pip install -r requirements.txt",
        run_command="python app.py",
        test_command="python -m pytest -q",
        files=[
            FileSpec(
                path="requirements.txt", description="Empty manifest",
                public_contract="Declares no third-party runtime packages.",
                file_type="manifest",
            ),
            FileSpec(
                path="app.py", description="Greeting implementation",
                implements=["APP-01"], public_contract="Exports greet() -> str.",
                file_type="source",
            ),
            FileSpec(
                path="tests/test_app.py", description="Greeting acceptance test",
                internal_dependencies=(
                    ["app.py"] if test_dependencies is None else test_dependencies
                ),
                implements=["APP-01"], public_contract="Verifies APP-01.",
                file_type="test",
            ),
            FileSpec(
                path="README.md", description="Usage documentation",
                internal_dependencies=["requirements.txt"],
                file_type="documentation",
            ),
        ],
    )


def test_developer_receives_verbatim_requirement_and_contract() -> None:
    blueprint = _contract_blueprint()
    captured = {}

    class FakeClient:
        def generate(self, **kwargs):
            captured["prompt"] = kwargs["prompt"]
            return json.dumps({
                "path": "app.py", "code": "def greet():\n    return 'hello'\n",
                "summary": "greeting",
            })

    run_developer_agent(
        FakeClient(), "local", blueprint, blueprint.files[1], {},
        project_prompt="VERBATIM USER REQUIREMENT",
    )

    assert "VERBATIM USER REQUIREMENT" in captured["prompt"]
    assert "APP-01" in captured["prompt"]
    assert "Exports greet()" in captured["prompt"]


def test_developer_retries_unchanged_repair_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blueprint = _contract_blueprint()
    old_code = "def greet():\n    return 'wrong'\n"
    responses = [
        json.dumps({"path": "app.py", "code": old_code, "summary": "unchanged"}),
        json.dumps({
            "path": "app.py", "code": "def greet():\n    return 'hello'\n",
            "summary": "fixed",
        }),
    ]

    class FakeClient:
        def generate(self, **kwargs):
            return responses.pop(0)

    monkeypatch.setattr("src.agents.developer.time.sleep", lambda _: None)
    generated = run_developer_agent(
        FakeClient(), "local", blueprint, blueprint.files[1],
        {"app.py": old_code}, feedback="Return the required greeting.",
    )

    assert generated.code != old_code
    assert generated.summary == "fixed"


def test_blueprint_rejects_test_without_dependency_edges() -> None:
    blueprint = _contract_blueprint(test_dependencies=[])

    with pytest.raises(ValueError, match="must declare the implementation files"):
        validate_blueprint(blueprint)


def test_blueprint_rejects_unknown_and_misordered_dependencies() -> None:
    blueprint = _contract_blueprint()
    broken_test = blueprint.files[2].model_copy(
        update={"internal_dependencies": ["missing.py"]}
    )
    blueprint = blueprint.model_copy(
        update={"files": [*blueprint.files[:2], broken_test, blueprint.files[3]]}
    )

    with pytest.raises(ValueError, match="unknown internal dependency missing.py"):
        validate_blueprint(blueprint)


def test_architect_completes_safe_vite_metadata() -> None:
    criteria = [
        AcceptanceCriterion(id="CALC-01", description="Add numbers.", verification="Test it."),
        AcceptanceCriterion(id="CALC-02", description="Enter decimals.", verification="Test it."),
    ]
    packages = [
        PackageDependency(name=name, version="1.0.0", purpose="React calculator", scope=scope)
        for name, scope in (
            ("react", "runtime"), ("react-dom", "runtime"),
            ("typescript", "development"), ("vitest", "development"),
            ("@testing-library/react", "development"),
        )
    ]
    blueprint = ArchitectureBlueprint(
        project_name="calculator", summary="React calculator", original_request="",
        assumptions=["C clears the calculator."],
        functional_requirements=["Perform arithmetic and accept decimals."],
        acceptance_criteria=criteria, tech_stack=["React", "Vite", "TypeScript"],
        dependency_inventory=packages, primary_language="TypeScript 5",
        framework="React with Vite", package_manager="npm", install_command="npm install",
        run_command="npm run dev", test_command="npm test -- --run",
        typecheck_command="npm run typecheck", build_command="npm run build",
        files=[
            FileSpec(path="package.json", description="npm manifest", file_type="manifest"),
            FileSpec(path="src/App.tsx", description="calculator UI", implements=["CALC-01", "CALC-02"], file_type="source"),
            FileSpec(path="src/main.tsx", description="React entry point", file_type="source"),
            FileSpec(path="src/logic/calculator.test.ts", description="calculator tests", implements=["CALC-01"], file_type="test"),
            FileSpec(path="README.md", description="documentation", file_type="documentation"),
        ],
    )

    completed = complete_blueprint_metadata(
        blueprint, "make a calculator app in React and TypeScript"
    )
    validate_blueprint(completed)

    specs = {spec.path: spec for spec in completed.files}
    assert "index.html" in specs
    assert specs["package.json"].external_dependencies == [item.name for item in packages]
    assert specs["src/main.tsx"].internal_dependencies == ["src/App.tsx"]
    assert "CALC-02" in specs["src/logic/calculator.test.ts"].implements
    assert specs["src/App.tsx"].public_contract == "calculator UI"


def test_architect_retry_includes_rejected_blueprint(monkeypatch: pytest.MonkeyPatch) -> None:
    invalid = _contract_blueprint().model_copy(update={"functional_requirements": []})
    valid = _contract_blueprint()

    class Response:
        def __init__(self, parsed):
            self.parsed = parsed

    class Models:
        def __init__(self):
            self.calls = []
            self.responses = iter([Response(invalid), Response(valid)])

        def generate_content(self, **kwargs):
            self.calls.append(kwargs["contents"])
            return next(self.responses)

    class Client:
        def __init__(self):
            self.models = Models()

    client = Client()
    monkeypatch.setattr("src.agents.architect.time.sleep", lambda _seconds: None)

    result = run_architect_agent(client, "gemini-test", "VERBATIM", max_retries=2)

    assert result.original_request == "VERBATIM"
    assert "PREVIOUS REJECTED BLUEPRINT" in client.models.calls[1]
    assert '"project_name": "contract-app"' in client.models.calls[1]


def test_simple_profile_rejects_unrequested_typescript_and_hook() -> None:
    blueprint = _contract_blueprint().model_copy(update={
        "original_request": "make a simple calculator app in react",
        "primary_language": "TypeScript",
        "tech_stack": ["React", "TypeScript"],
        "files": [
            *_contract_blueprint().files,
            FileSpec(
                path="src/useCalculator.ts", description="calculator hook",
                public_contract="Exports calculator state.", file_type="source",
            ),
        ],
    })

    with pytest.raises(ValueError) as exc_info:
        validate_blueprint(blueprint)

    assert "prefer JavaScript" in str(exc_info.value)
    assert "instead of a custom hook" in str(exc_info.value)


def test_simple_calculator_rejects_invented_chaining_requirement() -> None:
    original = _contract_blueprint()
    criterion = original.acceptance_criteria[0].model_copy(update={
        "description": "The calculator supports chained operations.",
    })
    blueprint = original.model_copy(update={
        "project_name": "calculator",
        "original_request": "make a simple calculator app",
        "functional_requirements": ["Perform arithmetic."],
        "acceptance_criteria": [criterion],
    })

    with pytest.raises(ValueError, match="must not require chained operations"):
        validate_blueprint(blueprint)


def test_repair_context_includes_target_dependencies_dependents_and_tests() -> None:
    blueprint = _contract_blueprint()
    paths = _context_paths(
        blueprint,
        blueprint.files[1],
        {
            "requirements.txt": "",
            "app.py": "old implementation",
            "tests/test_app.py": "test",
            "README.md": "docs",
        },
    )

    assert paths[0] == "app.py"
    assert "tests/test_app.py" in paths


def test_syntax_only_qa_ignores_unplanned_files(tmp_path: Path) -> None:
    blueprint = _contract_blueprint()
    for spec in blueprint.files:
        target = tmp_path / spec.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")
    (tmp_path / "stale.jsx").write_text("export default {};", encoding="utf-8")

    result = run_qa_agent(tmp_path, blueprint, run_tests=False, timeout=10)

    assert result.passed is True
    assert "stale.jsx" not in result.output


def test_syntax_only_qa_does_not_require_tests(tmp_path: Path) -> None:
    blueprint = _contract_blueprint()
    for spec in blueprint.files:
        target = tmp_path / spec.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")

    result = run_qa_agent(tmp_path, blueprint, run_tests=False, timeout=10)

    assert result.verified is True
    assert result.passed is True
    assert "syntax only" in result.output
    assert all(check.name not in {"tests", "build", "typecheck"} for check in result.checks)


def test_syntax_only_qa_does_not_run_typescript_typecheck(tmp_path: Path) -> None:
    blueprint = ArchitectureBlueprint(
        project_name="typed-app", summary="TypeScript fixture",
        original_request="Build typed app", assumptions=["No runtime needed."],
        functional_requirements=["Export a number."],
        acceptance_criteria=[AcceptanceCriterion(
            id="TS-01", description="Export a number.", verification="Compile and test it.",
        )],
        tech_stack=["TypeScript"], primary_language="TypeScript 5",
        framework="TypeScript", package_manager="npm", install_command="npm install",
        run_command="node dist/app.js", test_command="python -c pass",
        typecheck_command="tsc --noEmit", build_command="",
        files=[
            FileSpec(path="package.json", description="manifest", public_contract="npm manifest", file_type="manifest"),
            FileSpec(path="tsconfig.json", description="compiler", public_contract="strict compiler settings", file_type="config"),
            FileSpec(path="app.ts", description="app", implements=["TS-01"], public_contract="Exports value", file_type="source"),
            FileSpec(path="app.test.ts", description="test", internal_dependencies=["app.ts"], implements=["TS-01"], public_contract="Verifies TS-01", file_type="test"),
            FileSpec(path="README.md", description="docs", file_type="documentation"),
        ],
    )
    contents = {
        "package.json": "{}", "tsconfig.json": '{"compilerOptions":{"strict":true}}',
        "app.ts": "export const value: number = 'wrong';", "app.test.ts": "export {};",
        "README.md": "docs",
    }
    for path, content in contents.items():
        (tmp_path / path).write_text(content, encoding="utf-8")

    result = run_qa_agent(tmp_path, blueprint, run_tests=True, timeout=10)

    assert result.passed is True
    assert all(check.name != "typecheck" for check in result.checks)


def test_syntax_only_qa_ignores_dependency_inventory(tmp_path: Path) -> None:
    blueprint = _contract_blueprint().model_copy(update={
        "dependency_inventory": [PackageDependency(
            name="pytest", version=">=8.0.0", purpose="tests", scope="development",
        )]
    })
    manifest = blueprint.files[0].model_copy(
        update={"external_dependencies": ["pytest"]}
    )
    blueprint = blueprint.model_copy(update={"files": [manifest, *blueprint.files[1:]]})
    contents = {
        "requirements.txt": "",
        "app.py": "def greet():\n    return 'hello'\n",
        "tests/test_app.py": "def test_placeholder():\n    assert True\n",
        "README.md": "docs",
    }
    for path, content in contents.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    result = run_qa_agent(tmp_path, blueprint, run_tests=False, timeout=10)

    assert result.passed is True
    assert "dependency inventory" not in result.output


def test_simple_blueprint_does_not_require_a_test_file() -> None:
    original = _contract_blueprint()
    blueprint = original.model_copy(update={
        "original_request": "make a simple greeting app",
        "test_command": "",
        "files": [original.files[0], original.files[1], original.files[3]],
    })

    validate_blueprint(blueprint)


def test_critic_cannot_request_or_rewrite_new_files() -> None:
    review = CriticReview(
        approved=False,
        summary="Requested unnecessary setup.",
        findings=[
            ReviewFinding(
                severity="high", file_path="src/App.jsx",
                message="Addition returns concatenated text.",
                suggested_fix="Store operands separately and convert them before addition.",
            ),
            ReviewFinding(
                severity="high", file_path="src/setupTests.js",
                message="Missing setup file.", suggested_fix="Create the complete setup file.",
            ),
        ],
        requested_files=[FileSpec(
            path="src/setupTests.js", description="setup", file_type="config",
        )],
    )

    constrained = _constrain_review(review, {"src/App.jsx": "export default function App() {}"})

    assert constrained.approved is False
    assert constrained.requested_files == []
    assert [finding.file_path for finding in constrained.findings] == ["src/App.jsx"]


def test_critic_discards_speculative_state_and_css_opinions() -> None:
    review = CriticReview(
        approved=False,
        summary="review",
        findings=[
            ReviewFinding(
                severity="high", file_path="src/App.jsx",
                message="This may become stale because React setters are asynchronous.",
                suggested_fix="Rewrite state.",
            ),
            ReviewFinding(
                severity="high", file_path="src/index.css",
                message="The grid wrapper could break the button layout.",
                suggested_fix="Move the wrapper.",
            ),
        ],
    )

    constrained = _constrain_review(
        review, {"src/App.jsx": "code", "src/index.css": "css"}
    )

    assert constrained.approved is True
    assert constrained.findings == []


def test_critic_detects_vite_blank_page_entry_wiring() -> None:
    blueprint = ArchitectureBlueprint(
        project_name="calculator", summary="calculator",
        original_request="make a simple calculator app in react",
        tech_stack=["React", "Vite"], primary_language="JavaScript",
        framework="React", package_manager="npm", install_command="npm install",
        run_command="npm run dev", test_command="",
        files=[
            FileSpec(path="index.html", description="HTML entry", file_type="config"),
            FileSpec(path="src/App.jsx", description="App", file_type="source"),
            FileSpec(path="src/main.jsx", description="React entry", file_type="source"),
        ],
    )
    files = {
        "index.html": '<div id="root"></div>',
        "src/App.jsx": "export default function App() { return <div>Calculator</div>; }",
        "src/main.jsx": (
            "import ReactDOM from 'react-dom/client';\n"
            "import App from './App.jsx';\n"
            "ReactDOM.createRoot(document.getElementById('root')).render(<App />);"
        ),
    }

    findings = _deterministic_semantic_findings(blueprint, files)

    assert len(findings) == 1
    assert findings[0].file_path == "index.html"
    assert "blank page" in findings[0].message
    assert "/src/main.jsx" in findings[0].suggested_fix
    review = CriticReview(
        approved=False, summary="blank page", findings=findings,
    )
    assert MultiAgentPipeline._affected_files(blueprint, review) == ["index.html"]


def test_developer_rejects_vite_html_without_entry_script() -> None:
    blueprint = ArchitectureBlueprint(
        project_name="calculator", summary="calculator", tech_stack=["React", "Vite"],
        primary_language="JavaScript", framework="React", package_manager="npm",
        install_command="npm install", run_command="npm run dev", test_command="",
        files=[
            FileSpec(path="index.html", description="entry", file_type="config"),
            FileSpec(path="src/main.jsx", description="main", file_type="source"),
        ],
    )

    with pytest.raises(ValueError, match="must load /src/main.jsx"):
        _validate_blueprint_file_contract(
            blueprint, blueprint.files[0], '<div id="root"></div>'
        )

    _validate_blueprint_file_contract(
        blueprint,
        blueprint.files[0],
        '<div id="root"></div><script type="module" src="/src/main.jsx"></script>',
    )


def test_test_finding_does_not_regenerate_implementation_by_criterion() -> None:
    blueprint = _contract_blueprint()
    review = CriticReview(
        approved=False, summary="test import is wrong",
        findings=[ReviewFinding(
            severity="high", file_path="tests/test_app.py",
            message="bad test import", suggested_fix="repair the test",
            criterion_ids=["APP-01"],
        )],
    )

    assert MultiAgentPipeline._affected_files(blueprint, review) == ["tests/test_app.py"]


def test_implementation_repair_preserves_acceptance_test_oracle() -> None:
    blueprint = _contract_blueprint()
    review = CriticReview(
        approved=False, summary="implementation is wrong",
        findings=[ReviewFinding(
            severity="high", file_path="app.py", message="wrong result",
            suggested_fix="repair greet", criterion_ids=["APP-01"],
        )],
    )

    assert MultiAgentPipeline._affected_files(blueprint, review) == ["app.py"]


def test_component_repair_does_not_regenerate_unchanged_entrypoint() -> None:
    blueprint = ArchitectureBlueprint(
        project_name="web", summary="web", original_request="simple react app",
        tech_stack=["React", "Vite"], primary_language="JavaScript",
        framework="React", package_manager="npm", install_command="npm install",
        run_command="npm run dev", test_command="",
        files=[
            FileSpec(path="src/App.jsx", description="App", file_type="source"),
            FileSpec(
                path="src/main.jsx", description="entry", file_type="source",
                internal_dependencies=["src/App.jsx"],
            ),
        ],
    )
    review = CriticReview(
        approved=False, summary="logic defect",
        findings=[ReviewFinding(
            severity="high", file_path="src/App.jsx", message="wrong state update",
            suggested_fix="Use one coherent input transition.",
        )],
    )

    assert MultiAgentPipeline._affected_files(blueprint, review) == ["src/App.jsx"]


def test_publish_integrity_rejects_vite_entry_without_script(tmp_path: Path) -> None:
    blueprint = ArchitectureBlueprint(
        project_name="web", summary="web", original_request="simple react app",
        tech_stack=["React", "Vite"], primary_language="JavaScript",
        framework="React", package_manager="npm", install_command="npm install",
        run_command="npm run dev", test_command="",
        files=[
            FileSpec(path="index.html", description="entry", file_type="config"),
            FileSpec(path="src/main.jsx", description="main", file_type="source"),
        ],
    )
    files = {
        "index.html": '<div id="root"></div>',
        "src/main.jsx": "console.log('entry');",
    }
    for path, content in files.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    error = MultiAgentPipeline._published_snapshot_error(blueprint, tmp_path, files)

    assert error is not None
    assert "does not load" in error


def test_high_finding_cannot_be_approved() -> None:
    blueprint = _contract_blueprint()
    review = CriticReview(
        approved=True, summary="approved despite issue",
        findings=[ReviewFinding(
            severity="high", file_path="app.py", message="broken",
            suggested_fix="repair it", criterion_ids=["APP-01"],
        )],
    )
    validation = ValidationResult(
        passed=True, verified=True, command="tests", exit_code=0, output="passed",
    )

    problems = MultiAgentPipeline._approval_problems(
        review, validation, blueprint,
        {spec.path: "content" for spec in blueprint.files},
    )

    assert "critic reported high or critical findings" in problems


def test_pipeline_refuses_to_mix_with_existing_project(tmp_path: Path) -> None:
    existing = tmp_path / "quicknote-cli"
    existing.mkdir()
    marker = existing / "keep.txt"
    marker.write_text("untouched", encoding="utf-8")
    pipeline = MultiAgentPipeline(
        client=None, model="mock", developer_client=None,
        output_dir=tmp_path, run_tests=True,
    )

    assert pipeline.run("Build a note-taking CLI") is False
    assert marker.read_text(encoding="utf-8") == "untouched"
