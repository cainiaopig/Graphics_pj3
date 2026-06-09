"""Tests for the Pydantic scene schema models."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Ensure project root is on path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schema.scene_schema import (
    CameraConfig,
    LightingConfig,
    Relation,
    RoomConfig,
    SceneGraph,
    SceneObject,
    ValidationReport,
    VALID_PREDICATES,
)


class TestSceneObject:
    """Tests for SceneObject model."""

    def test_minimal_object_creation(self):
        """A SceneObject can be created with just id and type."""
        obj = SceneObject(id="test_1", type="cube")
        assert obj.id == "test_1"
        assert obj.type == "cube"
        assert obj.size == [1.0, 1.0, 1.0]  # default size
        assert obj.description == ""

    def test_object_size_defaults(self):
        """Default size is [1.0, 1.0, 1.0]."""
        obj = SceneObject(id="obj1", type="bed")
        assert len(obj.size) == 3
        assert obj.size == [1.0, 1.0, 1.0]

    def test_object_invalid_size_is_accepted_by_pydantic(self):
        """Pydantic does not validate size values — that's the validator's job."""
        obj = SceneObject(id="obj1", type="bed", size=[-1.0, 0.0, 3.0])
        assert obj.size == [-1.0, 0.0, 3.0]

    def test_object_rotation_defaults_to_none(self):
        """Rotation defaults to None."""
        obj = SceneObject(id="obj1", type="desk")
        assert obj.rotation is None

    def test_object_extra_defaults_to_empty_dict(self):
        """Extra field defaults to empty dict."""
        obj = SceneObject(id="obj1", type="lamp")
        assert obj.extra == {}


class TestRoomConfig:
    """Tests for RoomConfig model."""

    def test_default_room(self):
        """RoomConfig has sensible defaults."""
        room = RoomConfig()
        assert room.width == 6.0
        assert room.depth == 5.0
        assert room.height == 3.0
        assert room.floor_material == "wood"
        assert room.wall_material == "paint"


class TestRelation:
    """Tests for Relation model."""

    def test_valid_relation(self):
        """A relation with valid predicate is accepted."""
        rel = Relation(subject="monitor_1", predicate="on", object="desk_1")
        assert rel.subject == "monitor_1"
        assert rel.predicate == "on"
        assert rel.object == "desk_1"

    def test_any_predicate_accepted_by_model(self):
        """Pydantic model accepts any predicate string — validation is external."""
        rel = Relation(subject="a", predicate="invalid_predicate", object="b")
        assert rel.predicate == "invalid_predicate"

    def test_valid_predicates_set(self):
        """VALID_PREDICATES contains expected values."""
        assert "on" in VALID_PREDICATES
        assert "near" in VALID_PREDICATES
        assert "attached_to" in VALID_PREDICATES
        assert "left_of" in VALID_PREDICATES
        assert "right_of" in VALID_PREDICATES
        assert "facing" in VALID_PREDICATES


class TestLightingConfig:
    """Tests for LightingConfig."""

    def test_default_lighting(self):
        """LightingConfig has sensible defaults."""
        light = LightingConfig()
        assert light.mood == "neutral"
        assert light.brightness == "medium"
        assert light.use_emissive_lights is False


class TestCameraConfig:
    """Tests for CameraConfig."""

    def test_default_camera(self):
        """CameraConfig has sensible defaults."""
        cam = CameraConfig()
        assert cam.position == [4.5, -5.0, 3.0]
        assert cam.target == [0.0, 0.0, 1.2]
        assert cam.focal_length == 28.0
        assert cam.resolution == [1280, 720]


class TestSceneGraph:
    """Tests for the top-level SceneGraph model."""

    def test_minimal_scene_graph(self):
        """A SceneGraph can be created with just scene_id and scene_type."""
        sg = SceneGraph(scene_id="test_001", scene_type="bedroom")
        assert sg.scene_id == "test_001"
        assert sg.scene_type == "bedroom"
        assert isinstance(sg.room, RoomConfig)
        assert isinstance(sg.lighting, LightingConfig)
        assert isinstance(sg.camera, CameraConfig)
        assert sg.objects == []
        assert sg.relations == []

    def test_full_scene_graph(self):
        """A fully populated scene graph is valid."""
        sg = SceneGraph(
            scene_id="full_001",
            scene_type="bedroom",
            style=["cozy", "dark"],
            room=RoomConfig(width=6.0, depth=5.0, height=3.0),
            objects=[
                SceneObject(id="bed_1", type="bed", size=[2.2, 1.4, 0.55]),
                SceneObject(id="desk_1", type="desk", size=[1.6, 0.7, 0.75]),
            ],
            relations=[
                Relation(subject="bed_1", predicate="near", object="desk_1"),
            ],
            lighting=LightingConfig(mood="dark"),
            camera=CameraConfig(),
            metadata={"source": "test"},
        )
        assert len(sg.objects) == 2
        assert len(sg.relations) == 1


class TestValidationReport:
    """Tests for ValidationReport model."""

    def test_default_valid(self):
        """Default report is valid with score 1.0."""
        report = ValidationReport()
        assert report.is_valid is True
        assert report.score == 1.0
        assert report.missing_objects == []

    def test_invalid_report(self):
        """Report correctly records issues."""
        report = ValidationReport(
            is_valid=False,
            missing_objects=["carpet"],
            unsupported_objects=["spaceship"],
            invalid_relations=["alien -> wall"],
            score=0.5,
        )
        assert report.is_valid is False
        assert "carpet" in report.missing_objects
        assert "spaceship" in report.unsupported_objects


class TestExampleSceneGraphs:
    """Tests that example scene graph JSON files are loadable."""

    EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "scene_graphs"

    @pytest.mark.parametrize("filename", [
        "cyberpunk_bedroom.json",
        "cozy_study_room.json",
        "modern_classroom.json",
        "small_coffee_shop.json",
        "sci_fi_laboratory.json",
    ])
    def test_example_loads_as_scene_graph(self, filename):
        """Each example JSON can be loaded and validated as a SceneGraph."""
        filepath = self.EXAMPLES_DIR / filename
        assert filepath.exists(), f"Missing example: {filepath}"

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        sg = SceneGraph(**data)
        assert sg.scene_id is not None
        assert sg.scene_type is not None
        assert len(sg.objects) > 0

    @pytest.mark.parametrize("filename", [
        "cyberpunk_bedroom.json",
        "cozy_study_room.json",
        "modern_classroom.json",
        "small_coffee_shop.json",
        "sci_fi_laboratory.json",
    ])
    def test_example_objects_have_required_fields(self, filename):
        """Each example object has id, type, size."""
        filepath = self.EXAMPLES_DIR / filename
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        for obj in data.get("objects", []):
            assert "id" in obj, f"Missing id in {filename}"
            assert "type" in obj, f"Missing type for {obj.get('id', '?')} in {filename}"
            assert "size" in obj, f"Missing size for {obj['id']} in {filename}"
            assert "semantic_position" in obj, f"Missing semantic_position for {obj['id']} in {filename}"

    @pytest.mark.parametrize("filename", [
        "cyberpunk_bedroom.json",
        "cozy_study_room.json",
        "modern_classroom.json",
        "small_coffee_shop.json",
        "sci_fi_laboratory.json",
    ])
    def test_example_has_camera_and_lighting(self, filename):
        """Each example has camera and lighting configs."""
        filepath = self.EXAMPLES_DIR / filename
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "camera" in data, f"Missing camera in {filename}"
        assert "lighting" in data, f"Missing lighting in {filename}"
        assert "room" in data, f"Missing room in {filename}"
