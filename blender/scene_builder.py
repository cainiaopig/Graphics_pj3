"""Main Blender scene construction module.

Builds a complete Blender scene from a scene graph dictionary.
Designed to run inside Blender only. All bpy imports are lazy / function-local.

Stage-set convention:
    The room is built like a film set — floor, back wall, left wall, right wall,
    and ceiling are created. The FRONT wall is OMITTED so the camera can see in.
    The camera is placed outside the room looking in through the open front.

    Walls are built OUTSIDE the usable room volume so they don't intersect with
    furniture. Wall coordinates use WALL_THICKNESS to offset from room boundaries.

Coordinate convention:
    Room center is at (0, 0, 0).
    Floor top surface is z = 0.
    Object positions are CENTERS (not bottom-center).
"""

from __future__ import annotations

from typing import Any

# Constants matching layout.py
WALL_THICKNESS = 0.08
FLOOR_THICKNESS = 0.08


def _ensure_blender():
    """Lazy-import bpy. Raises RuntimeError if not inside Blender."""
    try:
        import bpy
        return bpy
    except ImportError:
        raise RuntimeError(
            "This module must be run inside Blender. bpy is not available."
        )


# ---------------------------------------------------------------------------
# Scene management
# ---------------------------------------------------------------------------

def clear_scene() -> None:
    """Remove all objects, meshes, materials, and lights from the current scene.

    Uses proper orphan-data cleanup: first unlinks objects, then purges
    all orphan data blocks in one pass.
    """
    bpy = _ensure_blender()

    # 1. Delete all objects (this unlinks meshes/materials but keeps them as orphans)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    # 2. Purge all orphan data blocks (meshes, materials, lights, etc.)
    #    The recursive call ensures nested orphans are cleaned
    orphan_count = 1
    while orphan_count > 0:
        orphan_count = 0
        for data_attr in ("meshes", "materials", "lights", "worlds",
                           "cameras", "curves", "textures", "images"):
            collection = getattr(bpy.data, data_attr, None)
            if collection is None:
                continue
            for item in list(collection):
                if item.users == 0:
                    collection.remove(item)
                    orphan_count += 1


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_scene(scene_graph: dict[str, Any], debug_layout: bool = False) -> dict[str, Any]:
    """Build a complete Blender scene from a scene graph dictionary.

    Order of operations:
    1. Clear existing scene data
    2. Run layout pipeline (pure Python — computes all positions)
    3. Build room geometry (walls outside usable volume, floor below z=0)
    4. Create each object at its resolved position (position = CENTER)
    5. Add lights based on lighting config
    6. Add point lights at emissive object locations
    7. Set up camera
    8. Configure render settings

    Args:
        scene_graph: Scene graph dict with room, objects, relations, lighting, camera.
        debug_layout: If True, print debug info and create bounding boxes.

    Returns:
        Layout report dict.
    """
    bpy = _ensure_blender()

    room = scene_graph.get("room", {})
    objects = scene_graph.get("objects", [])
    relations = scene_graph.get("relations", [])
    lighting_cfg = scene_graph.get("lighting", {})
    camera_cfg = scene_graph.get("camera", {})
    scene_type = scene_graph.get("scene_type", "generic_room")

    # 1. Clear defaults
    clear_scene()

    # 2. Run layout pipeline (no bpy needed — pure Python)
    from blender.layout import run_layout_pipeline
    layout_result = run_layout_pipeline(
        objects, relations, room, scene_type, debug=debug_layout
    )
    positions = layout_result["positions"]
    layout_report = layout_result["report"]
    aabbs = layout_result.get("aabbs", {})

    # 3. Build room
    _build_room(room)

    # 4. Create objects at resolved positions
    for obj_data in objects:
        pos = positions.get(obj_data["id"], (0, 0, 0))
        _create_object(obj_data, pos)

    # 4b. Debug: create transparent bounding boxes
    if debug_layout:
        _create_debug_boxes(aabbs)

    # 5. Lighting
    _setup_lighting(lighting_cfg, room, objects, positions)

    # 6. Camera
    _setup_camera(camera_cfg, room)

    # 7. Render settings
    from blender.render_config import setup_render, set_world_color
    resolution = camera_cfg.get("resolution", [1280, 720])
    setup_render(resolution_x=resolution[0], resolution_y=resolution[1])

    # World background color from mood
    mood = lighting_cfg.get("mood", "neutral").lower()
    if "cyberpunk" in mood or "neon" in mood:
        set_world_color((0.02, 0.02, 0.06, 1.0))
    elif "warm" in mood or "cozy" in mood:
        set_world_color((0.06, 0.05, 0.04, 1.0))
    elif "bright" in mood:
        set_world_color((0.12, 0.12, 0.14, 1.0))
    else:
        set_world_color((0.05, 0.05, 0.08, 1.0))

    return layout_report


# ---------------------------------------------------------------------------
# Room construction (stage-set: open front, walls outside usable volume)
# ---------------------------------------------------------------------------

def _build_room(room: dict[str, Any]) -> None:
    """Build room geometry — floor, 3 walls, ceiling. Front wall omitted.

    Walls are built OUTSIDE the usable room volume:
      - Back wall center y = room.depth/2 + WALL_THICKNESS/2
      - Left wall center x = -room.width/2 - WALL_THICKNESS/2
      - Right wall center x = room.width/2 + WALL_THICKNESS/2
      - Floor center z = -FLOOR_THICKNESS/2 (below z=0)
      - Ceiling center z = room.height (top of room)

    This ensures the room envelope does not intersect with furniture.

    Args:
        room: Room config dict (width, depth, height, floor_material, wall_material).
    """
    from blender.primitives import create_box, create_plane
    from blender.materials import get_or_create_material

    rw = room.get("width", 6.0)
    rd = room.get("depth", 5.0)
    rh = room.get("height", 3.0)
    floor_mat_name = room.get("floor_material", "wood")
    wall_mat_name = room.get("wall_material", "paint")

    floor_mat = get_or_create_material("floor_material", floor_mat_name)
    wall_mat = get_or_create_material("wall_material", wall_mat_name)
    ceiling_mat = get_or_create_material("ceiling_material", "white")

    # Floor — box below z=0, top surface exactly at z=0
    create_box("Floor",
               center=(0, 0, -FLOOR_THICKNESS / 2),
               size=(rw, rd, FLOOR_THICKNESS),
               material_name=floor_mat.name if floor_mat else None)

    # Back wall (y = +depth/2 + WALL_THICKNESS/2) — outside room
    create_box("BackWall",
               center=(0, rd / 2 + WALL_THICKNESS / 2, rh / 2),
               size=(rw, WALL_THICKNESS, rh),
               material_name=wall_mat.name if wall_mat else None)

    # Left wall (x = -width/2 - WALL_THICKNESS/2) — outside room
    create_box("LeftWall",
               center=(-rw / 2 - WALL_THICKNESS / 2, 0, rh / 2),
               size=(WALL_THICKNESS, rd, rh),
               material_name=wall_mat.name if wall_mat else None)

    # Right wall (x = +width/2 + WALL_THICKNESS/2) — outside room
    create_box("RightWall",
               center=(rw / 2 + WALL_THICKNESS / 2, 0, rh / 2),
               size=(WALL_THICKNESS, rd, rh),
               material_name=wall_mat.name if wall_mat else None)

    # No front wall — stage-set convention (camera sees in from outside)

    # Ceiling at top of room
    create_box("Ceiling",
               center=(0, 0, rh + FLOOR_THICKNESS / 2),
               size=(rw, rd, FLOOR_THICKNESS),
               material_name=ceiling_mat.name if ceiling_mat else None)


# ---------------------------------------------------------------------------
# Debug bounding boxes
# ---------------------------------------------------------------------------

def _create_debug_boxes(aabbs: dict[str, Any]) -> None:
    """Create semi-transparent wireframe boxes to visualize AABB positions.

    Args:
        aabbs: Dict mapping object ID to AABB objects.
    """
    bpy = _ensure_blender()
    from blender.materials import get_or_create_material

    debug_mat = get_or_create_material("debug_aabb_mat", "cyan")
    if debug_mat:
        bpy.data.materials.get(debug_mat.name)

    for oid, aabb in aabbs.items():
        from blender.primitives import create_box
        box_name = f"DEBUG_{oid}"
        create_box(box_name, center=aabb.center, size=aabb.size)

        # Make it wireframe / transparent
        obj = bpy.data.objects.get(box_name)
        if obj:
            obj.display_type = "WIRE"
            obj.hide_render = True
            if debug_mat:
                if obj.data.materials:
                    obj.data.materials[0] = debug_mat
                else:
                    obj.data.materials.append(debug_mat)


# ---------------------------------------------------------------------------
# Object creation dispatcher
# ---------------------------------------------------------------------------

def _create_object(obj_data: dict[str, Any], pos: tuple[float, float, float]) -> None:
    """Dispatch to the appropriate object-specific creator.

    Args:
        obj_data: Object properties dict (type, id, size, material, color, rotation).
        pos: Resolved (x, y, z) CENTER position from layout pipeline.
    """
    obj_type = obj_data.get("type", "cube")
    obj_id = obj_data.get("id", "unnamed")
    size = list(obj_data.get("size", [1.0, 1.0, 1.0]))
    material = obj_data.get("material", "default")
    color = obj_data.get("color")
    rotation = obj_data.get("rotation", [0, 0, 0])

    # Normalize size to 3 components
    while len(size) < 3:
        size.append(1.0)

    x, y, z = pos
    sx, sy, sz = size[0], size[1], size[2]
    rx, ry, rz = rotation if rotation else (0, 0, 0)

    creators = {
        "bed":              _make_bed,
        "desk":             _make_desk,
        "chair":            _make_chair,
        "table":            _make_table,
        "sofa":             _make_sofa,
        "shelf":            _make_shelf,
        "bookshelf":        _make_bookshelf,
        "counter":          _make_counter,
        "monitor":          _make_monitor,
        "keyboard":         _make_keyboard,
        "lamp":             _make_lamp,
        "plant":            _make_plant,
        "carpet":           _make_carpet,
        "poster":           _make_poster,
        "blackboard":       _make_blackboard,
        "projector_screen": _make_projector_screen,
        "menu_board":       _make_menu_board,
        "glowing_tube":     _make_glowing_tube,
        "warning_sign":     _make_warning_sign,
        "neon_light":       _make_neon_light,
        "book":             _make_book,
        "cup":              _make_cup,
        "window":           _make_window,
        "door":             _make_door,
        "wall_decoration":  _make_wall_decoration,
    }

    creator = creators.get(obj_type)
    if creator:
        creator(obj_id, x, y, z, sx, sy, sz, material, color, rx, ry, rz)
    else:
        # Fallback: plain cube
        from blender.primitives import create_box
        from blender.materials import get_or_create_material
        mat = get_or_create_material(f"mat_{obj_id}", color or material)
        create_box(obj_id, center=(x, y, z), size=(sx, sy, sz),
                   rotation=(rx, ry, rz),
                   material_name=mat.name if mat else None)


# ---------------------------------------------------------------------------
# Lighting
# ---------------------------------------------------------------------------

def _setup_lighting(
    lighting_cfg: dict[str, Any],
    room: dict[str, float],
    objects: list[dict[str, Any]],
    positions: dict[str, tuple[float, float, float]],
) -> None:
    """Place lights based on lighting configuration and emissive objects.

    Args:
        lighting_cfg: Lighting config (mood, main_colors, brightness, use_emissive_lights).
        room: Room dimensions.
        objects: All scene objects (to find emissive ones).
        positions: Resolved object positions.
    """
    bpy = _ensure_blender()
    from blender.primitives import add_point_light, add_area_light
    from blender.materials import parse_color

    rw = room.get("width", 6.0)
    rd = room.get("depth", 5.0)
    rh = room.get("height", 3.0)
    mood = lighting_cfg.get("mood", "neutral").lower()
    brightness = lighting_cfg.get("brightness", "medium")
    main_colors = lighting_cfg.get("main_colors", ["white"])

    # Parse dominant color
    dom_color = (1.0, 1.0, 1.0)
    if main_colors:
        dom_color = parse_color(main_colors[0])[:3]

    # Brightness -> energy multiplier
    energy_map = {"low": 0.5, "medium": 1.0, "high": 2.0}
    mult = energy_map.get(brightness, 1.0)

    # --- Main overhead light ---
    if "cyberpunk" in mood or "neon" in mood:
        add_point_light("MainLight", (0, 0, rh - 0.4), dom_color, energy=60 * mult)
    elif "warm" in mood or "cozy" in mood:
        add_point_light("MainLight", (0, 0, rh - 0.4), (1.0, 0.85, 0.55), energy=120 * mult)
    elif "bright" in mood:
        add_point_light("MainLight", (0, 0, rh - 0.3), (1.0, 1.0, 0.95), energy=300 * mult)
    else:
        add_point_light("MainLight", (0, 0, rh - 0.4), dom_color, energy=150 * mult)

    # --- Fill light from front ---
    add_area_light("FillLight", (0, -rd / 2 - 1.0, rh * 0.5),
                   (0.9, 0.9, 1.0), energy=40 * mult, size=rw * 0.8)

    # --- Emissive object lights (point lights at neon/glowing objects) ---
    emissive_types = {"neon_light", "glowing_tube", "monitor", "lamp"}
    if lighting_cfg.get("use_emissive_lights", False):
        for obj in objects:
            if obj.get("type") in emissive_types:
                oid = obj["id"]
                if oid in positions:
                    px, py, pz = positions[oid]
                    obj_color = parse_color(obj.get("color"))[:3]
                    add_point_light(
                        f"EmissiveLight_{oid}",
                        (px, py, pz),
                        obj_color,
                        energy=20 * mult,
                    )


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

def _setup_camera(camera_cfg: dict[str, Any], room: dict[str, float]) -> None:
    """Place and configure the render camera.

    The camera is placed outside the room looking in through the open front.

    Args:
        camera_cfg: Camera config (position, target, focal_length).
        room: Room dimensions.
    """
    bpy = _ensure_blender()

    # Default: camera outside, looking at room center from front
    default_pos = [room.get("width", 6.0) * 0.7,
                   -room.get("depth", 5.0) * 1.1,
                   room.get("height", 3.0) * 1.1]
    default_target = [0.0, 0.0, room.get("height", 3.0) * 0.4]

    pos = camera_cfg.get("position", default_pos)
    target = camera_cfg.get("target", default_target)
    focal_length = camera_cfg.get("focal_length", 28.0)

    bpy.ops.object.camera_add(location=pos)
    cam = bpy.context.active_object
    cam.name = "MainCamera"
    cam.data.lens = focal_length

    # Aim camera at target using Blender's built-in constraint
    # (mathutils is always available inside Blender)
    import mathutils
    dir_vec = mathutils.Vector(target) - mathutils.Vector(pos)
    cam.rotation_euler = dir_vec.to_track_quat("-Z", "Y").to_euler()

    bpy.context.scene.camera = cam


def save_blend_file(path: str) -> None:
    """Save the current scene as a .blend file.

    Args:
        path: Output file path (.blend extension recommended).
    """
    bpy = _ensure_blender()
    bpy.ops.wm.save_as_mainfile(filepath=str(path))


def render_image(output_path: str) -> None:
    """Render the current scene to an image and save to disk.

    Args:
        output_path: Output image path (.png extension recommended).
    """
    bpy = _ensure_blender()
    bpy.context.scene.render.filepath = str(output_path)
    bpy.context.scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)


# ===========================================================================
#  Object-specific creation functions
#  Each receives: id, x, y, z, sx, sy, sz, material, color, rx, ry, rz
#  (x, y, z) is the CENTER of the object bounding box
# ===========================================================================

def _m(name: str, color_or_mat: str | None) -> str | None:
    """Helper: get or create a material and return its name (or None)."""
    from blender.materials import get_or_create_material
    mat = get_or_create_material(name, color_or_mat)
    return mat.name if mat else None


def _make_bed(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_box
    mn = _m(f"mat_{oid}", color or mat)
    # z = center of bed. Frame goes from floor to sz
    # Bed frame — center at z (the whole bounding box center)
    create_box(f"{oid}_frame", (x, y, z), (sx, sy, sz * 0.55),
               (rx, ry, rz), mn)
    # Mattress — slightly smaller, top portion
    mm = _m(f"mat_{oid}_mattress", "dark gray")
    mattress_h = sz * 0.22
    create_box(f"{oid}_mattress", (x, y, z + sz * 0.22),
               (sx * 0.92, sy * 0.92, mattress_h), (rx, ry, rz), mm)
    # Pillow — top-back of bed
    pm = _m(f"mat_{oid}_pillow", "white")
    pillow_h = sz * 0.06
    create_box(f"{oid}_pillow", (x - sx * 0.25, y, z + sz * 0.35),
               (sx * 0.28, sy * 0.45, pillow_h), (rx, ry, rz), pm)


def _make_desk(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_box
    mn = _m(f"mat_{oid}", color or mat)
    leg_h = sz * 0.88
    leg_r = max(0.04, min(sx, sy) * 0.06)
    # Tabletop — top of desk
    tabletop_h = sz * 0.06
    create_box(f"{oid}_top", (x, y, z + sz * 0.44),
               (sx, sy, tabletop_h), (rx, ry, rz), mn)
    # 4 legs — from floor up
    for lx, ly in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
        create_box(f"{oid}_leg",
                   (x + lx * sx * 0.42, y + ly * sy * 0.42, z + leg_h / 2 - sz / 2),
                   (leg_r, leg_r, leg_h), (rx, ry, rz), mn)


def _make_chair(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_box
    mn = _m(f"mat_{oid}", color or mat)
    leg_r = max(0.03, min(sx, sy) * 0.08)
    # Seat
    seat_h = sz * 0.08
    create_box(f"{oid}_seat", (x, y, z + sz * 0.05),
               (sx, sy, seat_h), (rx, ry, rz), mn)
    # Back rest — behind and above seat
    create_box(f"{oid}_back", (x, y + sy * 0.42, z + sz * 0.22),
               (sx, sy * 0.12, sz * 0.4), (rx, ry, rz), mn)
    # 4 legs
    for lx, ly in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
        create_box(f"{oid}_leg",
                   (x + lx * sx * 0.38, y + ly * sy * 0.38, z + sz * 0.25 - sz / 2),
                   (leg_r, leg_r, sz * 0.5), (rx, ry, rz), mn)


def _make_table(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_cylinder_box
    mn = _m(f"mat_{oid}", color or mat)
    avg_w = (sx + sy) / 2
    # Round tabletop — top portion
    top_h = sz * 0.07
    create_cylinder_box(f"{oid}_top", (x, y, z + sz * 0.43),
                        (sx, sy, top_h), (rx, ry, rz), material_name=mn)
    # Central column
    leg_h = sz * 0.86
    create_cylinder_box(f"{oid}_leg", (x, y, z + sz * 0.43 - top_h / 2 - leg_h / 2),
                        (avg_w * 0.1, avg_w * 0.1, leg_h),
                        (rx, ry, rz), material_name=mn)
    # Base disc
    base_h = sz * 0.06
    create_cylinder_box(f"{oid}_base", (x, y, z + base_h / 2 - sz / 2),
                        (avg_w * 0.35, avg_w * 0.35, base_h),
                        (rx, ry, rz), material_name=mn)


def _make_sofa(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_box
    mn = _m(f"mat_{oid}", color or mat)
    # Seat cushion
    seat_h = sz * 0.4
    create_box(f"{oid}_seat", (x, y, z + sz * 0.1),
               (sx, sy, seat_h), (rx, ry, rz), mn)
    # Back rest
    create_box(f"{oid}_back", (x, y + sy * 0.4, z + sz * 0.58 - sz / 2),
               (sx, sy * 0.18, sz * 0.5), (rx, ry, rz), mn)
    # Armrests
    arm_h = sz * 0.2
    for ax in [-1, 1]:
        create_box(f"{oid}_arm_{ax}",
                   (x + ax * sx * 0.44, y, z + sz * 0.42 - sz / 2),
                   (sx * 0.08, sy * 0.75, arm_h), (rx, ry, rz), mn)


def _make_shelf(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_box
    mn = _m(f"mat_{oid}", color or mat)
    create_box(oid, (x, y, z), (sx, sy, sz), (rx, ry, rz), mn)


def _make_bookshelf(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_box
    mn = _m(f"mat_{oid}", color or mat)
    # Outer frame
    create_box(f"{oid}_frame", (x, y, z), (sx, sy, sz), (rx, ry, rz), mn)
    # Shelf dividers
    for i in range(1, 4):
        shelf_z = z + sz * (i / 4 - 0.5)
        create_box(f"{oid}_shelf_{i}", (x, y, shelf_z),
                   (sx * 0.85, sy * 0.85, sz * 0.025), (rx, ry, rz), mn)


def _make_counter(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    _make_desk(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz)


def _make_monitor(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_box
    from blender.materials import create_emissive_material, parse_color
    mn = _m(f"mat_{oid}_frame", color or mat)
    # Stand — base near bottom
    create_box(f"{oid}_stand", (x, y, z + sz * 0.08 - sz / 2),
               (sx * 0.35, sy * 0.6, sz * 0.16), (rx, ry, rz), mn)
    # Frame
    create_box(f"{oid}_frame", (x, y, z + sz * 0.65 - sz / 2),
               (sx, sy * 0.5, sz * 0.55), (rx, ry, rz), mn)
    # Emissive screen
    rgba = parse_color(color or "cyan")
    sm = create_emissive_material(f"mat_{oid}_screen", rgba, 3.0)
    screen_h = sz * 0.48
    create_box(f"{oid}_screen", (x, y - sy * 0.08, z + sz * 0.65 - sz / 2),
               (sx * 0.85, sy * 0.08, screen_h), (rx, ry, rz), sm.name)


def _make_keyboard(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_box
    mn = _m(f"mat_{oid}", color or mat)
    create_box(oid, (x, y, z), (sx, sy, sz), (rx, ry, rz), mn)


def _make_lamp(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_cylinder_box
    mn = _m(f"mat_{oid}", color or mat)
    avg_w = (sx + sy) / 2
    # Base
    base_h = sz * 0.08
    create_cylinder_box(f"{oid}_base", (x, y, z + base_h / 2 - sz / 2),
                        (avg_w * 0.6, avg_w * 0.6, base_h),
                        (rx, ry, rz), material_name=mn)
    # Pole
    pole_h = sz * 0.55
    create_cylinder_box(f"{oid}_pole", (x, y, z + base_h + pole_h / 2 - sz / 2),
                        (avg_w * 0.08, avg_w * 0.08, pole_h),
                        (rx, ry, rz), material_name=mn)
    # Lampshade
    shade_h = sz * 0.28
    from blender.primitives import create_cone
    create_cone(f"{oid}_shade",
                (x, y, z + base_h + pole_h + shade_h / 2 - sz / 2),
                (avg_w * 0.65, avg_w * 0.65, shade_h), material_name=mn)
    # Point light
    from blender.primitives import add_point_light
    add_point_light(f"{oid}_light", (x, y, z + sz * 0.7 - sz / 2),
                    (1.0, 0.9, 0.7), energy=40)


def _make_plant(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_cylinder_box, create_uv_sphere
    avg_w = (sx + sy) / 2
    pm = _m(f"mat_{oid}_pot", "brown")
    lm = _m(f"mat_{oid}_leaves", "green")
    # Pot — bottom portion
    pot_h = sz * 0.36
    create_cylinder_box(f"{oid}_pot", (x, y, z + pot_h / 2 - sz / 2),
                        (avg_w * 0.55, avg_w * 0.55, pot_h),
                        (rx, ry, rz), material_name=pm)
    # Leaves sphere — top portion
    leaves_h = sz * 0.5
    create_uv_sphere(f"{oid}_leaves",
                     (x, y, z + pot_h + leaves_h / 2 - sz / 2),
                     (avg_w * 0.5, avg_w * 0.5, leaves_h),
                     material_name=lm)


def _make_carpet(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_box
    mn = _m(f"mat_{oid}", color or mat)
    # Carpet is a very thin box at the floor level
    # z = center (sz/2 + 0.005 above floor)
    create_box(oid, (x, y, z), (sx, sy, sz), (rx, ry, rz), mn)


def _make_poster(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_box
    mn = _m(f"mat_{oid}", color or mat)
    create_box(oid, (x, y, z), (sx, sy, sz), (rx, ry, rz), mn)


def _make_blackboard(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_box
    mn = _m(f"mat_{oid}", color or "dark green")
    create_box(oid, (x, y, z), (sx, sy, sz), (rx, ry, rz), mn)


def _make_projector_screen(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_box
    mn = _m(f"mat_{oid}", color or "white")
    create_box(oid, (x, y, z), (sx, sy, sz), (rx, ry, rz), mn)


def _make_menu_board(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_box
    mn = _m(f"mat_{oid}", color or "black")
    create_box(oid, (x, y, z), (sx, sy, sz), (rx, ry, rz), mn)


def _make_glowing_tube(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_cylinder_box
    from blender.materials import create_emissive_material, parse_color
    rgba = parse_color(color or "cyan")
    em = create_emissive_material(f"mat_{oid}", rgba, 6.0)
    create_cylinder_box(oid, (x, y, z), (sx, sy, sz),
                        (rx, ry, rz), material_name=em.name)


def _make_warning_sign(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_box
    mn = _m(f"mat_{oid}", color or "yellow")
    create_box(oid, (x, y, z), (sx, sy, sz), (rx, ry, rz), mn)


def _make_neon_light(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_box
    from blender.materials import create_emissive_material, parse_color
    rgba = parse_color(color or "magenta")
    em = create_emissive_material(f"mat_{oid}", rgba, 10.0)
    create_box(oid, (x, y, z), (sx, sy, sz), (rx, ry, rz), em.name)


def _make_book(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_box
    mn = _m(f"mat_{oid}", color or "red")
    create_box(oid, (x, y, z), (sx, sy, sz), (rx, ry, rz), mn)


def _make_cup(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_cylinder_box
    mn = _m(f"mat_{oid}", color or "white")
    create_cylinder_box(oid, (x, y, z), (sx, sy, sz),
                        (rx, ry, rz), material_name=mn)


def _make_window(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_box
    fm = _m(f"mat_{oid}_frame", color or "white")
    # Outer frame
    create_box(f"{oid}_frame", (x, y, z), (sx + 0.08, sy * 1.5, sz + 0.08),
               (rx, ry, rz), fm)
    # Glass pane — recessed into wall
    gm = _m(f"mat_{oid}_glass", "cyan")
    create_box(f"{oid}_glass", (x, y - sy * 0.2, z),
               (sx * 0.85, sy * 0.04, sz * 0.85), (rx, ry, rz), gm)


def _make_door(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_box
    mn = _m(f"mat_{oid}", color or mat)
    create_box(oid, (x, y, z), (sx, sy, sz), (rx, ry, rz), mn)


def _make_wall_decoration(oid, x, y, z, sx, sy, sz, mat, color, rx, ry, rz):
    from blender.primitives import create_box
    mn = _m(f"mat_{oid}", color or mat)
    create_box(oid, (x, y, z), (sx, sy, sz), (rx, ry, rz), mn)
