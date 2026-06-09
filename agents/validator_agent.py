"""Validator agent that checks scene graphs for correctness and completeness.

Implements rule-based validation that does not require an LLM.
Checks object uniqueness, supported types, valid relations, style coverage,
and prompt-object alignment.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from agents.base_agent import BaseAgent
from schema.scene_schema import (
    VALID_PREDICATES,
    SceneGraph,
    ValidationReport,
)

logger = logging.getLogger(__name__)

# Room surfaces that can be targets of relations
ROOM_SURFACES: set[str] = {
    "back_wall",
    "front_wall",
    "left_wall",
    "right_wall",
    "ceiling",
    "floor",
}


def _load_supported_config() -> dict[str, Any]:
    """Load supported types/relations from the default config YAML."""
    config_path = Path(__file__).resolve().parent.parent / "configs" / "default.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class ValidatorAgent(BaseAgent):
    """Rule-based validator for scene graphs.

    Checks performed:
    1. All object IDs are unique.
    2. All object types are in the supported list.
    3. All relation predicates are supported.
    4. Relation subjects refer to existing objects.
    5. Relation objects refer to existing objects or room surfaces.
    6. Important prompt keywords appear in the scene graph.
    7. Style words are represented in the scene graph.
    8. Each object has valid (positive) size values.
    9. Camera and lighting configurations are present.
    """

    def __init__(self, backend: str = "mock") -> None:
        """Initialize the validator.

        Args:
            backend: Backend mode. Only "mock" (rule-based) is supported in MVP.
        """
        super().__init__(backend=backend)
        config = _load_supported_config()
        self.supported_object_types: set[str] = {
            str(t) for t in config.get("supported_object_types", [])
        }
        self.supported_scene_types: set[str] = {
            str(t) for t in config.get("supported_scene_types", [])
        }
        self.supported_relations: set[str] = {
            str(r) for r in config.get("supported_relations", VALID_PREDICATES)
        }

    def validate(self, user_prompt: str, scene_graph: SceneGraph) -> ValidationReport:
        """Run all rule-based checks on the scene graph.

        Args:
            user_prompt: The original user prompt.
            scene_graph: The scene graph to validate.

        Returns:
            A ValidationReport with all findings.
        """
        if self.is_mock:
            return self._validate_rules(user_prompt, scene_graph)
        else:
            return self._validate_llm(user_prompt, scene_graph)

    def _validate_rules(
        self, user_prompt: str, scene_graph: SceneGraph
    ) -> ValidationReport:
        """Execute all rule-based validation checks.

        Args:
            user_prompt: The original user prompt.
            scene_graph: The scene graph to validate.

        Returns:
            A populated ValidationReport.
        """
        missing_objects: list[str] = []
        unsupported_objects: list[str] = []
        invalid_relations: list[str] = []
        weak_style_elements: list[str] = []
        suggestions: list[str] = []
        warnings: list[str] = []

        # 1. Check object ID uniqueness
        object_ids = [obj.id for obj in scene_graph.objects]
        duplicates = {oid for oid in object_ids if object_ids.count(oid) > 1}
        if duplicates:
            for dup in duplicates:
                invalid_relations.append(f"Duplicate object ID: '{dup}'")
                warnings.append(f"Duplicate object ID found: '{dup}'")

        # 2. Check supported object types
        for obj in scene_graph.objects:
            if obj.type not in self.supported_object_types:
                unsupported_objects.append(obj.id)
                warnings.append(
                    f"Unsupported object type '{obj.type}' for object '{obj.id}'"
                )

        # 3 & 4 & 5. Check relations
        valid_targets = set(object_ids) | ROOM_SURFACES
        for rel in scene_graph.relations:
            if rel.predicate not in self.supported_relations:
                invalid_relations.append(
                    f"Unsupported predicate '{rel.predicate}' in relation "
                    f"({rel.subject} -> {rel.object})"
                )
            if rel.subject not in object_ids:
                invalid_relations.append(
                    f"Relation subject '{rel.subject}' does not exist in objects"
                )
            if rel.object not in valid_targets:
                invalid_relations.append(
                    f"Relation object '{rel.object}' is not a valid object "
                    f"or room surface"
                )

        # 6. Check prompt keyword coverage
        prompt_lower = user_prompt.lower()
        # Extract nouns from the prompt (simple approach: check known object type names)
        prompt_nouns: set[str] = set()
        for obj_type in self.supported_object_types:
            # Match whole words; skip very short types to avoid false matches
            if len(obj_type) >= 3 and re.search(r"\b" + re.escape(obj_type) + r"\b", prompt_lower):
                prompt_nouns.add(obj_type)

        # Also check for multi-word patterns
        special_patterns: dict[str, str] = {
            "neon": "neon_light",
            "computer monitor": "monitor",
            "monitor": "monitor",
            "painting": "poster",
            "paintings": "poster",
            "wall painting": "poster",
            "wall paintings": "poster",
            "workbench": "desk",
            "workbenches": "desk",
            "pendant": "lamp",
            "pendant lamp": "lamp",
            "ceiling light": "lamp",
            "ceiling lights": "lamp",
        }

        scene_object_types = {obj.type for obj in scene_graph.objects}
        for pattern, obj_type in special_patterns.items():
            if pattern in prompt_lower and obj_type not in scene_object_types:
                missing_objects.append(pattern)

        # Check standard object types from prompt against scene
        for noun in prompt_nouns:
            if noun not in scene_object_types:
                # Skip if already captured by special patterns
                if noun not in [v for v in special_patterns.values()]:
                    missing_objects.append(noun)

        # 7. Check style word representation
        style_words_in_prompt: set[str] = set()
        style_keywords = {
            "cozy", "cyberpunk", "neon", "warm", "modern", "sci-fi", "sci fi",
            "futuristic", "industrial", "bright", "clean", "rustic", "traditional",
        }
        for sw in style_keywords:
            if sw in prompt_lower:
                style_words_in_prompt.add(sw)

        scene_styles_lower = {s.lower() for s in scene_graph.style}
        for sw in style_words_in_prompt:
            if sw not in scene_styles_lower:
                # Check if there's a close match
                found = any(sw in ss or ss in sw for ss in scene_styles_lower)
                if not found:
                    weak_style_elements.append(
                        f"Style word '{sw}' from prompt not reflected in scene styles"
                    )

        # 8. Check object sizes are positive
        for obj in scene_graph.objects:
            if len(obj.size) != 3:
                warnings.append(
                    f"Object '{obj.id}' size should have 3 values [x, y, z], "
                    f"got {len(obj.size)}"
                )
            elif any(s <= 0 for s in obj.size):
                warnings.append(
                    f"Object '{obj.id}' has non-positive size: {obj.size}"
                )
            elif any(s > 10.0 for s in obj.size):
                warnings.append(
                    f"Object '{obj.id}' has unusually large size: {obj.size}"
                )

        # 9. Check camera and lighting presence
        if not scene_graph.camera:
            warnings.append("Camera configuration is missing")
        if not scene_graph.lighting:
            warnings.append("Lighting configuration is missing")

        # 10. Check scene type validity
        if scene_graph.scene_type not in self.supported_scene_types:
            warnings.append(
                f"Scene type '{scene_graph.scene_type}' is not in supported types"
            )
            suggestions.append(
                f"Map scene type to one of: {', '.join(sorted(self.supported_scene_types))}"
            )

        # 11. Check for objects that should have 'on' relations
        stackable_types = {"monitor", "keyboard", "book", "cup", "lamp"}
        for obj in scene_graph.objects:
            if obj.type in stackable_types:
                has_on_relation = any(
                    rel.subject == obj.id and rel.predicate == "on"
                    for rel in scene_graph.relations
                )
                if not has_on_relation and "on " in obj.semantic_position.lower():
                    suggestions.append(
                        f"Object '{obj.id}' ({obj.type}) appears to be placed 'on' "
                        f"something but has no 'on' relation"
                    )

        # Compute overall validity and score
        is_valid = (
            len(missing_objects) == 0
            and len(unsupported_objects) == 0
            and len(invalid_relations) == 0
        )

        total_checks = 9
        failed_checks = sum([
            1 if missing_objects else 0,
            1 if unsupported_objects else 0,
            1 if invalid_relations else 0,
            1 if weak_style_elements else 0,
            1 if duplicates else 0,
        ])
        score = max(0.0, 1.0 - (failed_checks / total_checks))

        return ValidationReport(
            is_valid=is_valid,
            missing_objects=missing_objects,
            unsupported_objects=unsupported_objects,
            invalid_relations=invalid_relations,
            weak_style_elements=weak_style_elements,
            suggestions=suggestions,
            warnings=warnings,
            score=round(score, 2),
        )

    def _validate_llm(
        self, user_prompt: str, scene_graph: SceneGraph
    ) -> ValidationReport:
        """Placeholder for LLM-based validation.

        Args:
            user_prompt: The original user prompt.
            scene_graph: The scene graph to validate.

        Raises:
            NotImplementedError: Always — not implemented in MVP.
        """
        raise NotImplementedError(
            "LLM-based validation is not implemented in the MVP. "
            "Use --backend mock instead."
        )
