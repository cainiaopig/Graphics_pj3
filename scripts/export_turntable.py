#!/usr/bin/env python3
"""Turntable video export — placeholder for future implementation.

Usage (future):
    blender --background --python scripts/export_turntable.py -- \\
        --scene-json path/to/scene.json \\
        --output path/to/turntable.mp4 \\
        --frames 120
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    argv = sys.argv
    try:
        double_dash = argv.index("--")
        script_args = argv[double_dash + 1:]
    except ValueError:
        script_args = []

    parser = argparse.ArgumentParser(
        description="Turntable video export (future feature)",
    )
    parser.add_argument("--scene-json", type=str, required=True)
    parser.add_argument("--output", type=str, required=True)
    parser.add_argument("--frames", type=int, default=120)

    return parser.parse_args(script_args)


def main() -> None:
    """Placeholder for turntable export."""
    args = parse_args()
    print("[Turntable] This feature is not yet implemented (planned for future version).")
    print(f"  Scene: {args.scene_json}")
    print(f"  Output: {args.output}")
    print(f"  Frames: {args.frames}")


if __name__ == "__main__":
    main()
