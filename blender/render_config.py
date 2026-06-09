"""Blender render configuration utilities.

Sets up render engine, resolution, samples, and output settings.
Designed to run inside Blender only. All bpy access is lazy via _ensure_blender().
"""

from __future__ import annotations


def _ensure_blender():
    """Lazy-import bpy. Raises RuntimeError if not inside Blender."""
    try:
        import bpy
        return bpy
    except ImportError:
        raise RuntimeError(
            "This module must be run inside Blender. bpy is not available."
        )


def setup_render(
    engine: str = "BLENDER_EEVEE",
    resolution_x: int = 1280,
    resolution_y: int = 720,
    samples: int = 64,
    output_path: str = "",
    file_format: str = "PNG",
) -> None:
    """Configure Blender render settings.

    Args:
        engine: Render engine — 'BLENDER_EEVEE' (fast, default) or 'CYCLES'.
        resolution_x: Image width in pixels.
        resolution_y: Image height in pixels.
        samples: Render samples (for EEVEE this is viewport samples; for Cycles it's render samples).
        output_path: Path for the rendered image.
        file_format: Output file format (PNG, JPEG, etc.).
    """
    bpy = _ensure_blender()

    scene = bpy.context.scene
    scene.render.engine = engine
    scene.render.resolution_x = resolution_x
    scene.render.resolution_y = resolution_y
    scene.render.resolution_percentage = 100

    if engine == "CYCLES":
        scene.cycles.samples = samples
    else:
        # EEVEE
        scene.eevee.taa_render_samples = samples

    if output_path:
        scene.render.filepath = output_path
        scene.render.image_settings.file_format = file_format


def set_world_color(
    color: tuple[float, float, float, float] = (0.05, 0.05, 0.08, 1.0),
) -> None:
    """Set the world background color via shader nodes.

    Args:
        color: RGBA color tuple, values in [0, 1].
    """
    bpy = _ensure_blender()

    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world

    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = color
        bg.inputs["Strength"].default_value = 1.0


def set_render_output(
    output_path: str,
    file_format: str = "PNG",
    color_mode: str = "RGBA",
    color_depth: str = "8",
) -> None:
    """Set only the render output path and format (without changing engine/samples).

    Args:
        output_path: File path for the rendered output.
        file_format: File format (PNG, JPEG, OPEN_EXR, etc.).
        color_mode: BW, RGB, or RGBA.
        color_depth: 8 or 16.
    """
    bpy = _ensure_blender()
    scene = bpy.context.scene
    scene.render.filepath = output_path
    scene.render.image_settings.file_format = file_format
    scene.render.image_settings.color_mode = color_mode
    scene.render.image_settings.color_depth = color_depth
