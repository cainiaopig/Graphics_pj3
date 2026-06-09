"""Low-level Blender primitive creation functions.

These functions are designed to be called from within Blender's Python environment.
They import bpy lazily via _ensure_blender() — safe to import this module from
normal Python as long as you don't call the functions.

All functions follow the pattern:
    create_<shape>(name, location, scale, material_name=None) -> bpy.types.Object
"""

from __future__ import annotations

from typing import Optional


def _ensure_blender():
    """Lazy-import bpy to avoid errors outside Blender.

    Returns:
        The bpy module.

    Raises:
        RuntimeError: If bpy is not available (not running inside Blender).
    """
    try:
        import bpy
        return bpy
    except ImportError:
        raise RuntimeError(
            "This module must be run inside Blender. bpy is not available. "
            "Are you running this from a normal Python interpreter?"
        )


def create_cube(
    name: str,
    location: tuple[float, float, float] = (0, 0, 0),
    scale: tuple[float, float, float] = (1, 1, 1),
    rotation: tuple[float, float, float] = (0, 0, 0),
    material_name: Optional[str] = None,
):
    """Create a cube primitive.

    Args:
        name: Object name in the Blender scene.
        location: (x, y, z) world position.
        scale: (x, y, z) scale factors (applied after creation).
        rotation: (rx, ry, rz) Euler rotation in radians.
        material_name: Optional material to assign.

    Returns:
        The created Blender object.
    """
    bpy = _ensure_blender()
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    obj.rotation_euler = rotation
    if material_name:
        _assign_material(obj, material_name)
    return obj


def create_plane(
    name: str,
    location: tuple[float, float, float] = (0, 0, 0),
    scale: tuple[float, float, float] = (1, 1, 1),
    rotation: tuple[float, float, float] = (0, 0, 0),
    material_name: Optional[str] = None,
):
    """Create a plane primitive (default: horizontal, face-up).

    Args:
        name: Object name.
        location: (x, y, z) world position.
        scale: (x, y, z) scale factors.
        rotation: (rx, ry, rz) Euler rotation in radians.
        material_name: Optional material to assign.

    Returns:
        The created Blender object.
    """
    bpy = _ensure_blender()
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    obj.rotation_euler = rotation
    if material_name:
        _assign_material(obj, material_name)
    return obj


def create_cylinder(
    name: str,
    location: tuple[float, float, float] = (0, 0, 0),
    scale: tuple[float, float, float] = (1, 1, 1),
    rotation: tuple[float, float, float] = (0, 0, 0),
    vertices: int = 32,
    material_name: Optional[str] = None,
):
    """Create a cylinder primitive (default: vertical, radius=0.5, height=1.0).

    Args:
        name: Object name.
        location: (x, y, z) world position (center).
        scale: (x, y, z) scale factors. scale[0] and scale[1] affect radius,
               scale[2] affects height.
        rotation: (rx, ry, rz) Euler rotation in radians.
        vertices: Number of vertices for the cylinder's circumference.
        material_name: Optional material to assign.

    Returns:
        The created Blender object.
    """
    bpy = _ensure_blender()
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=0.5,
        depth=1.0,
        location=location,
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    obj.rotation_euler = rotation
    if material_name:
        _assign_material(obj, material_name)
    return obj


def create_uv_sphere(
    name: str,
    location: tuple[float, float, float] = (0, 0, 0),
    scale: tuple[float, float, float] = (1, 1, 1),
    segments: int = 32,
    rings: int = 16,
    material_name: Optional[str] = None,
):
    """Create a UV sphere primitive.

    Args:
        name: Object name.
        location: (x, y, z) world position.
        scale: (x, y, z) scale factors.
        segments: Horizontal subdivisions.
        rings: Vertical subdivisions.
        material_name: Optional material to assign.

    Returns:
        The created Blender object.
    """
    bpy = _ensure_blender()
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments,
        ring_count=rings,
        radius=0.5,
        location=location,
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    if material_name:
        _assign_material(obj, material_name)
    return obj


def create_cone(
    name: str,
    location: tuple[float, float, float] = (0, 0, 0),
    scale: tuple[float, float, float] = (1, 1, 1),
    vertices: int = 32,
    material_name: Optional[str] = None,
):
    """Create a cone primitive.

    Args:
        name: Object name.
        location: (x, y, z) world position.
        scale: (x, y, z) scale factors.
        vertices: Number of vertices around the base.
        material_name: Optional material to assign.

    Returns:
        The created Blender object.
    """
    bpy = _ensure_blender()
    bpy.ops.mesh.primitive_cone_add(
        vertices=vertices,
        radius1=0.5,
        radius2=0.0,
        depth=1.0,
        location=location,
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    if material_name:
        _assign_material(obj, material_name)
    return obj


def add_point_light(
    name: str,
    location: tuple[float, float, float] = (0, 0, 2),
    color: tuple[float, float, float] = (1.0, 1.0, 1.0),
    energy: float = 100.0,
):
    """Add a point light to the scene.

    Args:
        name: Light object name.
        location: (x, y, z) world position.
        color: RGB color tuple (0-1 range).
        energy: Light intensity.

    Returns:
        The created light object.
    """
    bpy = _ensure_blender()
    bpy.ops.object.light_add(type="POINT", location=location)
    light = bpy.context.active_object
    light.name = name
    light.data.color = color
    light.data.energy = energy
    return light


def add_area_light(
    name: str,
    location: tuple[float, float, float] = (0, 0, 2),
    color: tuple[float, float, float] = (1.0, 1.0, 1.0),
    energy: float = 50.0,
    size: float = 2.0,
):
    """Add an area light to the scene.

    Args:
        name: Light object name.
        location: (x, y, z) world position.
        color: RGB color tuple (0-1 range).
        energy: Light intensity.
        size: Size of the area light.

    Returns:
        The created light object.
    """
    bpy = _ensure_blender()
    bpy.ops.object.light_add(type="AREA", location=location)
    light = bpy.context.active_object
    light.name = name
    light.data.color = color
    light.data.energy = energy
    light.data.size = size
    return light


def create_box(
    name: str,
    center: tuple[float, float, float] = (0, 0, 0),
    size: tuple[float, float, float] = (1, 1, 1),
    rotation: tuple[float, float, float] = (0, 0, 0),
    material_name: Optional[str] = None,
):
    """Create a box with exact world-space dimensions.

    Uses obj.dimensions + transform_apply(scale=True) to ensure
    the object's actual size matches the given size exactly,
    regardless of how it was created.

    Args:
        name: Object name in the Blender scene.
        center: (x, y, z) world position of the box center.
        size: (sx, sy, sz) exact world-space dimensions.
        rotation: (rx, ry, rz) Euler rotation in radians.
        material_name: Optional material to assign.

    Returns:
        The created Blender object.
    """
    bpy = _ensure_blender()
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=center)
    obj = bpy.context.active_object
    obj.name = name
    obj.dimensions = size
    obj.rotation_euler = rotation
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material_name:
        _assign_material(obj, material_name)
    return obj


def create_cylinder_box(
    name: str,
    center: tuple[float, float, float] = (0, 0, 0),
    size: tuple[float, float, float] = (1, 1, 1),
    rotation: tuple[float, float, float] = (0, 0, 0),
    vertices: int = 32,
    material_name: Optional[str] = None,
):
    """Create a cylinder with exact world-space dimensions.

    Uses obj.dimensions + transform_apply(scale=True) to ensure
    the cylinder's size matches the given size exactly.

    Args:
        name: Object name.
        center: (x, y, z) world position of center.
        size: (sx, sy, sz) exact world-space dimensions.
              sx and sy control the radius (cylinder is symmetric in x/y).
              sz controls the height.
        rotation: (rx, ry, rz) Euler rotation in radians.
        vertices: Number of vertices around the circumference.
        material_name: Optional material to assign.

    Returns:
        The created Blender object.
    """
    bpy = _ensure_blender()
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=0.5,
        depth=1.0,
        location=center,
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.dimensions = size
    obj.rotation_euler = rotation
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material_name:
        _assign_material(obj, material_name)
    return obj


def _assign_material(obj, material_name: str) -> None:
    """Assign a material to an object if it exists in Blender data.

    Args:
        obj: Blender object.
        material_name: Name of the material to assign.
    """
    bpy = _ensure_blender()
    mat = bpy.data.materials.get(material_name)
    if mat is not None:
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)
