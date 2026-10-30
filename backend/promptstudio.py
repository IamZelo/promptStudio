"""Run PromptStudio without installing its console command."""

from src.studio.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
