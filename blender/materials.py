"""Blender material creation utilities.

Creates and manages materials for procedural scene construction.
Designed to run inside Blender only.
"""

from __future__ import annotations

from typing import Optional, Tuple


def _ensure_blender():
    """Lazy-import bpy."""
    try:
        import bpy
        return bpy
    except ImportError:
        raise RuntimeError(
            "This module must be run inside Blender. bpy is not available."
        )


# Color name to RGBA mapping (approximate)
COLOR_MAP: dict[str, Tuple[float, float, float, float]] = {
    "white": (1.0, 1.0, 1.0, 1.0),
    "black": (0.02, 0.02, 0.02, 1.0),
    "dark gray": (0.15, 0.15, 0.15, 1.0),
    "gray": (0.5, 0.5, 0.5, 1.0),
    "light gray": (0.75, 0.75, 0.75, 1.0),
    "silver": (0.75, 0.75, 0.78, 1.0),
    "red": (0.8, 0.1, 0.1, 1.0),
    "dark red": (0.4, 0.05, 0.05, 1.0),
    "deep red": (0.5, 0.05, 0.05, 1.0),
    "warm red": (0.7, 0.15, 0.1, 1.0),
    "blue": (0.1, 0.2, 0.8, 1.0),
    "dark blue": (0.05, 0.08, 0.3, 1.0),
    "cyan": (0.0, 0.8, 0.8, 1.0),
    "green": (0.1, 0.7, 0.2, 1.0),
    "dark green": (0.05, 0.3, 0.1, 1.0),
    "yellow": (0.9, 0.8, 0.1, 1.0),
    "magenta": (0.8, 0.1, 0.6, 1.0),
    "purple": (0.5, 0.1, 0.5, 1.0),
    "dark purple": (0.2, 0.05, 0.2, 1.0),
    "brown": (0.35, 0.2, 0.1, 1.0),
    "dark brown": (0.15, 0.08, 0.04, 1.0),
    "warm brown": (0.4, 0.25, 0.15, 1.0),
    "orange": (0.9, 0.5, 0.1, 1.0),
    "pink": (0.9, 0.5, 0.6, 1.0),
    "brass": (0.7, 0.55, 0.25, 1.0),
    "copper": (0.8, 0.4, 0.2, 1.0),
    "gold": (0.85, 0.7, 0.15, 1.0),
    "beige": (0.85, 0.8, 0.7, 1.0),
}


def parse_color(color_name: Optional[str]) -> Tuple[float, float, float, float]:
    """Parse a color name into RGBA values.

    Args:
        color_name: Color name string (e.g., "dark wood", "blue").

    Returns:
        RGBA tuple with values in [0, 1].
    """
    if color_name is None:
        return (0.5, 0.5, 0.5, 1.0)

    color_lower = color_name.lower().strip()

    # Direct match
    if color_lower in COLOR_MAP:
        return COLOR_MAP[color_lower]

    # Check if any known color name is a substring
    for name, rgba in COLOR_MAP.items():
        if name in color_lower:
            return rgba

    # Default fallback
    return (0.5, 0.5, 0.5, 1.0)


def create_material(
    name: str,
    color: Tuple[float, float, float, float] = (0.5, 0.5, 0.5, 1.0),
) -> object:
    """Create a simple diffuse/Principled BSDF material.

    Args:
        name: Material name.
        color: RGBA color tuple.

    Returns:
        The Blender material.
    """
    bpy = _ensure_blender()
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    principled = nodes.get("Principled BSDF")
    if principled:
        principled.inputs["Base Color"].default_value = color
        principled.inputs["Roughness"].default_value = 0.7
    return mat


def create_emissive_material(
    name: str,
    color: Tuple[float, float, float, float] = (0.0, 0.5, 1.0, 1.0),
    strength: float = 5.0,
) -> object:
    """Create an emissive material for neon lights and glowing objects.

    Args:
        name: Material name.
        color: RGBA color tuple (alpha used for emission color).
        strength: Emission strength.

    Returns:
        The Blender material.
    """
    bpy = _ensure_blender()
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    principled = nodes.get("Principled BSDF")
    if principled:
        principled.inputs["Base Color"].default_value = color
        principled.inputs["Emission Color"].default_value = color[:3] + (1.0,)
        principled.inputs["Emission Strength"].default_value = strength
    return mat


def create_glass_material(name: str) -> object:
    """Create a simple glass-like material.

    Args:
        name: Material name.

    Returns:
        The Blender material.
    """
    bpy = _ensure_blender()
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    principled = nodes.get("Principled BSDF")
    if principled:
        principled.inputs["Base Color"].default_value = (0.9, 0.95, 1.0, 1.0)
        principled.inputs["Roughness"].default_value = 0.05
        principled.inputs["Transmission Weight"].default_value = 0.9
    return mat


def get_or_create_material(
    name: str,
    color: Optional[str] = None,
    emissive: bool = False,
    glass: bool = False,
) -> object:
    """Get an existing material by name or create a new one.

    Args:
        name: Material name.
        color: Optional color name or description.
        emissive: Whether to create an emissive material.
        glass: Whether to create a glass material.

    Returns:
        The Blender material (existing or new).
    """
    bpy = _ensure_blender()
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat

    rgba = parse_color(color)

    if emissive:
        return create_emissive_material(name, rgba)
    elif glass:
        return create_glass_material(name)
    else:
        return create_material(name, rgba)
