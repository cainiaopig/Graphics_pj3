"""Pydantic models for the BlenderSceneAgent scene graph.

These models define the intermediate representation (IR) between natural language
prompts and Blender procedural scene construction.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Room
# ---------------------------------------------------------------------------

class RoomConfig(BaseModel):
    """Configuration for the room/enclosure."""

    width: float = Field(default=6.0, ge=0.1, description="Room width along X axis (meters)")
    depth: float = Field(default=5.0, ge=0.1, description="Room depth along Y axis (meters)")
    height: float = Field(default=3.0, ge=0.1, description="Room height along Z axis (meters)")
    floor_material: str = Field(default="wood", description="Material name for the floor")
    wall_material: str = Field(default="paint", description="Material name for the walls")


# ---------------------------------------------------------------------------
# Scene Object
# ---------------------------------------------------------------------------

class SceneObject(BaseModel):
    """A single object placed in the scene."""

    id: str = Field(..., description="Unique identifier for this object")
    type: str = Field(..., description="Object type (see supported types)")
    description: str = Field(default="", description="Human-readable description")
    semantic_position: str = Field(
        default="center of the room",
        description="Semantic position description (e.g. 'left wall', 'on desk_1')",
    )
    size: list[float] = Field(
        default_factory=lambda: [1.0, 1.0, 1.0],
        description="Object size as [x, y, z] in meters",
    )
    material: str = Field(default="default", description="Material name")
    color: Optional[str] = Field(default=None, description="Color name or hex string")
    rotation: Optional[list[float]] = Field(
        default=None,
        description="Euler rotation [rx, ry, rz] in radians",
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional object-specific properties",
    )


# ---------------------------------------------------------------------------
# Relation
# ---------------------------------------------------------------------------

# Valid relation predicates
VALID_PREDICATES: set[str] = {
    "on",
    "near",
    "left_of",
    "right_of",
    "in_front_of",
    "behind",
    "attached_to",
    "inside",
    "facing",
}


class Relation(BaseModel):
    """A spatial or logical relation between two entities."""

    subject: str = Field(..., description="Subject object ID")
    predicate: str = Field(..., description="Relation type (on, near, left_of, etc.)")
    object: str = Field(..., description="Target object ID or room surface name")


# ---------------------------------------------------------------------------
# Lighting
# ---------------------------------------------------------------------------

class LightingConfig(BaseModel):
    """Lighting configuration for the scene."""

    mood: str = Field(default="neutral", description="Lighting mood descriptor")
    main_colors: list[str] = Field(default_factory=list, description="Dominant light colors")
    brightness: str = Field(default="medium", description="Brightness level: low, medium, high")
    use_emissive_lights: bool = Field(default=False, description="Whether to use emissive materials as lights")


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

class CameraConfig(BaseModel):
    """Camera configuration for rendering."""

    view: str = Field(default="perspective", description="Camera view type")
    position: list[float] = Field(
        default_factory=lambda: [4.5, -5.0, 3.0],
        description="Camera position [x, y, z]",
    )
    target: list[float] = Field(
        default_factory=lambda: [0.0, 0.0, 1.2],
        description="Camera look-at target [x, y, z]",
    )
    focal_length: float = Field(default=28.0, ge=1.0, description="Focal length in mm")
    resolution: list[int] = Field(
        default_factory=lambda: [1280, 720],
        description="Render resolution [width, height]",
    )


# ---------------------------------------------------------------------------
# Scene Graph (top-level)
# ---------------------------------------------------------------------------

class SceneGraph(BaseModel):
    """Top-level scene graph containing all scene elements."""

    scene_id: str = Field(..., description="Unique scene identifier")
    scene_type: str = Field(..., description="Scene type (bedroom, study_room, etc.)")
    style: list[str] = Field(default_factory=list, description="Style keywords")
    room: RoomConfig = Field(default_factory=RoomConfig, description="Room configuration")
    objects: list[SceneObject] = Field(default_factory=list, description="All objects in the scene")
    relations: list[Relation] = Field(default_factory=list, description="Relations between objects")
    lighting: LightingConfig = Field(default_factory=LightingConfig, description="Lighting configuration")
    camera: CameraConfig = Field(default_factory=CameraConfig, description="Camera configuration")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra metadata")


# ---------------------------------------------------------------------------
# Validation Report
# ---------------------------------------------------------------------------

class ValidationReport(BaseModel):
    """Report produced by the validator agent."""

    is_valid: bool = Field(default=True, description="Whether the scene graph is valid")
    missing_objects: list[str] = Field(default_factory=list, description="Objects from prompt missing in scene")
    unsupported_objects: list[str] = Field(default_factory=list, description="Objects with unsupported types")
    invalid_relations: list[str] = Field(default_factory=list, description="Invalid or broken relations")
    weak_style_elements: list[str] = Field(default_factory=list, description="Style elements not represented")
    suggestions: list[str] = Field(default_factory=list, description="Suggested improvements")
    warnings: list[str] = Field(default_factory=list, description="Non-critical warnings")
    score: float = Field(default=1.0, ge=0.0, le=1.0, description="Overall quality score 0.0-1.0")


# ---------------------------------------------------------------------------
# Visual Critique (placeholder for future VLM)
# ---------------------------------------------------------------------------

class VisualCritique(BaseModel):
    """Report produced by the visual critic agent (future)."""

    score: int = Field(default=5, ge=1, le=10, description="Quality score 1-10")
    visible_objects: list[str] = Field(default_factory=list)
    missing_or_unclear_objects: list[str] = Field(default_factory=list)
    style_issues: list[str] = Field(default_factory=list)
    geometry_issues: list[str] = Field(default_factory=list)
    camera_issues: list[str] = Field(default_factory=list)
    repair_suggestions: list[str] = Field(default_factory=list)
