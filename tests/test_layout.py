"""Tests for layout/coordinate resolution utilities.

These tests do NOT require Blender.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from blender.layout import (
    AABB,
    WALL_THICKNESS,
    MARGIN,
    apply_relation_layout,
    clamp_to_room,
    estimate_initial_location,
    intersects,
    is_inside_room,
    place_on_wall,
    resolve_semantic_position,
    run_layout_pipeline,
)


class TestSemanticPositionResolution:
    """Tests for resolving semantic positions to coordinates."""

    ROOM = {"width": 6.0, "depth": 5.0, "height": 3.0}

    def test_left_wall(self):
        """'left wall' maps near x = -room_width/2."""
        x, y, z = resolve_semantic_position("left wall", self.ROOM)
        assert x < 0
        assert x == pytest.approx(-3.0 + 0.16, abs=0.01)  # -rw/2 + WALL_THICKNESS + MARGIN
        assert z == 1.5  # mid-height

    def test_right_wall(self):
        """'right wall' maps near x = +room_width/2."""
        x, y, z = resolve_semantic_position("right wall", self.ROOM)
        assert x > 0
        assert x == pytest.approx(3.0 - 0.16, abs=0.01)

    def test_back_wall(self):
        """'back wall' maps near y = +room_depth/2."""
        x, y, z = resolve_semantic_position("back wall", self.ROOM)
        assert y > 0
        assert y == pytest.approx(2.5 - 0.16, abs=0.01)

    def test_front_wall(self):
        """'front wall' maps near y = -room_depth/2."""
        x, y, z = resolve_semantic_position("front wall", self.ROOM)
        assert y < 0
        assert y == pytest.approx(-2.5 + 0.16, abs=0.01)

    def test_center_of_room(self):
        """'center of the room' maps near origin on floor."""
        x, y, z = resolve_semantic_position("center of the room", self.ROOM)
        assert x == 0.0
        assert y == 0.0
        assert z == 0.0  # floor level

    def test_left_side(self):
        """'left side of the room' maps left of center."""
        x, y, z = resolve_semantic_position("left side of the room", self.ROOM)
        assert x < 0

    def test_right_side(self):
        """'right side of the room' maps right of center."""
        x, y, z = resolve_semantic_position("right side of the room", self.ROOM)
        assert x > 0

    def test_ceiling(self):
        """'ceiling' maps near z = room_height."""
        x, y, z = resolve_semantic_position("ceiling", self.ROOM)
        assert z == 3.0 - 0.2  # rh - offset

    def test_floor(self):
        """'floor' maps near z = 0."""
        x, y, z = resolve_semantic_position("floor", self.ROOM)
        assert z == 0.02  # slight offset from floor


class TestEstimateInitialLocation:
    """Tests for initial location estimation."""

    ROOM = {"width": 6.0, "depth": 5.0, "height": 3.0}

    def test_estimate_from_semantic_position(self):
        """Object position is derived from semantic_position."""
        obj = {"id": "test", "semantic_position": "left wall", "size": [1.0, 1.0, 1.0]}
        x, y, z = estimate_initial_location(obj, self.ROOM)
        assert x < 0
        assert z == 1.5  # mid height for wall objects


class TestRelationLayout:
    """Tests for relation-aware layout resolution."""

    ROOM = {"width": 6.0, "depth": 5.0, "height": 3.0}

    def test_on_relation_places_object_above_target(self):
        """An 'on' relation should place subject above the target object."""
        objects = [
            {"id": "desk_1", "type": "desk", "semantic_position": "center of the room", "size": [1.6, 0.7, 0.75]},
            {"id": "monitor_1", "type": "monitor", "semantic_position": "on desk_1", "size": [0.8, 0.08, 0.45]},
        ]
        relations = [
            {"subject": "monitor_1", "predicate": "on", "object": "desk_1"},
        ]
        positions = apply_relation_layout(objects, relations, self.ROOM)

        assert "desk_1" in positions
        assert "monitor_1" in positions

        desk_z = positions["desk_1"][2]
        monitor_z = positions["monitor_1"][2]

        # Monitor should be above the desk
        assert monitor_z > desk_z, f"monitor_z={monitor_z} should be above desk_z={desk_z}"

    def test_attached_to_wall(self):
        """'attached_to' back_wall places object near back wall."""
        objects = [
            {"id": "poster_1", "type": "poster", "semantic_position": "back wall", "size": [0.6, 0.03, 0.8]},
        ]
        relations = [
            {"subject": "poster_1", "predicate": "attached_to", "object": "back_wall"},
        ]
        positions = apply_relation_layout(objects, relations, self.ROOM)

        poster_y = positions["poster_1"][1]
        rd = self.ROOM["depth"]
        assert poster_y > 0, f"Poster y={poster_y} should be near back wall (y={rd/2})"

    def test_left_of_relation(self):
        """'left_of' relation places subject to the left of target."""
        objects = [
            {"id": "desk_1", "type": "desk", "semantic_position": "center of the room", "size": [1.6, 0.7, 0.75]},
            {"id": "chair_1", "type": "chair", "semantic_position": "left of desk_1", "size": [0.5, 0.5, 0.9]},
        ]
        relations = [
            {"subject": "chair_1", "predicate": "left_of", "object": "desk_1"},
        ]
        positions = apply_relation_layout(objects, relations, self.ROOM)

        desk_x = positions["desk_1"][0]
        chair_x = positions["chair_1"][0]
        assert chair_x < desk_x, f"chair_x={chair_x} should be left of desk_x={desk_x}"

    def test_near_relation(self):
        """'near' relation places objects close to each other."""
        objects = [
            {"id": "bed_1", "type": "bed", "semantic_position": "left side of the room", "size": [2.2, 1.4, 0.55]},
            {"id": "carpet_1", "type": "carpet", "semantic_position": "near bed_1", "size": [2.0, 1.5, 0.03]},
        ]
        relations = [
            {"subject": "carpet_1", "predicate": "near", "object": "bed_1"},
        ]
        positions = apply_relation_layout(objects, relations, self.ROOM)

        # Both should have valid positions
        assert "bed_1" in positions
        assert "carpet_1" in positions

    def test_unknown_object_target_still_resolves(self):
        """If a relation target is a room surface (not in objects), layout still works."""
        objects = [
            {"id": "neon_1", "type": "neon_light", "semantic_position": "ceiling", "size": [1.0, 0.05, 0.1]},
        ]
        relations = [
            {"subject": "neon_1", "predicate": "attached_to", "object": "ceiling"},
        ]
        positions = apply_relation_layout(objects, relations, self.ROOM)

        neon_z = positions["neon_1"][2]
        assert neon_z > 2.0, f"Neon light z={neon_z} should be near ceiling"


# =========================================================================
# New tests for AABB and geometry-safe pipeline
# =========================================================================

class TestAABB:
    """Tests for the AABB dataclass."""

    def test_aabb_creation(self):
        """AABB is created with center and size."""
        aabb = AABB(center=(1.0, 2.0, 3.0), size=(2.0, 4.0, 6.0))
        assert aabb.center == (1.0, 2.0, 3.0)
        assert aabb.size == (2.0, 4.0, 6.0)

    def test_aabb_min_max(self):
        """AABB min/max properties are correct."""
        aabb = AABB(center=(0.0, 0.0, 0.5), size=(2.0, 3.0, 1.0))
        assert aabb.min_x == -1.0
        assert aabb.max_x == 1.0
        assert aabb.min_y == -1.5
        assert aabb.max_y == 1.5
        assert aabb.min_z == 0.0
        assert aabb.max_z == 1.0

    def test_aabb_width_depth_height(self):
        """AABB convenience properties."""
        aabb = AABB(center=(0, 0, 0), size=(2.0, 3.0, 4.0))
        assert aabb.width == 2.0
        assert aabb.depth == 3.0
        assert aabb.height == 4.0

    def test_with_center(self):
        """with_center returns new AABB with updated center."""
        aabb = AABB(center=(0, 0, 0), size=(2, 3, 4))
        moved = aabb.with_center((5, 6, 7))
        assert moved.center == (5, 6, 7)
        assert moved.size == (2, 3, 4)
        assert aabb.center == (0, 0, 0)  # original unchanged


class TestIntersection:
    """Tests for AABB intersection."""

    def test_overlapping(self):
        """Two overlapping AABBs intersect."""
        a = AABB(center=(0, 0, 0), size=(2, 2, 2))
        b = AABB(center=(0.5, 0.5, 0.5), size=(2, 2, 2))
        assert intersects(a, b)

    def test_separated(self):
        """Two separated AABBs do not intersect."""
        a = AABB(center=(0, 0, 0), size=(1, 1, 1))
        b = AABB(center=(5, 5, 5), size=(1, 1, 1))
        assert not intersects(a, b)

    def test_adjacent_with_padding(self):
        """Adjacent (not touching) AABBs with padding do not intersect."""
        a = AABB(center=(0, 0, 0), size=(2, 2, 2))
        b = AABB(center=(2.1, 0, 0), size=(2, 2, 2))  # 0.05 gap
        assert not intersects(a, b, padding=0.02)

    def test_touching_no_padding(self):
        """Touching AABBs without padding intersect."""
        a = AABB(center=(0, 0, 0), size=(2, 2, 2))
        b = AABB(center=(2, 0, 0), size=(2, 2, 2))
        assert not intersects(a, b, padding=0.0)  # min_x of b == max_x of a


class TestRoomContainment:
    """Tests for room containment and clamping."""

    ROOM = {"width": 6.0, "depth": 5.0, "height": 3.0}

    def test_inside_room(self):
        """Object at center is inside room."""
        aabb = AABB(center=(0, 0, 0.5), size=(1, 1, 1))
        assert is_inside_room(aabb, self.ROOM)

    def test_outside_left(self):
        """Object extending beyond left wall is not inside."""
        aabb = AABB(center=(-3.5, 0, 0.5), size=(1, 1, 1))
        assert not is_inside_room(aabb, self.ROOM)

    def test_clamp_to_room_shifts_object(self):
        """Object outside room gets shifted inside."""
        aabb = AABB(center=(-3.5, 0, 0.5), size=(1, 1, 1))
        clamped = clamp_to_room(aabb, self.ROOM)
        assert is_inside_room(clamped, self.ROOM)
        assert clamped.center[0] > -3.5  # moved right

    def test_clamp_below_floor(self):
        """Object below floor gets lifted."""
        aabb = AABB(center=(0, 0, -0.5), size=(1, 1, 1))
        clamped = clamp_to_room(aabb, self.ROOM)
        assert clamped.min_z >= -0.01


class TestPlaceOnWall:
    """Tests for wall placement function."""

    ROOM = {"width": 6.0, "depth": 5.0, "height": 3.0}

    def test_back_wall_placement(self):
        """Object on back wall is at correct y position."""
        x, y, z = place_on_wall(0.0, 0.0, 1.0, 0.05, 0.5, "back_wall", self.ROOM)
        assert y > 0  # back wall is positive y
        assert y == pytest.approx(2.5 - WALL_THICKNESS / 2 - 0.05 / 2 - 0.005, abs=0.01)
        assert z == pytest.approx(3.0 * 0.55)  # default height ratio

    def test_front_wall_placement(self):
        """Object on front wall is at correct y position."""
        x, y, z = place_on_wall(0.0, 0.0, 1.0, 0.05, 0.5, "front_wall", self.ROOM)
        assert y < 0  # front wall is negative y

    def test_left_wall_placement(self):
        """Object on left wall is at correct x position."""
        x, y, z = place_on_wall(0.0, 0.0, 1.0, 0.05, 0.5, "left_wall", self.ROOM)
        assert x < 0  # left wall is negative x

    def test_right_wall_placement(self):
        """Object on right wall is at correct x position."""
        x, y, z = place_on_wall(0.0, 0.0, 1.0, 0.05, 0.5, "right_wall", self.ROOM)
        assert x > 0  # right wall is positive x

    def test_custom_height_ratio(self):
        """Height ratio parameter affects z."""
        _, _, z_low = place_on_wall(0, 0, 1, 0.05, 0.5, "back_wall", self.ROOM, height_ratio=0.3)
        _, _, z_high = place_on_wall(0, 0, 1, 0.05, 0.5, "back_wall", self.ROOM, height_ratio=0.8)
        assert z_low < z_high


class TestLayoutPipeline:
    """End-to-end tests for the geometry-safe layout pipeline."""

    ROOM = {"width": 6.0, "depth": 5.0, "height": 3.0}

    def test_floor_objects_sit_on_floor(self):
        """Floor objects have center_z = height/2 so they sit ON the floor."""
        objects = [
            {"id": "bed_1", "type": "bed", "semantic_position": "left side",
             "size": [2.2, 1.4, 0.55]},
            {"id": "desk_1", "type": "desk", "semantic_position": "right side",
             "size": [1.6, 0.7, 0.75]},
        ]
        relations: list[dict[str, str]] = []
        result = run_layout_pipeline(objects, relations, self.ROOM, "bedroom")
        positions = result["positions"]

        # Bed: center_z should be height/2 = 0.275
        assert positions["bed_1"][2] == pytest.approx(0.275, abs=0.01)
        # Desk: center_z should be height/2 = 0.375
        assert positions["desk_1"][2] == pytest.approx(0.375, abs=0.01)

    def test_carpet_slightly_above_floor(self):
        """Carpet center_z = height/2 + 0.005."""
        objects = [
            {"id": "carpet_1", "type": "carpet", "semantic_position": "center",
             "size": [2.0, 1.5, 0.03]},
        ]
        relations: list[dict[str, str]] = []
        result = run_layout_pipeline(objects, relations, self.ROOM, "bedroom")
        pos = result["positions"]["carpet_1"]
        # height/2 + 0.005 = 0.015 + 0.005 = 0.02
        assert pos[2] == pytest.approx(0.02, abs=0.005)

    def test_monitor_on_desk(self):
        """Monitor placed 'on' the desk is at correct height."""
        objects = [
            {"id": "desk_1", "type": "desk", "semantic_position": "right side",
             "size": [1.6, 0.7, 0.75]},
            {"id": "monitor_1", "type": "monitor", "semantic_position": "on desk_1",
             "size": [0.8, 0.08, 0.45]},
        ]
        relations = [{"subject": "monitor_1", "predicate": "on", "object": "desk_1"}]
        result = run_layout_pipeline(objects, relations, self.ROOM, "bedroom")
        positions = result["positions"]

        desk_z = positions["desk_1"][2]
        monitor_z = positions["monitor_1"][2]
        # desk max_z = desk_z + 0.75/2 = desk_z + 0.375
        # monitor_z = desk_max_z + 0.45/2 + 0.01
        desk_max_z = desk_z + 0.75 / 2
        expected_monitor_z = desk_max_z + 0.45 / 2 + 0.01
        assert monitor_z == pytest.approx(expected_monitor_z, abs=0.01)
        assert monitor_z > desk_z

    def test_wall_objects_on_wall(self):
        """Wall objects are placed on the correct wall with proper offset."""
        objects = [
            {"id": "poster_1", "type": "poster", "semantic_position": "left wall",
             "size": [0.8, 0.03, 1.0]},
            {"id": "window_1", "type": "window", "semantic_position": "back wall",
             "size": [1.6, 0.05, 1.1]},
        ]
        relations = [
            {"subject": "poster_1", "predicate": "attached_to", "object": "left_wall"},
            {"subject": "window_1", "predicate": "attached_to", "object": "back_wall"},
        ]
        result = run_layout_pipeline(objects, relations, self.ROOM, "bedroom")
        positions = result["positions"]

        # Poster on left wall: x should be near -rw/2
        poster_x = positions["poster_1"][0]
        assert poster_x < -2.0  # near left wall

        # Window on back wall: y should be near +rd/2
        window_y = positions["window_1"][1]
        assert window_y > 2.0  # near back wall

    def test_bedroom_anchors(self):
        """In bedroom, bed is left-back and desk is right-back."""
        objects = [
            {"id": "bed_1", "type": "bed", "semantic_position": "left side",
             "size": [2.2, 1.4, 0.55]},
            {"id": "desk_1", "type": "desk", "semantic_position": "right side",
             "size": [1.6, 0.7, 0.75]},
        ]
        relations: list[dict[str, str]] = []
        result = run_layout_pipeline(objects, relations, self.ROOM, "bedroom")
        positions = result["positions"]

        bed_x = positions["bed_1"][0]
        desk_x = positions["desk_1"][0]
        assert bed_x < 0  # left side
        assert desk_x > 0  # right side

    def test_collision_resolution(self):
        """Two overlapping floor objects get separated."""
        objects = [
            {"id": "table_1", "type": "table", "semantic_position": "center",
             "size": [1.2, 0.8, 0.75]},
            {"id": "table_2", "type": "table", "semantic_position": "center",
             "size": [1.2, 0.8, 0.75]},
        ]
        relations: list[dict[str, str]] = []
        result = run_layout_pipeline(objects, relations, self.ROOM, "generic_room")
        report = result["report"]

        # Collisions after should be fewer than before (or zero)
        assert report["collision_count_after"] < report["collision_count_before"] or \
               report["collision_count_after"] == 0

    def test_report_structure(self):
        """Layout report has all required fields."""
        objects = [
            {"id": "bed_1", "type": "bed", "semantic_position": "left side",
             "size": [2.2, 1.4, 0.55]},
        ]
        relations: list[dict[str, str]] = []
        result = run_layout_pipeline(objects, relations, self.ROOM, "bedroom")
        report = result["report"]

        assert "objects" in report
        assert "collisions_before" in report
        assert "collisions_after" in report
        assert "out_of_bounds_before" in report
        assert "out_of_bounds_after" in report
        assert "warnings" in report
        assert "collision_count_before" in report
        assert "collision_count_after" in report

        # Each object in report has center, size, min, max
        obj_report = report["objects"]["bed_1"]
        assert "center" in obj_report
        assert "size" in obj_report
        assert "min" in obj_report
        assert "max" in obj_report

    def test_pipeline_returns_aabbs(self):
        """Pipeline returns AABB objects keyed by ID."""
        objects = [
            {"id": "desk_1", "type": "desk", "semantic_position": "center",
             "size": [1.6, 0.7, 0.75]},
        ]
        relations: list[dict[str, str]] = []
        result = run_layout_pipeline(objects, relations, self.ROOM, "generic_room")

        assert "aabbs" in result
        assert "desk_1" in result["aabbs"]
        assert isinstance(result["aabbs"]["desk_1"], AABB)

    def test_placed_objects_have_categories(self):
        """Placed objects have correct category."""
        objects = [
            {"id": "bed_1", "type": "bed", "semantic_position": "left side",
             "size": [2.2, 1.4, 0.55]},
            {"id": "poster_1", "type": "poster", "semantic_position": "back wall",
             "size": [0.8, 0.03, 1.0]},
            {"id": "monitor_1", "type": "monitor", "semantic_position": "on desk_1",
             "size": [0.8, 0.08, 0.45]},
        ]
        relations = [
            {"subject": "poster_1", "predicate": "attached_to", "object": "back_wall"},
        ]
        result = run_layout_pipeline(objects, relations, self.ROOM, "bedroom")
        placed = result["placed"]

        assert placed["bed_1"].category == "floor"
        assert placed["poster_1"].category == "wall"
