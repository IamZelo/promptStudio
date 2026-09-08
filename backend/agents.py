"""Backwards-compatibility module forwarding to modular components in src/.

Exports schemas and agent runner functions.
"""

from src.schemas import ArchitectureBlueprint, FileSpec, GeneratedFile
from src.agents.architect import run_architect_agent
from src.agents.developer import run_developer_agent

__all__ = [
    "ArchitectureBlueprint",
    "FileSpec",
    "GeneratedFile",
    "run_architect_agent",
    "run_developer_agent",
]
