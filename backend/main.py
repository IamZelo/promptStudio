"""Command-line entry point for the Multi-Agent Software Development Pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config import AppConfig, get_genai_client
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
        help="Gemini model name (default from GEMINI_MODEL env or 'gemini-2.5-flash')"
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
    elif config.has_valid_api_key:
        client = get_genai_client(config.gemini_api_key)
        log_info(f"Connected to Google GenAI API with model: [bold cyan]{model}[/bold cyan]")
    else:
        log_warning("GEMINI_API_KEY not found in environment or .env file.")
        log_info("Automatically running in [bold yellow]MOCK / SIMULATION[/bold yellow] mode for demo.")
        log_info("To use live Gemini API, set GEMINI_API_KEY in your .env file.")
        client = None

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
    )

    success = pipeline.run(project_prompt=prompt)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
