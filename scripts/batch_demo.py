#!/usr/bin/env python3
"""Batch demo: run the pipeline on all example prompts.

Usage:
    python scripts/batch_demo.py --backend mock [--render]

Outputs are organized under outputs/batch/<scene_name>/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on the path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.json_utils import save_json
from core.logging_utils import setup_logger
from core.pipeline import SceneGenerationPipeline


def load_prompts(prompts_dir: Path) -> list[tuple[str, str, str]]:
    """Load all example prompt files.

    Args:
        prompts_dir: Directory containing .txt prompt files.

    Returns:
        List of (filename_stem, scene_type, prompt_text) tuples.
    """
    results = []
    for prompt_file in sorted(prompts_dir.glob("*.txt")):
        name = prompt_file.stem  # e.g., "cyberpunk_bedroom"
        with open(prompt_file, "r", encoding="utf-8") as f:
            text = f.read().strip()
        # Infer scene type from filename
        scene_type = name  # cyberpunk_bedroom, cozy_study_room, etc.
        results.append((name, scene_type, text))
    return results


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Batch demo for BlenderSceneAgent",
    )
    parser.add_argument(
        "--backend", "-b",
        type=str,
        default="mock",
        choices=["mock"],
        help="Agent backend (default: mock).",
    )
    parser.add_argument(
        "--render",
        action="store_true",
        default=False,
        help="Attempt to render each scene with Blender.",
    )
    parser.add_argument(
        "--prompts-dir",
        type=str,
        default=None,
        help="Directory containing prompt .txt files.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the batch demo."""
    args = parse_args()

    prompts_dir = Path(args.prompts_dir) if args.prompts_dir else (
        _PROJECT_ROOT / "examples" / "prompts"
    )

    if not prompts_dir.exists():
        print(f"Prompts directory not found: {prompts_dir}")
        sys.exit(1)

    prompts = load_prompts(prompts_dir)
    print(f"Found {len(prompts)} example prompts")

    # Setup batch output directory
    batch_dir = _PROJECT_ROOT / "outputs" / "batch"
    logger = setup_logger(log_file=batch_dir / "batch_run.log")

    results_summary = []

    for idx, (name, scene_type, prompt_text) in enumerate(prompts, 1):
        print(f"\n{'=' * 60}")
        print(f"[{idx}/{len(prompts)}] Processing: {name}")
        print(f"  Prompt: {prompt_text[:80]}...")
        print(f"{'=' * 60}")

        scene_output_dir = batch_dir / name
        scene_output_dir.mkdir(parents=True, exist_ok=True)

        # Save the prompt
        prompt_path = scene_output_dir / "prompt.txt"
        prompt_path.write_text(prompt_text, encoding="utf-8")

        # Run pipeline
        pipeline = SceneGenerationPipeline(
            backend=args.backend,
            output_dir=scene_output_dir,
        )

        try:
            results = pipeline.run(
                user_prompt=prompt_text,
                skip_render=not args.render,
            )

            # Save combined results summary
            save_json(results, scene_output_dir / "pipeline_results.json")

            results_summary.append({
                "scene": name,
                "status": "success",
                "is_valid": results.get("is_valid"),
                "score": results.get("validation_score"),
                "post_repair_valid": results.get("post_repair_valid"),
            })

            logger.info("[%d/%d] %s: valid=%s score=%.2f",
                         idx, len(prompts), name,
                         results.get("is_valid"),
                         results.get("validation_score", 0))

        except Exception as e:
            logger.error("[%d/%d] %s: FAILED - %s", idx, len(prompts), name, e)
            results_summary.append({
                "scene": name,
                "status": "failed",
                "error": str(e),
            })

    # Save overall summary
    save_json(results_summary, batch_dir / "batch_summary.json")

    # Print summary
    print(f"\n{'=' * 60}")
    print("Batch Demo Summary")
    print(f"{'=' * 60}")
    success_count = sum(1 for r in results_summary if r["status"] == "success")
    print(f"  Total:  {len(results_summary)}")
    print(f"  Passed: {success_count}")
    print(f"  Failed: {len(results_summary) - success_count}")
    print(f"  Output: {batch_dir}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
