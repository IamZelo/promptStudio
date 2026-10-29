"""Backwards-compatibility module forwarding to modular components in src/.

Exports schemas and agent runner functions.
"""

from src.schemas import (
    AcceptanceCriterion,
    ArchitectureBlueprint,
    CriticReview,
    FileSpec,
    GeneratedFile,
    PackageDependency,
    ReviewFinding,
    ValidationCheck,
    ValidationResult,
)
from src.agents.architect import run_architect_agent
from src.agents.developer import run_developer_agent
from src.agents.critic import run_critic_agent
from src.agents.qa import run_qa_agent

__all__ = [
    "ArchitectureBlueprint",
    "AcceptanceCriterion",
    "FileSpec",
    "GeneratedFile",
    "PackageDependency",
    "CriticReview",
    "ReviewFinding",
    "ValidationCheck",
    "ValidationResult",
    "run_architect_agent",
    "run_developer_agent",
    "run_critic_agent",
    "run_qa_agent",
]
