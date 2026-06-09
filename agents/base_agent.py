"""Abstract base class for all agents in the pipeline."""

from __future__ import annotations

from abc import ABC


class BaseAgent(ABC):
    """Abstract base agent.

    All agents (planner, validator, repair, visual critic) inherit from this class.
    The backend parameter allows switching between mock and real LLM implementations.
    """

    def __init__(self, backend: str = "mock") -> None:
        """Initialize the agent.

        Args:
            backend: Backend mode. Supported values:
                - "mock": Use mock/rule-based logic (default, no API required).
                - "openai_compatible": Use an OpenAI-compatible API (future).
        """
        self.backend = backend

    @property
    def is_mock(self) -> bool:
        """Return True if the agent is using mock backend."""
        return self.backend == "mock"
