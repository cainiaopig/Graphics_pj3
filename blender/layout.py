"""Layout utilities: convert semantic positions and relations into coordinates.

Coordinate convention:
    x axis: left-right   (positive = right)
    y axis: front-back   (positive = back)
    z axis: height       (positive = up)
    room center: origin (0, 0)
    floor top surface: z = 0
    back wall interior:  y = +room_depth/2
    front wall interior: y = -room_depth/2
    left wall interior:  x = -room_width/2
    right wall interior: x = +room_width/2

Usable room interior:
    x in [-room.width/2, room.width/2]
    y in [-room.depth/2, room.depth/2]
    z in [0, room.height]

This module does NOT require Blender. It computes all coordinates in pure Python
so the Blender side only needs to create geometry at the given positions.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WALL_THICKNESS = 0.08
FLOOR_THICKNESS = 0.08
MARGIN = 0.08

# Which object types belong to which category
FLOOR_OBJECT_TYPES = {
    "bed", "desk", "chair", "table", "sofa", "shelf", "bookshelf",
    "counter", "plant", "carpet", "door",
}

WALL_OBJECT_TYPES = {
    "window", "poster", "blackboard", "projector_screen",
    "menu_board", "warning_sign", "neon_light", "wall_decoration",
}

CEILING_OBJECT_TYPES = set()

# Objects placed ON other objects (not directly on floor/wall)
ON_TARGET_TYPES = {
    "monitor", "keyboard", "lamp", "book", "cup", "glowing_tube",
}

# Default sizes per type (used when scene graph provides no size)
DEFAULT_SIZES: dict[str, list[float]] = {
    "bed":              [2.2, 1.4, 0.55],
    "desk":             [1.6, 0.7, 0.75],
    "chair":            [0.5, 0.5, 0.9],
    "table":            [1.2, 0.8, 0.75],
    "sofa":             [2.0, 0.9, 0.85],
    "shelf":            [1.0, 0.3, 0.8],
    "bookshelf":        [0.9, 0.35, 2.0],
    "counter":          [1.8, 0.7, 1.1],
    "monitor":          [0.8, 0.08, 0.45],
    "keyboard":         [0.5, 0.15, 0.03],
    "lamp":             [0.25, 0.25, 0.55],
    "plant":            [0.35, 0.35, 0.6],
    "carpet":           [2.0, 1.5, 0.03],
    "poster":           [0.8, 0.03, 1.0],
    "blackboard":       [2.5, 0.05, 1.2],
    "projector_screen": [2.0, 0.04, 1.3],
    "menu_board":       [1.0, 0.03, 0.7],
    "glowing_tube":     [0.8, 0.06, 0.06],
    "warning_sign":     [0.4, 0.03, 0.3],
    "neon_light":       [1.4, 0.05, 0.12],
    "book":             [0.2, 0.14, 0.03],
    "cup":              [0.08, 0.08, 0.12],
    "window":           [1.6, 0.05, 1.1],
    "door":             [0.9, 0.06, 2.1],
    "wall_decoration":  [0.5, 0.03, 0.5],
}


# ---------------------------------------------------------------------------
# AABB — Axis-Aligned Bounding Box
# ---------------------------------------------------------------------------

@dataclass
class AABB:
    """Axis-aligned bounding box defined by center and size."""

    center: tuple[float, float, float]
    size: tuple[float, float, float]

    # -- Properties for each axis ------------------------------------------

    @property
    def min_x(self) -> float:
        return self.center[0] - self.size[0] / 2

    @property
    def max_x(self) -> float:
        return self.center[0] + self.size[0] / 2

    @property
    def min_y(self) -> float:
        return self.center[1] - self.size[1] / 2

    @property
    def max_y(self) -> float:
        return self.center[1] + self.size[1] / 2

    @property
    def min_z(self) -> float:
        return self.center[2] - self.size[2] / 2

    @property
    def max_z(self) -> float:
        return self.center[2] + self.size[2] / 2

    @property
    def width(self) -> float:
        return self.size[0]

    @property
    def depth(self) -> float:
        return self.size[1]

    @property
    def height(self) -> float:
        return self.size[2]

    def with_center(self, new_center: tuple[float, float, float]) -> AABB:
        """Return a new AABB with updated center."""
        return AABB(center=new_center, size=self.size)

    def as_dict(self) -> dict[str, Any]:
        return {
            "center": list(self.center),
            "size": list(self.size),
            "min": [self.min_x, self.min_y, self.min_z],
            "max": [self.max_x, self.max_y, self.max_z],
        }


# ---------------------------------------------------------------------------
# PlacedObject — object with category
# ---------------------------------------------------------------------------

@dataclass
class PlacedObject:
    """An object with its resolved position and AABB."""

    id: str
    obj_type: str
    aabb: AABB
    category: str  # "floor", "wall", "ceiling", "on_target"


# ---------------------------------------------------------------------------
# Geometry utilities
# ---------------------------------------------------------------------------

def intersects(a: AABB, b: AABB, padding: float = 0.02) -> bool:
    """Check if two AABBs intersect (with optional padding)."""
    if a.max_x + padding <= b.min_x:
        return False
    if a.min_x >= b.max_x + padding:
        return False
    if a.max_y + padding <= b.min_y:
        return False
    if a.min_y >= b.max_y + padding:
        return False
    if a.max_z + padding <= b.min_z:
        return False
    if a.min_z >= b.max_z + padding:
        return False
    return True


def is_inside_room(aabb: AABB, room: dict[str, float], margin: float | None = None) -> bool:
    """Check if an AABB is fully inside the usable room volume.

    Args:
        aabb: The bounding box to check.
        room: Room dict with width, depth, height.
        margin: Margin from walls/floor/ceiling. Defaults to MARGIN.
    """
    if margin is None:
        margin = MARGIN

    rw = room.get("width", 6.0)
    rd = room.get("depth", 5.0)
    rh = room.get("height", 3.0)

    half_w = rw / 2
    half_d = rd / 2

    return (
        aabb.min_x >= -half_w + margin
        and aabb.max_x <= half_w - margin
        and aabb.min_y >= -half_d + margin
        and aabb.max_y <= half_d - margin
        and aabb.min_z >= 0.0 - 0.001
        and aabb.max_z <= rh - margin
    )


def clamp_to_room(aabb: AABB, room: dict[str, float], margin: float | None = None) -> AABB:
    """Clamp an AABB so it fits within the usable room volume.

    Shifts the center as needed. If the object is larger than the room
    in any dimension, it is centered in that dimension.

    Args:
        aabb: The bounding box to clamp.
        room: Room dict with width, depth, height.
        margin: Margin from walls. Defaults to MARGIN.
    """
    if margin is None:
        margin = MARGIN

    rw = room.get("width", 6.0)
    rd = room.get("depth", 5.0)
    rh = room.get("height", 3.0)

    half_w = rw / 2
    half_d = rd / 2

    cx, cy, cz = aabb.center
    sx, sy, sz = aabb.size

    # X axis
    if sx <= rw - 2 * margin:
        if aabb.min_x < -half_w + margin:
            cx = -half_w + margin + sx / 2
        elif aabb.max_x > half_w - margin:
            cx = half_w - margin - sx / 2
    else:
        cx = 0.0

    # Y axis
    if sy <= rd - 2 * margin:
        if aabb.min_y < -half_d + margin:
            cy = -half_d + margin + sy / 2
        elif aabb.max_y > half_d - margin:
            cy = half_d - margin - sy / 2
    else:
        cy = 0.0

    # Z axis — bottom must not go below floor
    if aabb.min_z < 0.0:
        cz = sz / 2
    if aabb.max_z > rh - margin:
        cz = rh - margin - sz / 2

    return AABB(center=(cx, cy, cz), size=(sx, sy, sz))


# ---------------------------------------------------------------------------
# Wall placement
# ---------------------------------------------------------------------------

def place_on_wall(
    center_x: float,
    center_y: float,
    object_width: float,
    object_depth: float,
    object_height: float,
    wall_name: str,
    room: dict[str, float],
    height_ratio: float = 0.55,
) -> tuple[float, float, float]:
    """Compute the center position for a wall-mounted object.

    Args:
        center_x: Desired x position (may be overridden by left/right walls).
        center_y: Desired y position (may be overridden by back/front walls).
        object_width: Object size in x.
        object_depth: Object size in y.
        object_height: Object size in z.
        wall_name: Which wall — back_wall, front_wall, left_wall, right_wall.
        room: Room dimensions dict.
        height_ratio: Vertical placement as fraction of room height (0=floor, 1=ceiling).

    Returns:
        (x, y, z) center position for the wall object.
    """
    rw = room.get("width", 6.0)
    rd = room.get("depth", 5.0)
    rh = room.get("height", 3.0)

    wall_name = wall_name.lower().strip()
    z = rh * height_ratio

    if "back_wall" in wall_name or wall_name == "back":
        y = rd / 2 - WALL_THICKNESS / 2 - object_depth / 2 - 0.005
        return (center_x, y, z)

    elif "front_wall" in wall_name or wall_name == "front":
        y = -rd / 2 + WALL_THICKNESS / 2 + object_depth / 2 + 0.005
        return (center_x, y, z)

    elif "left_wall" in wall_name or wall_name == "left":
        x = -rw / 2 + WALL_THICKNESS / 2 + object_width / 2 + 0.005
        return (x, center_y, z)

    elif "right_wall" in wall_name or wall_name == "right":
        x = rw / 2 - WALL_THICKNESS / 2 - object_width / 2 - 0.005
        return (x, center_y, z)

    else:
        # Unknown wall — return unchanged
        return (center_x, center_y, z)


# ---------------------------------------------------------------------------
# Normalize sizes
# ---------------------------------------------------------------------------

def _normalize_sizes(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure every object has a valid [x, y, z] size.

    Returns a deep copy with normalized sizes.
    """
    result = []
    for obj in objects:
        obj = copy.deepcopy(obj)
        raw = obj.get("size", [1.0, 1.0, 1.0])
        if not raw or len(raw) < 3:
            # Fall back to defaults
            obj_type = obj.get("type", "cube")
            defaults = DEFAULT_SIZES.get(obj_type, [1.0, 1.0, 1.0])
            raw = list(defaults)

        # Ensure at least 3 components
        size = list(raw[:3])
        while len(size) < 3:
            size.append(1.0)

        # Enforce minimums
        size[0] = max(size[0], 0.05)
        size[1] = max(size[1], 0.03)
        size[2] = max(size[2], 0.02)

        obj["size"] = size
        result.append(obj)
    return result


# ---------------------------------------------------------------------------
# Categorize objects
# ---------------------------------------------------------------------------

def _categorize(obj_type: str) -> str:
    """Return the category for an object type."""
    if obj_type in FLOOR_OBJECT_TYPES:
        return "floor"
    if obj_type in WALL_OBJECT_TYPES:
        return "wall"
    if obj_type in CEILING_OBJECT_TYPES:
        return "ceiling"
    if obj_type in ON_TARGET_TYPES:
        return "on_target"
    # Guess based on typical sizes
    return "floor"


# ---------------------------------------------------------------------------
# Stage 2: Anchor assignment
# ---------------------------------------------------------------------------

def _assign_anchors(
    objects: list[dict[str, Any]],
    room: dict[str, float],
    scene_type: str,
) -> dict[str, PlacedObject]:
    """Assign initial positions for all objects based on type and scene.

    Objects with 'on <target>' semantic positions are skipped here —
    they will be placed during relation application.
    """
    rw = room.get("width", 6.0)
    rd = room.get("depth", 5.0)
    rh = room.get("height", 3.0)

    placed: dict[str, PlacedObject] = {}

    # Count objects of each type for grid placement
    type_counts: dict[str, int] = {}
    floor_index = 0
    wall_index = 0

    for obj in objects:
        oid = obj["id"]
        obj_type = obj.get("type", "cube")
        size = obj.get("size", [1.0, 1.0, 1.0])
        sx, sy, sz = float(size[0]), float(size[1]), float(size[2])
        category = _categorize(obj_type)
        sem_pos = obj.get("semantic_position", "").lower().strip()

        # Track type counts
        type_counts[obj_type] = type_counts.get(obj_type, 0) + 1
        t_idx = type_counts[obj_type]

        # --- Objects placed ON something else: defer to relation stage ---
        if sem_pos.startswith("on "):
            continue

        # --- Wall objects ---
        if category == "wall":
            wall_name, height_ratio = _resolve_wall_target(sem_pos, obj_type, scene_type, room)
            cx, cy = _wall_xy_for_type(obj_type, scene_type, room, wall_index)
            cz = rh * height_ratio
            px, py, pz = place_on_wall(cx, cy, sx, sy, sz, wall_name, room, height_ratio)
            placed[oid] = PlacedObject(
                id=oid, obj_type=obj_type,
                aabb=AABB(center=(px, py, pz), size=(sx, sy, sz)),
                category="wall",
            )
            wall_index += 1
            continue

        # --- Floor objects ---
        center_z = sz / 2  # sitting on floor
        if obj_type == "carpet":
            center_z = sz / 2 + 0.005  # slightly above floor

        if scene_type == "bedroom":
            cx, cy = _bedroom_anchor(obj_type, t_idx, room, floor_index)
        elif scene_type == "classroom":
            cx, cy = _classroom_anchor(obj_type, t_idx, room, floor_index)
        elif scene_type == "coffee_shop":
            cx, cy = _coffee_shop_anchor(obj_type, t_idx, room, floor_index)
        elif scene_type == "laboratory":
            cx, cy = _laboratory_anchor(obj_type, t_idx, room, floor_index)
        elif scene_type == "study_room":
            cx, cy = _study_room_anchor(obj_type, t_idx, room, floor_index)
        else:
            cx, cy = _generic_anchor(obj_type, t_idx, room, floor_index)

        placed[oid] = PlacedObject(
            id=oid, obj_type=obj_type,
            aabb=AABB(center=(cx, cy, center_z), size=(sx, sy, sz)),
            category="floor",
        )
        floor_index += 1

    return placed


def _resolve_wall_target(
    sem_pos: str,
    obj_type: str,
    scene_type: str,
    room: dict[str, float],
) -> tuple[str, float]:
    """Determine which wall and height ratio a wall object should use."""
    wall = "back_wall"
    height_ratio = 0.55

    # Check semantic position for wall hints
    if "left wall" in sem_pos or "left side" in sem_pos:
        wall = "left_wall"
    elif "right wall" in sem_pos or "right side" in sem_pos:
        wall = "right_wall"
    elif "back wall" in sem_pos:
        wall = "back_wall"
    elif "front wall" in sem_pos:
        wall = "front_wall"
    elif "ceiling" in sem_pos:
        height_ratio = 0.88

    # Adjust height by type
    if obj_type in ("window",):
        height_ratio = 0.5
    elif obj_type in ("neon_light",):
        height_ratio = 0.78
    elif obj_type in ("blackboard", "projector_screen"):
        height_ratio = 0.5
    elif obj_type in ("menu_board",):
        height_ratio = 0.6
    elif obj_type in ("warning_sign",):
        height_ratio = 0.7
    elif obj_type in ("poster", "wall_decoration"):
        height_ratio = 0.55

    return wall, height_ratio


def _wall_xy_for_type(
    obj_type: str,
    scene_type: str,
    room: dict[str, float],
    index: int,
) -> tuple[float, float]:
    """Return a default (x, y) coordinate for a wall object before
    the wall attachment function corrects the perpendicular axis."""
    rw = room.get("width", 6.0)
    rd = room.get("depth", 5.0)

    # Default: back wall, spread across width
    spread = rw * 0.7
    if index == 0:
        cx = 0.0
    elif index == 1:
        cx = spread * 0.35
    elif index == 2:
        cx = -spread * 0.35
    else:
        cx = (-spread * 0.35) + (index - 2) * 0.6

    cy = rd / 2
    return (cx, cy)


def _bedroom_anchor(
    obj_type: str, t_idx: int, room: dict[str, float], floor_idx: int,
) -> tuple[float, float]:
    """Deterministic anchors for bedroom scene."""
    rw = room.get("width", 6.0)
    rd = room.get("depth", 5.0)

    if obj_type == "bed":
        return (-rw * 0.27, rd * 0.25)
    elif obj_type == "desk":
        return (rw * 0.28, rd * 0.22)
    elif obj_type == "chair":
        # Near desk — will be adjusted by relations if present,
        # otherwise default
        return (rw * 0.28, rd * 0.05)
    elif obj_type == "carpet":
        return (0.0, 0.0)
    elif obj_type == "plant":
        corners = [(-rw * 0.38, rd * 0.3), (rw * 0.38, -rd * 0.3)]
        idx = (t_idx - 1) % len(corners)
        return corners[idx]
    elif obj_type == "door":
        return (0.0, -rd / 2 + 0.2)
    elif obj_type == "shelf" or obj_type == "bookshelf":
        if t_idx == 1:
            return (-rw * 0.38, rd * 0.15)
        return (rw * 0.38, rd * 0.15)
    elif obj_type == "sofa":
        return (-rw * 0.2, -rd * 0.15)
    else:
        # Spread other floor objects
        return _spread_position(floor_idx, room)


def _classroom_anchor(
    obj_type: str, t_idx: int, room: dict[str, float], floor_idx: int,
) -> tuple[float, float]:
    """Deterministic anchors for classroom scene."""
    rw = room.get("width", 6.0)
    rd = room.get("depth", 5.0)

    if obj_type == "desk" or obj_type == "table":
        # Grid: 2 columns, rows from front
        col = (t_idx - 1) % 3
        row = (t_idx - 1) // 3
        x = (col - 1) * 1.2
        y = -rd * 0.1 + row * 1.0
        return (x, y)
    elif obj_type == "chair":
        col = (t_idx - 1) % 3
        row = (t_idx - 1) // 3
        x = (col - 1) * 1.2
        y = -rd * 0.1 + row * 1.0 - 0.6
        return (x, y)
    elif obj_type == "shelf" or obj_type == "bookshelf":
        return (-rw * 0.4, rd * 0.2)
    else:
        return _spread_position(floor_idx, room)


def _coffee_shop_anchor(
    obj_type: str, t_idx: int, room: dict[str, float], floor_idx: int,
) -> tuple[float, float]:
    """Deterministic anchors for coffee shop scene."""
    rw = room.get("width", 6.0)
    rd = room.get("depth", 5.0)

    if obj_type == "counter":
        return (rw * 0.2, rd * 0.3)
    elif obj_type == "table":
        col = (t_idx - 1) % 2
        row = (t_idx - 1) // 2
        x = (col - 0.5) * 1.5
        y = -rd * 0.1 + row * 1.2
        return (x, y)
    elif obj_type == "chair":
        col = (t_idx - 1) % 2
        row = (t_idx - 1) // 2
        x = (col - 0.5) * 1.5 + 0.5
        y = -rd * 0.1 + row * 1.2
        return (x, y)
    elif obj_type == "plant":
        corners = [(-rw * 0.38, rd * 0.3), (rw * 0.38, -rd * 0.3)]
        idx = (t_idx - 1) % len(corners)
        return corners[idx]
    else:
        return _spread_position(floor_idx, room)


def _laboratory_anchor(
    obj_type: str, t_idx: int, room: dict[str, float], floor_idx: int,
) -> tuple[float, float]:
    """Deterministic anchors for laboratory scene."""
    rw = room.get("width", 6.0)
    rd = room.get("depth", 5.0)

    if obj_type in ("desk", "table", "counter"):
        if t_idx == 1:
            return (-rw * 0.3, rd * 0.25)
        elif t_idx == 2:
            return (rw * 0.3, rd * 0.25)
        else:
            return (0.0, rd * 0.25)
    elif obj_type == "chair":
        if t_idx == 1:
            return (-rw * 0.3, rd * 0.05)
        return (rw * 0.3, rd * 0.05)
    elif obj_type in ("shelf", "bookshelf"):
        return (-rw * 0.4, rd * 0.15)
    else:
        return _spread_position(floor_idx, room)


def _study_room_anchor(
    obj_type: str, t_idx: int, room: dict[str, float], floor_idx: int,
) -> tuple[float, float]:
    """Deterministic anchors for study room scene."""
    rw = room.get("width", 6.0)
    rd = room.get("depth", 5.0)

    if obj_type == "desk":
        return (0.0, rd * 0.2)
    elif obj_type == "chair":
        return (0.0, 0.0)
    elif obj_type in ("shelf", "bookshelf"):
        if t_idx == 1:
            return (-rw * 0.38, rd * 0.2)
        return (rw * 0.38, rd * 0.2)
    elif obj_type == "sofa":
        return (-rw * 0.2, -rd * 0.15)
    elif obj_type == "carpet":
        return (0.0, 0.0)
    elif obj_type == "plant":
        return (rw * 0.35, -rd * 0.2)
    else:
        return _spread_position(floor_idx, room)


def _generic_anchor(
    obj_type: str, t_idx: int, room: dict[str, float], floor_idx: int,
) -> tuple[float, float]:
    """Fallback anchor for unknown scene types."""
    return _spread_position(floor_idx, room)


def _spread_position(index: int, room: dict[str, float]) -> tuple[float, float]:
    """Spread objects evenly in a rough pattern."""
    rw = room.get("width", 6.0)
    rd = room.get("depth", 5.0)
    positions = [
        (-rw * 0.27, rd * 0.25),
        (rw * 0.28, rd * 0.22),
        (0.0, 0.0),
        (-rw * 0.25, -rd * 0.2),
        (rw * 0.25, -rd * 0.2),
        (-rw * 0.3, 0.0),
        (rw * 0.3, 0.0),
    ]
    return positions[index % len(positions)]


# ---------------------------------------------------------------------------
# Stage 3: Apply relations
# ---------------------------------------------------------------------------

def _apply_relations(
    placed: dict[str, PlacedObject],
    objects: list[dict[str, Any]],
    relations: list[dict[str, str]],
    room: dict[str, float],
) -> dict[str, PlacedObject]:
    """Adjust positions based on spatial relations.

    Also places objects that were skipped in anchor assignment
    (objects with 'on <target>' semantic positions).
    """
    rh = room.get("height", 3.0)
    obj_map: dict[str, dict[str, Any]] = {obj["id"]: obj for obj in objects}

    # First, handle objects that haven't been placed yet (on_target category)
    for obj in objects:
        oid = obj["id"]
        if oid in placed:
            continue
        obj_type = obj.get("type", "cube")
        size = obj.get("size", [1.0, 1.0, 1.0])
        sx, sy, sz = float(size[0]), float(size[1]), float(size[2])
        # Place at origin temporarily — will be fixed by relation
        placed[oid] = PlacedObject(
            id=oid, obj_type=obj_type,
            aabb=AABB(center=(0.0, 0.0, sz / 2), size=(sx, sy, sz)),
            category="on_target",
        )

    # Apply each relation
    for rel in relations:
        subj_id = rel.get("subject", "")
        pred = rel.get("predicate", "")
        target_id = rel.get("object", "")

        if subj_id not in placed:
            continue

        subj = placed[subj_id]
        target = placed.get(target_id)

        if pred == "on":
            if target is not None:
                subj.aabb = _rel_on(subj, target)
            else:
                # Target might be a room surface (e.g., floor, ceiling)
                _rel_attach_or_on_surface(subj, target_id, room)

        elif pred == "near":
            if target is not None:
                subj.aabb = _rel_near(subj, target)

        elif pred == "left_of":
            if target is not None:
                subj.aabb = _rel_left_of(subj, target)

        elif pred == "right_of":
            if target is not None:
                subj.aabb = _rel_right_of(subj, target)

        elif pred == "in_front_of":
            if target is not None:
                subj.aabb = _rel_in_front_of(subj, target)

        elif pred == "behind":
            if target is not None:
                subj.aabb = _rel_behind(subj, target)

        elif pred == "attached_to":
            _rel_attach_or_on_surface(subj, target_id, room)

        elif pred == "inside":
            if target is not None:
                tc = target.aabb.center
                subj.aabb = subj.aabb.with_center(tc)

    return placed


def _rel_on(subj: PlacedObject, target: PlacedObject) -> AABB:
    """Place subject on top of target, centered horizontally."""
    tc = target.aabb.center
    t_max_z = target.aabb.max_z
    sh = subj.aabb.height
    return subj.aabb.with_center((tc[0], tc[1], t_max_z + sh / 2 + 0.01))


def _rel_near(subj: PlacedObject, target: PlacedObject) -> AABB:
    """Place subject near target (offset in x and y, preserve z)."""
    tc = target.aabb.center
    sc = subj.aabb.center
    return subj.aabb.with_center((tc[0] + 0.5, tc[1] - 0.5, sc[2]))


def _rel_left_of(subj: PlacedObject, target: PlacedObject) -> AABB:
    """Place subject to the left of target."""
    tc = target.aabb.center
    ts = target.aabb.size
    sc = subj.aabb.center
    ss = subj.aabb.size
    new_x = tc[0] - ts[0] / 2 - ss[0] / 2 - 0.15
    return subj.aabb.with_center((new_x, tc[1], sc[2]))


def _rel_right_of(subj: PlacedObject, target: PlacedObject) -> AABB:
    """Place subject to the right of target."""
    tc = target.aabb.center
    ts = target.aabb.size
    sc = subj.aabb.center
    ss = subj.aabb.size
    new_x = tc[0] + ts[0] / 2 + ss[0] / 2 + 0.15
    return subj.aabb.with_center((new_x, tc[1], sc[2]))


def _rel_in_front_of(subj: PlacedObject, target: PlacedObject) -> AABB:
    """Place subject in front of target (more negative y)."""
    tc = target.aabb.center
    ts = target.aabb.size
    sc = subj.aabb.center
    ss = subj.aabb.size
    new_y = tc[1] - ts[1] / 2 - ss[1] / 2 - 0.15
    return subj.aabb.with_center((tc[0], new_y, sc[2]))


def _rel_behind(subj: PlacedObject, target: PlacedObject) -> AABB:
    """Place subject behind target (more positive y)."""
    tc = target.aabb.center
    ts = target.aabb.size
    sc = subj.aabb.center
    ss = subj.aabb.size
    new_y = tc[1] + ts[1] / 2 + ss[1] / 2 + 0.15
    return subj.aabb.with_center((tc[0], new_y, sc[2]))


def _rel_attach_or_on_surface(
    subj: PlacedObject, target_id: str, room: dict[str, float],
) -> None:
    """Handle attached_to or placement on a room surface."""
    surface = target_id.lower().strip()
    rh = room.get("height", 3.0)
    sx, sy, sz = subj.aabb.size

    if "back_wall" in surface:
        cx, cy, cz = place_on_wall(0.0, 0.0, sx, sy, sz, "back_wall", room)
        subj.aabb = AABB(center=(cx, cy, cz), size=(sx, sy, sz))
        subj.category = "wall"

    elif "front_wall" in surface:
        cx, cy, cz = place_on_wall(0.0, 0.0, sx, sy, sz, "front_wall", room)
        subj.aabb = AABB(center=(cx, cy, cz), size=(sx, sy, sz))
        subj.category = "wall"

    elif "left_wall" in surface:
        cx, cy, cz = place_on_wall(0.0, 0.0, sx, sy, sz, "left_wall", room)
        subj.aabb = AABB(center=(cx, cy, cz), size=(sx, sy, sz))
        subj.category = "wall"

    elif "right_wall" in surface:
        cx, cy, cz = place_on_wall(0.0, 0.0, sx, sy, sz, "right_wall", room)
        subj.aabb = AABB(center=(cx, cy, cz), size=(sx, sy, sz))
        subj.category = "wall"

    elif "ceiling" in surface:
        cz = rh - 0.1 - sz / 2
        subj.aabb = subj.aabb.with_center((0.0, 0.0, cz))
        subj.category = "ceiling"

    elif "floor" in surface:
        subj.aabb = subj.aabb.with_center((0.0, 0.0, sz / 2 + 0.005))
        subj.category = "floor"


# ---------------------------------------------------------------------------
# Stage 4: Clamp all objects to room
# ---------------------------------------------------------------------------

def _clamp_all(
    placed: dict[str, PlacedObject],
    room: dict[str, float],
) -> dict[str, PlacedObject]:
    """Clamp every object so it fits inside the room."""
    for oid, pobj in placed.items():
        pobj.aabb = clamp_to_room(pobj.aabb, room)
    return placed


# ---------------------------------------------------------------------------
# Stage 5: Collision resolution
# ---------------------------------------------------------------------------

def _resolve_collisions(
    placed: dict[str, PlacedObject],
    relations: list[dict[str, str]],
    room: dict[str, float],
) -> tuple[dict[str, PlacedObject], list[dict[str, Any]]]:
    """Detect and resolve collisions between floor objects.

    Returns:
        (updated placed dict, collisions_before list)
    """
    # Gather all relation pairs to skip
    on_pairs: set[tuple[str, str]] = set()
    for rel in relations:
        if rel.get("predicate") == "on":
            on_pairs.add((rel["subject"], rel["object"]))
            on_pairs.add((rel["object"], rel["subject"]))

    # Get ordered floor objects (non-wall, non-on_target)
    floor_objs = [
        (oid, pobj) for oid, pobj in placed.items()
        if pobj.category == "floor"
    ]

    # Priority: big furniture first
    priority_order = {"bed": 0, "sofa": 1, "desk": 2, "table": 3, "counter": 4,
                      "bookshelf": 5, "shelf": 6, "chair": 7, "plant": 8,
                      "carpet": 9, "door": 10}
    floor_objs.sort(key=lambda x: priority_order.get(x[1].obj_type, 50))

    # Detect collisions before resolution
    collisions_before: list[dict[str, Any]] = []
    floor_ids = [f[0] for f in floor_objs]
    for i in range(len(floor_ids)):
        for j in range(i + 1, len(floor_ids)):
            a_id, b_id = floor_ids[i], floor_ids[j]
            if (a_id, b_id) in on_pairs:
                continue
            a, b = placed[a_id], placed[b_id]
            if intersects(a.aabb, b.aabb):
                collisions_before.append({
                    "object_a": a_id,
                    "object_b": b_id,
                    "overlap": _compute_overlap(a.aabb, b.aabb),
                })

    # Resolve collisions
    warnings: list[str] = []
    resolved_ids: set[str] = set()
    shifts = [0.3, -0.3, 0.6, -0.6, 0.9, -0.9, 1.2, -1.2, 1.5, -1.5,
              0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    for attempt in range(20):
        any_collision = False
        for i in range(len(floor_ids)):
            for j in range(i + 1, len(floor_ids)):
                a_id, b_id = floor_ids[i], floor_ids[j]
                if (a_id, b_id) in on_pairs:
                    continue
                a, b = placed[a_id], placed[b_id]

                if intersects(a.aabb, b.aabb, padding=0.01):
                    any_collision = True
                    # Try to shift the later object
                    later = b if priority_order.get(b.obj_type, 50) >= priority_order.get(a.obj_type, 50) else a
                    later_id = later.id

                    if later_id in resolved_ids and attempt > 10:
                        continue

                    shift = shifts[attempt % len(shifts)]
                    axis = "x" if attempt % 2 == 0 else "y"
                    cx, cy, cz = later.aabb.center

                    if axis == "x":
                        new_center = (cx + shift, cy, cz)
                    else:
                        new_center = (cx, cy + shift, cz)

                    later.aabb = later.aabb.with_center(new_center)
                    later.aabb = clamp_to_room(later.aabb, room)
                    resolved_ids.add(later_id)

        if not any_collision:
            break
    else:
        warnings.append(f"Could not resolve all collisions after 20 attempts")

    # Detect collisions after resolution
    collisions_after: list[dict[str, Any]] = []
    for i in range(len(floor_ids)):
        for j in range(i + 1, len(floor_ids)):
            a_id, b_id = floor_ids[i], floor_ids[j]
            if (a_id, b_id) in on_pairs:
                continue
            a, b = placed[a_id], placed[b_id]
            if intersects(a.aabb, b.aabb):
                collisions_after.append({
                    "object_a": a_id,
                    "object_b": b_id,
                    "overlap": _compute_overlap(a.aabb, b.aabb),
                })

    return placed, collisions_before, collisions_after, warnings


def _compute_overlap(a: AABB, b: AABB) -> dict[str, float]:
    """Compute the overlap between two AABBs."""
    ox = max(0.0, min(a.max_x, b.max_x) - max(a.min_x, b.min_x))
    oy = max(0.0, min(a.max_y, b.max_y) - max(a.min_y, b.min_y))
    oz = max(0.0, min(a.max_z, b.max_z) - max(a.min_z, b.min_z))
    return {"x": round(ox, 4), "y": round(oy, 4), "z": round(oz, 4)}


# ---------------------------------------------------------------------------
# Stage 6: Generate layout report
# ---------------------------------------------------------------------------

def _generate_report(
    placed: dict[str, PlacedObject],
    collisions_before: list[dict[str, Any]],
    collisions_after: list[dict[str, Any]],
    out_of_bounds_before: list[str],
    out_of_bounds_after: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    """Build the layout report."""
    return {
        "objects": {
            oid: {
                "type": pobj.obj_type,
                "category": pobj.category,
                "center": [round(v, 4) for v in pobj.aabb.center],
                "size": [round(v, 4) for v in pobj.aabb.size],
                "min": [round(pobj.aabb.min_x, 4),
                        round(pobj.aabb.min_y, 4),
                        round(pobj.aabb.min_z, 4)],
                "max": [round(pobj.aabb.max_x, 4),
                        round(pobj.aabb.max_y, 4),
                        round(pobj.aabb.max_z, 4)],
            }
            for oid, pobj in placed.items()
        },
        "collisions_before": collisions_before,
        "collisions_after": collisions_after,
        "out_of_bounds_before": out_of_bounds_before,
        "out_of_bounds_after": out_of_bounds_after,
        "warnings": warnings,
        "collision_count_before": len(collisions_before),
        "collision_count_after": len(collisions_after),
    }


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

def run_layout_pipeline(
    objects: list[dict[str, Any]],
    relations: list[dict[str, str]],
    room: dict[str, float],
    scene_type: str = "generic_room",
    debug: bool = False,
) -> dict[str, Any]:
    """Run the full geometry-safe layout pipeline.

    Stages:
      1. Normalize sizes
      2. Assign deterministic anchors by object type and scene
      3. Apply relations (on, near, attached_to, etc.)
      4. Clamp all objects to room bounds
      5. Resolve collisions between floor objects
      6. Generate layout report

    Args:
        objects: List of object dicts (each has id, type, size, semantic_position).
        relations: List of relation dicts (subject, predicate, object).
        room: Room dimensions dict (width, depth, height).
        scene_type: Type of scene (bedroom, classroom, etc.) — used for anchors.
        debug: If True, print debug info.

    Returns:
        Dict with keys:
          - positions: {object_id: (x, y, z) center}
          - aabbs: {object_id: AABB}
          - placed: {object_id: PlacedObject}
          - report: layout report dict
    """
    # Stage 1: Normalize
    objects = _normalize_sizes(objects)

    # Record out-of-bounds before
    # (we'll check after clamping)

    # Stage 2: Anchors
    placed = _assign_anchors(objects, room, scene_type)

    # Stage 3: Relations
    placed = _apply_relations(placed, objects, relations, room)

    # Check out-of-bounds before clamping
    out_of_bounds_before: list[str] = []
    for oid, pobj in placed.items():
        if not is_inside_room(pobj.aabb, room):
            out_of_bounds_before.append(oid)

    # Stage 4: Clamp
    placed = _clamp_all(placed, room)

    # Check out-of-bounds after clamping
    out_of_bounds_after: list[str] = []
    for oid, pobj in placed.items():
        if not is_inside_room(pobj.aabb, room):
            out_of_bounds_after.append(oid)

    # Stage 5: Collisions
    placed, collisions_before, collisions_after, collision_warnings = (
        _resolve_collisions(placed, relations, room)
    )

    # Stage 6: Report
    report = _generate_report(
        placed, collisions_before, collisions_after,
        out_of_bounds_before, out_of_bounds_after,
        collision_warnings,
    )

    # Build output
    positions: dict[str, tuple[float, float, float]] = {
        oid: pobj.aabb.center for oid, pobj in placed.items()
    }
    aabbs: dict[str, AABB] = {
        oid: pobj.aabb for oid, pobj in placed.items()
    }

    if debug:
        _print_debug(placed, collisions_before, collisions_after, collision_warnings)

    return {
        "positions": positions,
        "aabbs": aabbs,
        "placed": placed,
        "report": report,
    }


def _print_debug(
    placed: dict[str, PlacedObject],
    collisions_before: list[dict[str, Any]],
    collisions_after: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    """Print debug layout information."""
    print("\n[Layout Debug] =========================================")
    print(f"{'ID':<20} {'Type':<14} {'Category':<10} {'Center (x,y,z)':<32} {'Size (x,y,z)':<28}")
    print("-" * 100)
    for oid, pobj in placed.items():
        c = pobj.aabb.center
        s = pobj.aabb.size
        print(f"{oid:<20} {pobj.obj_type:<14} {pobj.category:<10} "
              f"({c[0]:.3f}, {c[1]:.3f}, {c[2]:.3f}){'':<16} "
              f"({s[0]:.3f}, {s[1]:.3f}, {s[2]:.3f})")

    if collisions_before:
        print(f"\n[Collisions Before] {len(collisions_before)}:")
        for c in collisions_before:
            print(f"  {c['object_a']} <-> {c['object_b']}  overlap={c['overlap']}")

    if collisions_after:
        print(f"\n[Collisions After] {len(collisions_after)}:")
        for c in collisions_after:
            print(f"  {c['object_a']} <-> {c['object_b']}  overlap={c['overlap']}")

    if warnings:
        print(f"\n[Warnings]:")
        for w in warnings:
            print(f"  {w}")

    print("[Layout Debug] End =====================================\n")


# ---------------------------------------------------------------------------
# Backward-compatible API (used by existing code)
# ---------------------------------------------------------------------------

def apply_relation_layout(
    objects: list[dict[str, Any]],
    relations: list[dict[str, str]],
    room: dict[str, float],
    scene_type: str = "generic_room",
    debug: bool = False,
) -> dict[str, tuple[float, float, float]]:
    """Backward-compatible wrapper around run_layout_pipeline.

    Returns just the positions dict (same signature as before).
    """
    result = run_layout_pipeline(objects, relations, room, scene_type, debug)
    return result["positions"]


def resolve_semantic_position(
    semantic_position: str,
    room: dict[str, float],
    object_size: Optional[list[float]] = None,
) -> tuple[float, float, float]:
    """Resolve a semantic position description into approximate (x, y, z) coordinates.

    This is kept for backward compatibility. New code should use
    run_layout_pipeline() for full geometry-safe placement.

    Args:
        semantic_position: Description like "left wall", "center of the room".
        room: Room dimensions dict (width, depth, height).
        object_size: Optional [x, y, z] size.

    Returns:
        (x, y, z) coordinate tuple.
    """
    rw = room.get("width", 6.0)
    rd = room.get("depth", 5.0)
    rh = room.get("height", 3.0)

    pos = semantic_position.lower().strip()

    floor_z = 0.0
    mid_z = rh / 2
    if object_size and len(object_size) >= 3:
        floor_z = object_size[2] / 2

    if pos.startswith("on "):
        return (0.0, 0.0, 0.5)
    if pos.startswith("near "):
        return (0.0, 0.0, floor_z)
    if pos.startswith("in front of "):
        return (0.0, -rd * 0.3, floor_z)
    if pos.startswith("behind "):
        return (0.0, rd * 0.3, floor_z)

    if "left wall" in pos or "left side" in pos:
        return (-rw / 2 + WALL_THICKNESS + MARGIN, 0.0, mid_z)
    if "right wall" in pos or "right side" in pos:
        return (rw / 2 - WALL_THICKNESS - MARGIN, 0.0, mid_z)
    if "back wall" in pos:
        return (0.0, rd / 2 - WALL_THICKNESS - MARGIN, mid_z)
    if "front wall" in pos:
        return (0.0, -rd / 2 + WALL_THICKNESS + MARGIN, mid_z)
    if "ceiling" in pos:
        return (0.0, 0.0, rh - 0.2)
    if "floor" in pos:
        return (0.0, 0.0, floor_z + 0.02)
    if "center" in pos:
        return (0.0, 0.0, floor_z)

    return (0.0, 0.0, floor_z)


def estimate_initial_location(
    obj: dict[str, Any],
    room: dict[str, float],
) -> tuple[float, float, float]:
    """Estimate initial (x, y, z) for a single object.

    Kept for backward compatibility.
    """
    semantic_pos = obj.get("semantic_position", "center of the room")
    size = obj.get("size", [1.0, 1.0, 1.0])
    return resolve_semantic_position(semantic_pos, room, size)
