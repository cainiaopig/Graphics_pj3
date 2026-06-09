"""Visual critic agent placeholder.

In the future this agent will accept a rendered image and evaluate whether
it satisfies the original prompt. For the MVP, it returns a mock critique.
"""

from __future__ import annotations

from agents.base_agent import BaseAgent
from schema.scene_schema import VisualCritique


class VisualCriticAgent(BaseAgent):
    """Agent that critiques rendered images against the original prompt.

    For the MVP this is a placeholder that returns a mock critique.
    Future versions will integrate VLM-based image understanding.
    """

    def __init__(self, backend: str = "mock") -> None:
        """Initialize the visual critic.

        Args:
            backend: Backend mode. Only "mock" is supported in MVP.
        """
        super().__init__(backend=backend)

    def critique(self, user_prompt: str, image_path: str) -> dict:
        """Critique a rendered image against the original prompt.

        In mock mode, returns a placeholder critique with default values.
        In the future, this will use a VLM to analyze the image.

        Args:
            user_prompt: The original user prompt.
            image_path: Path to the rendered image file.

        Returns:
            A dictionary with critique results.
        """
        if self.is_mock:
            return self._critique_mock(user_prompt, image_path)
        else:
            return self._critique_vlm(user_prompt, image_path)

    def _critique_mock(self, user_prompt: str, image_path: str) -> dict:
        """Return a mock visual critique.

        Args:
            user_prompt: The original prompt (unused in mock).
            image_path: Path to the rendered image (unused in mock).

        Returns:
            A mock critique dictionary.
        """
        critique = VisualCritique(
            score=7,
            visible_objects=["room", "furniture", "lighting"],
            missing_or_unclear_objects=[],
            style_issues=["mock critique - no real image analysis performed"],
            geometry_issues=[],
            camera_issues=[],
            repair_suggestions=[
                "Real visual critique requires VLM integration (future work)"
            ],
        )
        return critique.model_dump()

    def _critique_vlm(self, user_prompt: str, image_path: str) -> dict:
        """Placeholder for VLM-based visual critique.

        Args:
            user_prompt: The original prompt.
            image_path: Path to the rendered image.

        Raises:
            NotImplementedError: Always — not implemented in MVP.
        """
        raise NotImplementedError(
            "VLM-based visual critique is not implemented in the MVP."
        )
