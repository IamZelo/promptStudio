"""Command-line entry point for the Multi-Agent Software Development Pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config import AppConfig, LlamaCppClient, get_genai_client
from src.pipeline import MultiAgentPipeline
from src.utils import display_banner, display_prompt, log_info, log_warning


DEFAULT_PROMPT = (
    "Build a modular command-line markdown note-taking tool called quicknote "
    "with commands to add notes with tags, list notes, search note content, and delete notes."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Collaborative Multi-Agent Software Development Pipeline."
    )
    parser.add_argument(
        "-p", "--prompt",
        type=str,
        default=None,
        help="Description of the project to build. If omitted, prompts interactively."
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        default="output",
        help="Base directory where generated projects will be saved (default: 'output')"
    )
    parser.add_argument(
        "-m", "--model",
        type=str,
        default=None,
        help="Gemini model used by Architect and Critic agents"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in mock/demo mode without calling the Gemini API."
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Prompt for user confirmation before starting the Developer phase."
    )
    parser.add_argument(
        "--llama-model",
        default=None,
        help="llama.cpp server model alias (default from LLAMA_CPP_MODEL).",
    )
    parser.add_argument(
        "--llama-url",
        default=None,
        help="llama.cpp server URL (default from LLAMA_CPP_BASE_URL).",
    )
    parser.add_argument(
        "--llama-timeout",
        type=int,
        default=None,
        help="Maximum seconds for one local-model response (default: 120).",
    )
    parser.add_argument(
        "--max-repair-attempts",
        type=int,
        default=5,
        help="Maximum QA/Critic repair loops (default: 5).",
    )
    validation_group = parser.add_mutually_exclusive_group()
    validation_group.add_argument(
        "--run-tests", dest="run_tests", action="store_true",
        help="Reserved for strict validation mode; demo QA currently checks syntax only.",
    )
    validation_group.add_argument(
        "--skip-tests", dest="run_tests", action="store_false",
        help="Skip generated tests (default in syntax-only demo QA).",
    )
    parser.set_defaults(run_tests=False)
    install_group = parser.add_mutually_exclusive_group()
    install_group.add_argument(
        "--install-dependencies", dest="install_dependencies", action="store_true",
        help="Reserved for strict validation mode; demo QA never installs dependencies.",
    )
    install_group.add_argument(
        "--skip-install", dest="install_dependencies", action="store_false",
        help="Skip dependency installation (default in syntax-only demo QA).",
    )
    parser.set_defaults(install_dependencies=False)
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Replace an existing final project only after a new snapshot is approved.",
    )
    parser.add_argument(
        "--test-timeout",
        type=int,
        default=60,
        help="Timeout in seconds for local syntax commands (default: 60).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    display_banner()

    config = AppConfig()
    model = args.model or config.gemini_model

    # Determine whether to use live client or mock mode
    if args.mock:
        log_info("Running in [bold yellow]MOCK / SIMULATION[/bold yellow] mode (no API calls).")
        client = None
        developer_client = None
    elif config.has_valid_api_key:
        client = get_genai_client(config.gemini_api_key)
        developer_client = LlamaCppClient(
            args.llama_url or config.llama_cpp_base_url,
            timeout=max(1, args.llama_timeout or config.llama_cpp_timeout),
            max_tokens=config.llama_cpp_max_tokens,
        )
        log_info(f"Connected to Google GenAI API with model: [bold cyan]{model}[/bold cyan]")
        log_info(
            "Developer Agent will use llama.cpp model: "
            f"[bold cyan]{args.llama_model or config.llama_cpp_model}[/bold cyan]"
        )
    else:
        log_warning("GEMINI_API_KEY not found in environment or .env file.")
        log_info("Automatically running in [bold yellow]MOCK / SIMULATION[/bold yellow] mode for demo.")
        log_info("To use live Gemini API, set GEMINI_API_KEY in your .env file.")
        client = None
        developer_client = None

    # Handle project prompt
    prompt = args.prompt
    if not prompt:
        print("\nEnter your project requirement: (Press Enter to use default demo prompt)")
        try:
            user_input = input("> ").strip()
            prompt = user_input if user_input else DEFAULT_PROMPT
        except (EOFError, KeyboardInterrupt):
            prompt = DEFAULT_PROMPT
            print()

    display_prompt(prompt)

    # Instantiate and execute pipeline
    pipeline = MultiAgentPipeline(
        client=client,
        model=model,
        output_dir=Path(args.output_dir),
        interactive=args.interactive,
        developer_client=developer_client,
        developer_model=args.llama_model or config.llama_cpp_model,
        max_iterations=max(0, args.max_repair_attempts),
        run_tests=args.run_tests,
        install_dependencies=args.install_dependencies,
        overwrite=args.overwrite,
        test_timeout=max(1, args.test_timeout),
    )

    success = pipeline.run(project_prompt=prompt)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
