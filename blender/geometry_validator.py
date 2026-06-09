"""Geometry validator: checks for basic layout and geometry issues.

This module does NOT require Blender. It performs checks using AABB-based
computations from layout.py:

1. Object sizes are positive.
2. Objects are inside room bounds (using AABB containment).
3. Objects with 'on' relation have plausible z positions.
4. Wall-attached objects are near walls.
5. Very large objects are flagged.
"""

from __future__ import annotations

from typing import Any


# Import AABB utilities (pure Python, no bpy)
def _get_aabb_funcs():
    """Lazy-import AABB functions from blender.layout."""
    from blender.layout import AABB, is_inside_room
    return AABB, is_inside_room


def validate_geometry(
    objects: list[dict[str, Any]],
    relations: list[dict[str, str]],
    room: dict[str, float],
    positions: dict[str, tuple[float, float, float]],
) -> dict[str, Any]:
    """Run geometry validation checks.

    Args:
        objects: List of object dicts.
        relations: List of relation dicts.
        room: Room dimensions dict with width, depth, height.
        positions: Resolved (x, y, z) CENTER positions keyed by object ID.

    Returns:
        Dict with warnings and issues lists.
    """
    warnings: list[str] = []
    issues: list[str] = []

    rw = room.get("width", 6.0)
    rd = room.get("depth", 5.0)
    rh = room.get("height", 3.0)

    # Build lookup
    obj_by_id: dict[str, dict[str, Any]] = {obj["id"]: obj for obj in objects}

    # Use AABB-based checks if available
    try:
        AABB, is_inside_room = _get_aabb_funcs()
        use_aabb = True
    except Exception:
        use_aabb = False

    for obj in objects:
        oid = obj["id"]
        pos = positions.get(oid, (0, 0, 0))
        size = obj.get("size", [1.0, 1.0, 1.0])
        if len(size) < 3:
            size = [1.0, 1.0, 1.0]

        x, y, z = pos
        sx, sy, sz = size[0], size[1], size[2]

        # 1. Check positive sizes
        if any(s <= 0 for s in (sx, sy, sz)):
            issues.append(f"Object '{oid}' has non-positive size: [{sx}, {sy}, {sz}]")

        # 2. Check inside room bounds
        if use_aabb:
            aabb = AABB(center=pos, size=(sx, sy, sz))
            if not is_inside_room(aabb, room):
                if aabb.min_x < -rw / 2:
                    warnings.append(f"Object '{oid}' extends beyond left wall (min_x={aabb.min_x:.2f})")
                if aabb.max_x > rw / 2:
                    warnings.append(f"Object '{oid}' extends beyond right wall (max_x={aabb.max_x:.2f})")
                if aabb.min_y < -rd / 2:
                    warnings.append(f"Object '{oid}' extends beyond front wall (min_y={aabb.min_y:.2f})")
                if aabb.max_y > rd / 2:
                    warnings.append(f"Object '{oid}' extends beyond back wall (max_y={aabb.max_y:.2f})")
                if aabb.min_z < -0.01:
                    warnings.append(f"Object '{oid}' penetrates floor (min_z={aabb.min_z:.3f})")
                if aabb.max_z > rh:
                    warnings.append(f"Object '{oid}' extends above ceiling (max_z={aabb.max_z:.2f})")
        else:
            # Fallback to simple checks
            margin = 0.5
            half_sx = sx / 2
            half_sy = sy / 2
            if x - half_sx < -rw / 2 - margin:
                warnings.append(f"Object '{oid}' extends beyond left wall")
            if x + half_sx > rw / 2 + margin:
                warnings.append(f"Object '{oid}' extends beyond right wall")
            if y - half_sy < -rd / 2 - margin:
                warnings.append(f"Object '{oid}' extends beyond front wall")
            if y + half_sy > rd / 2 + margin:
                warnings.append(f"Object '{oid}' extends beyond back wall")
            if z + sz > rh + margin:
                warnings.append(f"Object '{oid}' extends above ceiling")
            if z < -margin:
                warnings.append(f"Object '{oid}' is below floor level")

        # 3. Check for very large objects
        if sx > rw * 0.8 or sy > rd * 0.8:
            warnings.append(f"Object '{oid}' is very large ({sx}x{sy}) relative to room ({rw}x{rd})")
        if sz > rh * 0.9:
            warnings.append(f"Object '{oid}' is nearly as tall as the room ({sz} vs {rh})")

        # 4. Check 'on' relations — subject should be above target's top surface
        for rel in relations:
            if rel.get("subject") == oid and rel.get("predicate") == "on":
                target_id = rel.get("object", "")
                target = obj_by_id.get(target_id)
                if target and target_id in positions:
                    tx, ty, tz = positions[target_id]
                    tsize = target.get("size", [1.0, 1.0, 1.0])
                    tz_top = tz + (tsize[2] / 2 if len(tsize) >= 3 else 0.5)
                    # subject bottom should be at or above target top
                    subj_bottom = z - (sz / 2 if len(size) >= 3 else 0.5)
                    if subj_bottom < tz_top - 0.01:
                        issues.append(
                            f"Object '{oid}' has 'on' relation with '{target_id}' "
                            f"but subject bottom z={subj_bottom:.2f} is below target top z={tz_top:.2f}"
                        )

        # 5. Check wall-attached objects are near walls
        for rel in relations:
            if rel.get("subject") == oid and rel.get("predicate") == "attached_to":
                target = rel.get("object", "").lower()
                wall_threshold = 0.6
                if "left_wall" in target and x > -rw / 2 + wall_threshold:
                    warnings.append(f"Object '{oid}' attached to left wall but x={x:.2f} (wall at x={-rw/2})")
                if "right_wall" in target and x < rw / 2 - wall_threshold:
                    warnings.append(f"Object '{oid}' attached to right wall but x={x:.2f} (wall at x={rw/2})")
                if "back_wall" in target and y < rd / 2 - wall_threshold:
                    warnings.append(f"Object '{oid}' attached to back wall but y={y:.2f} (wall at y={rd/2})")
                if "front_wall" in target and y > -rd / 2 + wall_threshold:
                    warnings.append(f"Object '{oid}' attached to front wall but y={y:.2f} (wall at y={-rd/2})")

    return {
        "warnings": warnings,
        "issues": issues,
        "is_geometrically_valid": len(issues) == 0,
        "geometry_warning_count": len(warnings),
        "geometry_issue_count": len(issues),
    }
