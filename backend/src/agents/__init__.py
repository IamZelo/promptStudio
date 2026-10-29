"""Agents package exporting Architect and Developer roles."""

from src.agents.architect import run_architect_agent
from src.agents.developer import run_developer_agent
from src.agents.critic import run_critic_agent
from src.agents.qa import run_qa_agent

__all__ = ["run_architect_agent", "run_developer_agent", "run_critic_agent", "run_qa_agent"]
