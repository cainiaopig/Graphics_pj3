#!/usr/bin/env python3
"""BlenderSceneAgent — Main CLI entry point.

Usage:
    python main.py --prompt "Create a cozy cyberpunk bedroom..." --backend mock --skip-render
    python main.py --scene-json path/to/scene.json --render
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.logging_utils import setup_logger
from core.pipeline import SceneGenerationPipeline


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="BlenderSceneAgent — AI-assisted 3D scene generation pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full mock pipeline without rendering:
  python main.py --prompt "Create a cozy cyberpunk bedroom with neon lights." --backend mock --skip-render

  # Render an existing scene graph:
  python main.py --scene-json outputs/scene_json/latest_scene_graph.json --render

  # Custom output directory:
  python main.py --prompt "A warm study room" --backend mock --output-dir my_outputs --skip-render
        """,
    )

    parser.add_argument(
        "--prompt", "-p",
        type=str,
        default=None,
        help="Natural language scene description.",
    )
    parser.add_argument(
        "--backend", "-b",
        type=str,
        default="mock",
        choices=["mock", "openai_compatible"],
        help="Agent backend mode (default: mock).",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="outputs",
        help="Root output directory (default: outputs).",
    )
    parser.add_argument(
        "--skip-render",
        action="store_true",
        default=True,
        help="Skip Blender render step (default: True).",
    )
    parser.add_argument(
        "--render",
        action="store_true",
        default=False,
        help="Attempt to render with Blender (requires Blender installed).",
    )
    parser.add_argument(
        "--scene-json",
        type=str,
        default=None,
        help="Path to an existing scene graph JSON. Skips planning if provided.",
    )
    parser.add_argument(
        "--debug-layout",
        action="store_true",
        default=False,
        help="Print layout debug info and save layout report.",
    )

    return parser.parse_args()


def main() -> None:
    """Run the scene generation pipeline."""
    args = parse_args()

    # Setup logging
    log_dir = Path(args.output_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "latest_run.log"
    logger = setup_logger(log_file=log_file)
    logger.info("BlenderSceneAgent starting...")

    # Validate arguments
    if not args.prompt and not args.scene_json:
        logger.error("Either --prompt or --scene-json must be provided.")
        sys.exit(1)

    prompt = args.prompt or "Scene from file"

    # Determine render flag
    skip_render = not args.render  # --render overrides default --skip-render

    # Run the pipeline
    pipeline = SceneGenerationPipeline(
        backend=args.backend,
        output_dir=args.output_dir,
        debug_layout=args.debug_layout,
    )

    results = pipeline.run(
        user_prompt=prompt,
        skip_render=skip_render,
        scene_json_path=args.scene_json,
    )

    # Print summary
    print("\n" + "=" * 60)
    print("Pipeline Results")
    print("=" * 60)
    print(f"  Backend:            {results['backend']}")
    print(f"  Valid:              {results.get('is_valid', 'N/A')}")
    print(f"  Score:              {results.get('validation_score', 'N/A')}")
    print(f"  Initial scene:      {results.get('initial_scene_graph', 'N/A')}")
    print(f"  Validation report:  {results.get('validation_report', 'N/A')}")
    if "repaired_scene_graph" in results:
        print(f"  Repaired scene:     {results['repaired_scene_graph']}")
        print(f"  Post-repair valid:  {results.get('post_repair_valid', 'N/A')}")
    if "render_output" in results:
        print(f"  Render:             {results['render_output']}")
    print("=" * 60)

    # Exit with appropriate code
    if results.get("is_valid", True):
        sys.exit(0)
    else:
        logger.warning("Scene graph had validation issues (see report for details)")
        sys.exit(0)  # Still exit 0 — validation issues are expected in mock mode


if __name__ == "__main__":
    main()
