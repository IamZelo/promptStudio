"""Project complexity inference shared by planning, implementation, and review."""

from __future__ import annotations

from typing import Literal

ComplexityProfile = Literal["simple", "standard", "advanced"]


def infer_complexity(project_prompt: str) -> ComplexityProfile:
    """Infer the smallest suitable engineering profile from the user's wording."""
    prompt = project_prompt.lower()
    advanced_markers = {
        "production", "enterprise", "scalable", "distributed", "microservice",
        "authentication", "authorization", "database", "deploy", "multi-tenant",
    }
    simple_markers = {
        "simple", "basic", "minimal", "small", "demo", "toy", "beginner",
    }
    if any(marker in prompt for marker in advanced_markers):
        return "advanced"
    if any(marker in prompt for marker in simple_markers):
        return "simple"
    return "standard"


def profile_guidance(profile: ComplexityProfile) -> str:
    if profile == "simple":
        return (
            "Keep the project intentionally small. Prefer JavaScript unless the user explicitly "
            "requests TypeScript. Avoid custom hooks, service layers, state libraries, elaborate "
            "configuration, and speculative features when one component or module is sufficient. "
            "Plan only the files needed to run and verify the requested behavior."
        )
    if profile == "advanced":
        return (
            "Use production-oriented boundaries and validation proportional to the explicitly "
            "requested operational, security, persistence, and deployment requirements."
        )
    return (
        "Use conventional modular structure, but avoid abstractions or infrastructure that are "
        "not justified by the stated requirements."
    )
