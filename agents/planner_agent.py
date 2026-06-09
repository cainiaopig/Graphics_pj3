"""Planner agent that converts natural language prompts into scene graphs.

Supports two backends:
- mock: Keyword-based selection from example scene graphs.
- openai_compatible: Placeholder for future LLM-based planning.
"""

from __future__ import annotations

import logging
from pathlib import Path

from agents.base_agent import BaseAgent
from core.json_utils import load_json
from schema.scene_schema import SceneGraph

logger = logging.getLogger(__name__)

# Mapping from prompt keywords to example scene graph files
KEYWORD_TO_SCENE: dict[str, str] = {
    "bedroom": "cyberpunk_bedroom.json",
    "study": "cozy_study_room.json",
    "classroom": "modern_classroom.json",
    "coffee": "small_coffee_shop.json",
    "laboratory": "sci_fi_laboratory.json",
    "lab": "sci_fi_laboratory.json",
}


class PlannerAgent(BaseAgent):
    """Agent responsible for generating a SceneGraph from a user prompt.

    In mock mode, it selects the best-matching example scene graph based on
    keyword matching against the prompt text.
    """

    def __init__(
        self,
        backend: str = "mock",
        examples_dir: str | Path | None = None,
    ) -> None:
        """Initialize the planner.

        Args:
            backend: Backend mode ("mock" or "openai_compatible").
            examples_dir: Directory containing example scene graph JSON files.
        """
        super().__init__(backend=backend)
        if examples_dir is None:
            examples_dir = Path(__file__).resolve().parent.parent / "examples" / "scene_graphs"
        self.examples_dir = Path(examples_dir)

    def plan(self, user_prompt: str) -> SceneGraph:
        """Generate a scene graph from a user prompt.

        Args:
            user_prompt: Natural language description of the desired scene.

        Returns:
            A SceneGraph instance.

        Raises:
            FileNotFoundError: If no matching example scene graph is found.
        """
        if self.is_mock:
            return self._plan_mock(user_prompt)
        else:
            return self._plan_openai(user_prompt)

    def _plan_mock(self, user_prompt: str) -> SceneGraph:
        """Mock planner: select scene graph by keyword matching.

        Searches the prompt (lowercased) for known keywords and loads the
        corresponding example JSON file.

        Args:
            user_prompt: The user's natural language prompt.

        Returns:
            A SceneGraph loaded from the matching example file.

        Raises:
            FileNotFoundError: If no keyword matches or the example file is missing.
        """
        prompt_lower = user_prompt.lower()

        matched_scene = None
        for keyword, filename in KEYWORD_TO_SCENE.items():
            if keyword in prompt_lower:
                matched_scene = filename
                logger.info("Planner matched keyword '%s' -> %s", keyword, filename)
                break

        if matched_scene is None:
            logger.warning(
                "No keyword matched in prompt. Falling back to generic_room. "
                "Prompt: '%s'",
                user_prompt,
            )
            matched_scene = "cyberpunk_bedroom.json"

        filepath = self.examples_dir / matched_scene
        if not filepath.exists():
            raise FileNotFoundError(
                f"Example scene graph not found: {filepath}\n"
                f"Keyword matched: {matched_scene}"
            )

        data = load_json(filepath)
        scene_graph = SceneGraph(**data)

        # Update metadata with the actual source prompt
        scene_graph.metadata["source_prompt"] = user_prompt
        scene_graph.metadata["planner_backend"] = "mock"

        logger.info("Planner loaded scene graph: %s", scene_graph.scene_id)
        return scene_graph

    def _plan_openai(self, user_prompt: str) -> SceneGraph:
        """Placeholder for OpenAI-compatible LLM planning.

        Args:
            user_prompt: The user's natural language prompt.

        Raises:
            NotImplementedError: Always — not implemented in MVP.
        """
        raise NotImplementedError(
            "OpenAI-compatible planner is not implemented in the MVP. "
            "Use --backend mock instead."
        )
