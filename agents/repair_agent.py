"""Repair agent that fixes issues found by the validator.

Implements simple rule-based repairs that do not require an LLM:
- Adds missing objects mentioned in the prompt.
- Removes or maps unsupported objects.
- Fixes broken relations.
- Strengthens weak style elements.
"""

from __future__ import annotations

import copy
import logging

from agents.base_agent import BaseAgent
from schema.scene_schema import (
    CameraConfig,
    LightingConfig,
    Relation,
    RoomConfig,
    SceneGraph,
    SceneObject,
    ValidationReport,
)

logger = logging.getLogger(__name__)


class RepairAgent(BaseAgent):
    """Rule-based repair agent for scene graphs.

    Applies deterministic fixes to common validation issues.
    In the future this can be replaced with an LLM-based repair backend.
    """

    def __init__(self, backend: str = "mock") -> None:
        """Initialize the repair agent.

        Args:
            backend: Backend mode. Only "mock" (rule-based) is supported in MVP.
        """
        super().__init__(backend=backend)

    def repair(
        self,
        user_prompt: str,
        scene_graph: SceneGraph,
        validation_report: ValidationReport,
    ) -> SceneGraph:
        """Repair a scene graph based on validation feedback.

        Args:
            user_prompt: The original user prompt.
            scene_graph: The scene graph to repair.
            validation_report: The validation report with identified issues.

        Returns:
            A repaired (possibly modified) copy of the scene graph.
        """
        # Always use rule-based repair (rule repairs are comprehensive;
        # LLM-based repair is optional future work)
        return self._repair_rules(user_prompt, scene_graph, validation_report)

    def _repair_rules(
        self,
        user_prompt: str,
        scene_graph: SceneGraph,
        validation_report: ValidationReport,
    ) -> SceneGraph:
        """Apply rule-based repairs.

        This creates a deep copy of the scene graph and applies fixes in-place.

        Args:
            user_prompt: The original user prompt.
            scene_graph: The scene graph to repair.
            validation_report: The validation report.

        Returns:
            The repaired scene graph.
        """
        # Work on a deep copy so the original is preserved
        sg = copy.deepcopy(scene_graph)
        prompt_lower = user_prompt.lower()
        existing_ids = {obj.id for obj in sg.objects}
        existing_types = {obj.type for obj in sg.objects}
        repair_count = 0

        # --- Repair 1: Remove unsupported objects ---
        if validation_report.unsupported_objects:
            unsupported_set = set(validation_report.unsupported_objects)
            sg.objects = [
                obj for obj in sg.objects if obj.id not in unsupported_set
            ]
            # Also remove relations involving removed objects
            sg.relations = [
                rel for rel in sg.relations
                if rel.subject not in unsupported_set and rel.object not in unsupported_set
            ]
            repair_count += len(unsupported_set)
            logger.info(
                "Repair: removed %d unsupported objects: %s",
                len(unsupported_set),
                unsupported_set,
            )
            existing_ids = {obj.id for obj in sg.objects}

        # --- Repair 2: Add missing objects from prompt ---
        # Use a counter for unique IDs
        obj_counter = len(sg.objects)

        # Check for "poster" or "painting" in prompt
        if ("poster" in prompt_lower or "painting" in prompt_lower) and "poster" not in existing_types:
            obj_counter += 1
            sg.objects.append(SceneObject(
                id=f"poster_{obj_counter}",
                type="poster",
                description="a wall poster added by repair agent",
                semantic_position="back wall",
                size=[0.6, 0.03, 0.8],
                material="paper",
                color="blue",
                extra={"added_by": "repair_agent"},
            ))
            sg.relations.append(Relation(
                subject=f"poster_{obj_counter}",
                predicate="attached_to",
                object="back_wall",
            ))
            existing_ids.add(f"poster_{obj_counter}")
            existing_types.add("poster")
            repair_count += 1
            logger.info("Repair: added missing poster")

        # Check for "carpet" or "cozy" in prompt
        if ("carpet" in prompt_lower or ("cozy" in prompt_lower and "carpet" not in existing_types)):
            obj_counter += 1
            sg.objects.append(SceneObject(
                id=f"carpet_{obj_counter}",
                type="carpet",
                description="a soft carpet added by repair agent",
                semantic_position="center of the room",
                size=[2.0, 1.5, 0.03],
                material="fabric",
                color="dark red",
                extra={"added_by": "repair_agent"},
            ))
            sg.relations.append(Relation(
                subject=f"carpet_{obj_counter}",
                predicate="near",
                object="bed_1" if "bed_1" in existing_ids else sg.objects[0].id if sg.objects else "back_wall",
            ))
            existing_ids.add(f"carpet_{obj_counter}")
            existing_types.add("carpet")
            repair_count += 1
            logger.info("Repair: added missing carpet")

        # Check for neon/cyberpunk -> neon_light
        if ("neon" in prompt_lower or "cyberpunk" in prompt_lower) and "neon_light" not in existing_types:
            obj_counter += 1
            sg.objects.append(SceneObject(
                id=f"neon_{obj_counter}",
                type="neon_light",
                description="neon wall light added by repair agent",
                semantic_position="back wall",
                size=[1.0, 0.05, 0.1],
                material="emissive",
                color="magenta",
                extra={"added_by": "repair_agent"},
            ))
            sg.relations.append(Relation(
                subject=f"neon_{obj_counter}",
                predicate="attached_to",
                object="back_wall",
            ))
            existing_ids.add(f"neon_{obj_counter}")
            existing_types.add("neon_light")
            repair_count += 1
            logger.info("Repair: added missing neon_light")

        # Check for monitor without desk
        if "monitor" in existing_types and "desk" not in existing_types:
            obj_counter += 1
            sg.objects.append(SceneObject(
                id=f"desk_{obj_counter}",
                type="desk",
                description="desk added for monitor support by repair agent",
                semantic_position="center of the room",
                size=[1.6, 0.7, 0.75],
                material="wood",
                color="brown",
                extra={"added_by": "repair_agent"},
            ))
            existing_ids.add(f"desk_{obj_counter}")
            existing_types.add("desk")
            repair_count += 1
            logger.info("Repair: added desk for monitor support")

        # Check for monitor without "on desk" relation
        monitor_objects = [obj for obj in sg.objects if obj.type == "monitor"]
        desk_objects = [obj for obj in sg.objects if obj.type == "desk"]
        if monitor_objects and desk_objects:
            for mon in monitor_objects:
                has_on_relation = any(
                    rel.subject == mon.id and rel.predicate == "on"
                    for rel in sg.relations
                )
                if not has_on_relation:
                    # Find the closest desk or use the first one
                    target_desk = desk_objects[0].id
                    sg.relations.append(Relation(
                        subject=mon.id,
                        predicate="on",
                        object=target_desk,
                    ))
                    repair_count += 1
                    logger.info(
                        "Repair: added 'on' relation: %s on %s",
                        mon.id,
                        target_desk,
                    )

        # --- Repair 3: Fix invalid relations ---
        if validation_report.invalid_relations:
            # Remove relations that are flagged (simple approach: remove and re-add)
            valid_predicates = {"on", "near", "left_of", "right_of", "in_front_of",
                                "behind", "attached_to", "inside", "facing"}
            room_surfaces = {"back_wall", "front_wall", "left_wall", "right_wall", "ceiling", "floor"}
            valid_targets = existing_ids | room_surfaces

            fixed_relations = []
            for rel in sg.relations:
                if (rel.predicate in valid_predicates
                        and rel.subject in existing_ids
                        and rel.object in valid_targets):
                    fixed_relations.append(rel)
                else:
                    repair_count += 1
                    logger.info("Repair: removed invalid relation %s -> %s (%s)",
                                rel.subject, rel.object, rel.predicate)
            sg.relations = fixed_relations

        # --- Repair 4: Strengthen weak style elements ---
        if validation_report.weak_style_elements:
            for weak in validation_report.weak_style_elements:
                style_lower = weak.lower()
                if "neon" in style_lower and "neon_light" not in existing_types:
                    obj_counter += 1
                    sg.objects.append(SceneObject(
                        id=f"neon_{obj_counter}",
                        type="neon_light",
                        description="neon light for style enhancement",
                        semantic_position="ceiling",
                        size=[1.2, 0.04, 0.08],
                        material="emissive",
                        color="cyan",
                        extra={"added_by": "repair_agent", "reason": "style_enhancement"},
                    ))
                    sg.relations.append(Relation(
                        subject=f"neon_{obj_counter}",
                        predicate="attached_to",
                        object="ceiling",
                    ))
                    existing_types.add("neon_light")
                    repair_count += 1
                    logger.info("Repair: added neon_light for style enhancement")

                if "cozy" in style_lower and "carpet" not in existing_types:
                    obj_counter += 1
                    sg.objects.append(SceneObject(
                        id=f"carpet_{obj_counter}",
                        type="carpet",
                        description="carpet for cozy atmosphere",
                        semantic_position="center of the room",
                        size=[2.0, 1.5, 0.03],
                        material="fabric",
                        color="warm red",
                        extra={"added_by": "repair_agent", "reason": "style_enhancement"},
                    ))
                    existing_types.add("carpet")
                    repair_count += 1
                    logger.info("Repair: added carpet for cozy style")

        # --- Repair 5: Ensure lighting and camera exist ---
        if not sg.lighting:
            sg.lighting = LightingConfig(
                mood="neutral",
                main_colors=["white"],
                brightness="medium",
                use_emissive_lights=False,
            )
            repair_count += 1
            logger.info("Repair: added default lighting config")

        if not sg.camera:
            sg.camera = CameraConfig()
            repair_count += 1
            logger.info("Repair: added default camera config")

        # Update metadata
        sg.metadata["repaired"] = True
        sg.metadata["repair_count"] = repair_count
        sg.metadata["repair_backend"] = "rule_based"

        if repair_count > 0:
            logger.info("Repair: applied %d total fixes", repair_count)
        else:
            logger.info("Repair: no fixes needed")

        return sg

    def _repair_llm(
        self,
        user_prompt: str,
        scene_graph: SceneGraph,
        validation_report: ValidationReport,
    ) -> SceneGraph:
        """Placeholder for LLM-based repair.

        Args:
            user_prompt: The original user prompt.
            scene_graph: The scene graph to repair.
            validation_report: The validation report.

        Raises:
            NotImplementedError: Always — not implemented in MVP.
        """
        raise NotImplementedError(
            "LLM-based repair is not implemented in the MVP. "
            "Use --backend mock instead."
        )
