"""Shared LangGraph state for the multi-agent workflow."""

from __future__ import annotations

from typing import Dict, List, Optional, TypedDict

from src.schemas import ArchitectureBlueprint, CriticReview, ValidationResult


class ProjectState(TypedDict):
    user_prompt: str
    blueprint: Optional[ArchitectureBlueprint]
    files: Dict[str, str]
    pending_files: List[str]
    generation_results: List[dict]
    validation: Optional[ValidationResult]
    review: Optional[CriticReview]
    feedback: str
    file_feedback: Dict[str, str]
    iteration: int
    max_iterations: int
    errors: List[str]
    generation_errors: List[str]
    workspace_root: str
    last_failure_signature: str
    status: str
