"""Tests for the rule-based validator agent."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schema.scene_schema import (
    CameraConfig,
    LightingConfig,
    Relation,
    RoomConfig,
    SceneGraph,
    SceneObject,
)
from agents.validator_agent import ValidatorAgent


class TestValidatorBasic:
    """Basic validator functionality tests."""

    def setup_method(self):
        self.validator = ValidatorAgent(backend="mock")

    def _make_valid_scene(self) -> SceneGraph:
        """Create a minimal valid scene graph."""
        return SceneGraph(
            scene_id="test_001",
            scene_type="bedroom",
            style=["cozy"],
            room=RoomConfig(),
            objects=[
                SceneObject(id="bed_1", type="bed", size=[2.0, 1.5, 0.5]),
                SceneObject(id="desk_1", type="desk", size=[1.5, 0.7, 0.75]),
                SceneObject(id="monitor_1", type="monitor", size=[0.8, 0.08, 0.45]),
            ],
            relations=[
                Relation(subject="monitor_1", predicate="on", object="desk_1"),
            ],
            lighting=LightingConfig(),
            camera=CameraConfig(),
        )

    def test_valid_scene_passes(self):
        """A well-formed scene graph passes validation."""
        sg = self._make_valid_scene()
        report = self.validator.validate("A bedroom with bed and desk", sg)
        assert report.is_valid is True
        assert report.score > 0.8

    def test_missing_object_detection(self):
        """Validator detects objects mentioned in prompt but missing from scene."""
        sg = self._make_valid_scene()
        # Prompt mentions "carpet" but scene doesn't have one
        report = self.validator.validate(
            "Create a cozy bedroom with a carpet and bed",
            sg,
        )
        # "carpet" is in the prompt but not in the scene
        # The validator should flag this
        assert len(report.missing_objects) > 0 or len(report.warnings) > 0

    def test_unsupported_object_detection(self):
        """Validator flags objects with unsupported types."""
        sg = SceneGraph(
            scene_id="test_002",
            scene_type="bedroom",
            objects=[
                SceneObject(id="alien_1", type="spaceship", size=[5.0, 5.0, 5.0]),
            ],
        )
        report = self.validator.validate("A bedroom", sg)
        assert "alien_1" in report.unsupported_objects

    def test_invalid_relation_detection(self):
        """Validator flags relations with invalid predicates or targets."""
        sg = SceneGraph(
            scene_id="test_003",
            scene_type="bedroom",
            objects=[
                SceneObject(id="bed_1", type="bed", size=[2.0, 1.5, 0.5]),
            ],
            relations=[
                Relation(subject="bed_1", predicate="floats_above", object="floor"),
                Relation(subject="ghost_1", predicate="on", object="bed_1"),
            ],
        )
        report = self.validator.validate("A bedroom", sg)
        # Should detect unsupported predicate and non-existent subject
        assert len(report.invalid_relations) > 0

    def test_duplicate_object_ids_detected(self):
        """Validator flags duplicate object IDs."""
        sg = SceneGraph(
            scene_id="test_004",
            scene_type="bedroom",
            objects=[
                SceneObject(id="bed_1", type="bed", size=[2.0, 1.5, 0.5]),
                SceneObject(id="bed_1", type="desk", size=[1.5, 0.7, 0.75]),
            ],
        )
        report = self.validator.validate("A bedroom", sg)
        assert len(report.warnings) > 0 or len(report.invalid_relations) > 0

    def test_non_positive_size_warning(self):
        """Validator warns about non-positive object sizes."""
        sg = SceneGraph(
            scene_id="test_005",
            scene_type="bedroom",
            objects=[
                SceneObject(id="bed_1", type="bed", size=[0.0, -1.0, 0.5]),
            ],
        )
        report = self.validator.validate("A bedroom", sg)
        assert len(report.warnings) > 0

    def test_style_word_coverage(self):
        """Validator checks if prompt style words appear in scene styles."""
        sg = self._make_valid_scene()
        # Scene style is ["cozy"], prompt mentions "cyberpunk"
        report = self.validator.validate(
            "Create a cyberpunk bedroom with neon lights",
            sg,
        )
        # Should flag weak cyberpunk style
        assert len(report.weak_style_elements) > 0 or report.score < 1.0

    def test_relation_to_room_surface_is_valid(self):
        """Relations targeting room surfaces (back_wall, etc.) are valid."""
        sg = SceneGraph(
            scene_id="test_006",
            scene_type="bedroom",
            objects=[
                SceneObject(id="poster_1", type="poster", size=[0.6, 0.03, 0.8]),
            ],
            relations=[
                Relation(subject="poster_1", predicate="attached_to", object="back_wall"),
            ],
        )
        report = self.validator.validate("A bedroom with poster on wall", sg)
        assert len(report.invalid_relations) == 0


class TestValidatorReportStructure:
    """Tests for validation report structure."""

    def setup_method(self):
        self.validator = ValidatorAgent(backend="mock")

    def test_report_has_all_fields(self):
        """Validation report contains all expected fields."""
        sg = SceneGraph(scene_id="t1", scene_type="bedroom")
        report = self.validator.validate("test", sg)
        assert hasattr(report, "is_valid")
        assert hasattr(report, "missing_objects")
        assert hasattr(report, "unsupported_objects")
        assert hasattr(report, "invalid_relations")
        assert hasattr(report, "weak_style_elements")
        assert hasattr(report, "suggestions")
        assert hasattr(report, "warnings")
        assert hasattr(report, "score")

    def test_report_score_in_range(self):
        """Score is always between 0.0 and 1.0."""
        sg = SceneGraph(scene_id="t1", scene_type="bedroom")
        report = self.validator.validate("test", sg)
        assert 0.0 <= report.score <= 1.0
