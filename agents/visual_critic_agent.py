"""Visual critic agent for post-generation quality checks.

The critic can run fully offline: it compares the prompt with the final scene
graph, checks the pure-Python layout report, and verifies that render output was
created when an image path is provided. A future VLM backend can replace or
augment these checks, but the current implementation already produces real
quality signals instead of a fixed placeholder response.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from agents.base_agent import BaseAgent
from core.json_utils import load_json
from schema.scene_schema import SceneGraph, VisualCritique


class VisualCriticAgent(BaseAgent):
    """Critique generated scenes against the original prompt."""

    def __init__(self, backend: str = "mock") -> None:
        """Initialize the visual critic.

        Args:
            backend: Backend mode. The offline critic works for every backend;
                non-mock VLM critique remains future work.
        """
        super().__init__(backend=backend)

    def critique(
        self,
        user_prompt: str,
        image_path: str | None = None,
        scene_graph: SceneGraph | dict[str, Any] | None = None,
        scene_json_path: str | Path | None = None,
    ) -> dict:
        """Critique a generated scene.

        Args:
            user_prompt: The original user prompt.
            image_path: Optional rendered image path.
            scene_graph: Optional final scene graph object or dictionary.
            scene_json_path: Optional scene graph JSON path.

        Returns:
            A dictionary matching the VisualCritique schema.
        """
        if not self.is_mock:
            return self._critique_vlm(user_prompt, image_path or "")
        return self._critique_offline(user_prompt, image_path, scene_graph, scene_json_path)

    def _critique_offline(
        self,
        user_prompt: str,
        image_path: str | None,
        scene_graph: SceneGraph | dict[str, Any] | None,
        scene_json_path: str | Path | None,
    ) -> dict:
        graph_data = self._load_scene_graph(scene_graph, scene_json_path)
        object_types = {obj.get("type", "") for obj in graph_data.get("objects", [])}
        requested_types = self._requested_types(user_prompt)

        missing = sorted(requested_types - object_types)
        visible = sorted(t for t in object_types if t)
        style_issues = self._style_issues(user_prompt, graph_data)
        geometry_issues = self._geometry_issues(graph_data)
        camera_issues: list[str] = []

        if image_path:
            path = Path(image_path)
            if not path.exists() or path.stat().st_size == 0:
                camera_issues.append(f"render output missing or empty: {image_path}")

        suggestions: list[str] = []
        if missing:
            suggestions.append("Add or map missing prompt objects: " + ", ".join(missing))
        if geometry_issues:
            suggestions.append("Tune layout anchors or collision resolution for flagged geometry issues")
        if style_issues:
            suggestions.append("Reflect missing style words in scene styles, materials, or lighting")
        if camera_issues:
            suggestions.append("Render the final scene and verify camera framing")

        score = 10
        score -= min(4, len(missing))
        score -= min(3, len(geometry_issues))
        score -= min(2, len(style_issues))
        score -= min(2, len(camera_issues))
        score = max(1, score)

        return VisualCritique(
            score=score,
            visible_objects=visible,
            missing_or_unclear_objects=missing,
            style_issues=style_issues,
            geometry_issues=geometry_issues,
            camera_issues=camera_issues,
            repair_suggestions=suggestions,
        ).model_dump()

    @staticmethod
    def _load_scene_graph(
        scene_graph: SceneGraph | dict[str, Any] | None,
        scene_json_path: str | Path | None,
    ) -> dict[str, Any]:
        if isinstance(scene_graph, SceneGraph):
            return scene_graph.model_dump()
        if isinstance(scene_graph, dict):
            return scene_graph
        if scene_json_path:
            return load_json(scene_json_path)
        return {}

    @staticmethod
    def _requested_types(user_prompt: str) -> set[str]:
        # Reuse the planner's prompt patterns so generation and critique agree
        # on supported object mappings.
        from agents.planner_agent import PROMPT_OBJECT_PATTERNS

        prompt_lower = user_prompt.lower()
        requested: set[str] = set()
        for obj_type, patterns in PROMPT_OBJECT_PATTERNS.items():
            for pattern in patterns:
                if re.search(r"\b" + re.escape(pattern) + r"s?\b", prompt_lower):
                    requested.add(obj_type)
                    break
        if "tv stand" in prompt_lower:
            requested.update({"table", "monitor"})
        if "floor cushion" in prompt_lower or "tea room" in prompt_lower:
            requested.update({"chair", "sofa"})
        if "crystal ball" in prompt_lower or "floating" in prompt_lower:
            requested.update({"glowing_tube", "neon_light"})
        return requested

    @staticmethod
    def _style_issues(user_prompt: str, graph_data: dict[str, Any]) -> list[str]:
        prompt_lower = user_prompt.lower()
        styles = {str(s).lower() for s in graph_data.get("style", [])}
        issues = []
        for word in ("cozy", "cyberpunk", "futuristic", "japanese", "magical", "modern", "warm"):
            if word in prompt_lower and not any(word in style for style in styles):
                issues.append(f"style word not reflected: {word}")
        return issues

    @staticmethod
    def _geometry_issues(graph_data: dict[str, Any]) -> list[str]:
        if not graph_data.get("objects"):
            return ["scene graph has no objects"]
        try:
            from blender.layout import run_layout_pipeline

            room = graph_data.get("room", {})
            layout = run_layout_pipeline(
                objects=graph_data.get("objects", []),
                relations=graph_data.get("relations", []),
                room={
                    "width": room.get("width", 6.0),
                    "depth": room.get("depth", 5.0),
                    "height": room.get("height", 3.0),
                },
                scene_type=graph_data.get("scene_type", "generic_room"),
                debug=False,
            )
        except Exception as exc:
            return [f"layout critique failed: {exc}"]

        report = layout.get("report", {})
        issues: list[str] = []
        collision_count = report.get("collision_count_after", len(report.get("collisions_after", [])))
        if collision_count:
            issues.append(f"{collision_count} object collisions remain after layout")
        out_of_bounds = report.get("out_of_bounds_after", [])
        if out_of_bounds:
            issues.append(f"{len(out_of_bounds)} objects remain out of room bounds")
        warnings = report.get("warnings", [])
        issues.extend(str(w) for w in warnings[:3])
        return issues

    def _critique_vlm(self, user_prompt: str, image_path: str) -> dict:
        """Placeholder for future VLM-based image critique."""
        raise NotImplementedError(
            "VLM-based visual critique is not implemented yet. Use backend='mock' "
            "for deterministic offline critique."
        )
