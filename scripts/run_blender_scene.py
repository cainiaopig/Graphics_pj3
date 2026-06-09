#!/usr/bin/env python3
"""Blender runtime script — load a scene graph JSON, build a 3D scene, and render.

This script is meant to be executed BY Blender, not by a normal Python interpreter.

Usage:
    blender --background --python scripts/run_blender_scene.py -- \\
        --scene-json path/to/scene.json \\
        --output path/to/render.png \\
        [--save-blend path/to/scene.blend] \\
        [--engine BLENDER_EEVEE|CYCLES] \\
        [--samples 64] \\
        [--resolution 1280 720]

Examples:
    # Fast EEVEE render:
    blender --background --python scripts/run_blender_scene.py -- \\
        --scene-json outputs/scene_json/latest_repaired_scene_graph.json \\
        --output outputs/renders/latest_render.png

    # High-quality Cycles render:
    blender --background --python scripts/run_blender_scene.py -- \\
        --scene-json outputs/scene_json/latest_scene_graph.json \\
        --output outputs/renders/high_quality.png \\
        --engine CYCLES --samples 256

All arguments after the '--' separator are parsed by this script.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments passed after the '--' separator.

    Blender passes everything after '--' as extra args in sys.argv.
    We locate the '--' index and parse everything after it.
    """
    argv = sys.argv
    try:
        double_dash = argv.index("--")
        script_args = argv[double_dash + 1:]
    except ValueError:
        script_args = []

    parser = argparse.ArgumentParser(
        description="Blender scene renderer for BlenderSceneAgent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  blender --background --python scripts/run_blender_scene.py -- \\
      --scene-json outputs/scene_json/latest_scene_graph.json \\
      --output outputs/renders/render.png
        """,
    )

    parser.add_argument(
        "--scene-json",
        type=str,
        required=True,
        help="Path to the scene graph JSON file.",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Path for the rendered PNG output file.",
    )
    parser.add_argument(
        "--save-blend",
        type=str,
        default=None,
        help="Optional path to save the .blend file.",
    )
    parser.add_argument(
        "--engine",
        type=str,
        default="BLENDER_EEVEE",
        choices=["BLENDER_EEVEE", "CYCLES"],
        help="Render engine (default: BLENDER_EEVEE for speed).",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=64,
        help="Render samples (default: 64 for EEVEE, use 128+ for CYCLES).",
    )
    parser.add_argument(
        "--resolution",
        type=int,
        nargs=2,
        default=None,
        metavar=("WIDTH", "HEIGHT"),
        help="Override render resolution (default: from scene graph camera config).",
    )
    parser.add_argument(
        "--debug-layout",
        action="store_true",
        default=False,
        help="Print layout debug info and save layout report.",
    )

    return parser.parse_args(script_args)


def main() -> None:
    """Entry point: load scene JSON, build Blender scene, render, and optionally save."""
    args = parse_args()

    # ------------------------------------------------------------------
    # Ensure project root is importable inside Blender's Python
    # ------------------------------------------------------------------
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Now safe to import bpy (we ARE inside Blender)
    import bpy  # noqa: E402

    from blender.scene_builder import (  # noqa: E402
        build_scene,
        clear_scene,
        render_image,
        save_blend_file,
    )
    from blender.render_config import setup_render  # noqa: E402

    # ------------------------------------------------------------------
    # Validate inputs
    # ------------------------------------------------------------------
    scene_json_path = Path(args.scene_json)
    if not scene_json_path.exists():
        print(f"[ERROR] Scene JSON not found: {args.scene_json}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Load scene graph
    # ------------------------------------------------------------------
    print(f"[BlenderSceneAgent] Loading: {args.scene_json}")
    with open(args.scene_json, "r", encoding="utf-8") as f:
        scene_graph = json.load(f)

    scene_id = scene_graph.get("scene_id", "unknown")
    obj_count = len(scene_graph.get("objects", []))
    rel_count = len(scene_graph.get("relations", []))
    scene_type = scene_graph.get("scene_type", "unknown")
    print(f"[BlenderSceneAgent] Scene: {scene_id}")
    print(f"[BlenderSceneAgent] Type: {scene_type} | Objects: {obj_count} | Relations: {rel_count}")

    # ------------------------------------------------------------------
    # Determine resolution
    # ------------------------------------------------------------------
    camera_cfg = scene_graph.get("camera", {})
    if args.resolution:
        res_x, res_y = args.resolution
        print(f"[BlenderSceneAgent] Resolution override: {res_x}x{res_y}")
    else:
        res = camera_cfg.get("resolution", [1280, 720])
        res_x, res_y = res[0], res[1]

    # ------------------------------------------------------------------
    # Build scene
    # ------------------------------------------------------------------
    print("[BlenderSceneAgent] Building scene geometry...")
    debug_layout = getattr(args, "debug_layout", False)
    try:
        # clear_scene() is called inside build_scene()
        layout_report = build_scene(scene_graph, debug_layout=debug_layout)
    except Exception:
        print("[ERROR] Scene build failed:", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

    print("[BlenderSceneAgent] Scene built successfully.")

    # Save layout report if debug mode
    if debug_layout and layout_report:
        report_path = output_path.parent / "latest_layout_report.json"
        with open(str(report_path), "w", encoding="utf-8") as f:
            json.dump(layout_report, f, indent=2, default=str)
        print(f"[BlenderSceneAgent] Layout report saved: {report_path}")

    # ------------------------------------------------------------------
    # Configure render
    # ------------------------------------------------------------------
    setup_render(
        engine=args.engine,
        resolution_x=res_x,
        resolution_y=res_y,
        samples=args.samples,
        output_path=str(output_path),
    )
    print(f"[BlenderSceneAgent] Engine: {args.engine} | Samples: {args.samples} | Resolution: {res_x}x{res_y}")

    # ------------------------------------------------------------------
    # Save .blend (optional)
    # ------------------------------------------------------------------
    if args.save_blend:
        blend_path = Path(args.save_blend)
        blend_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"[BlenderSceneAgent] Saving .blend: {args.save_blend}")
        save_blend_file(str(blend_path))

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    print(f"[BlenderSceneAgent] Rendering to: {args.output}")
    try:
        render_image(str(output_path))
        print(f"[BlenderSceneAgent] Render complete: {args.output}")
    except Exception:
        print("[ERROR] Render failed:", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

    print("[BlenderSceneAgent] Done!")


if __name__ == "__main__":
    main()
