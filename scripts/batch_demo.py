#!/usr/bin/env python3
"""Batch demo: run the pipeline on all test prompts.

Usage:
    python scripts/batch_demo.py --backend mock --skip-render
    python scripts/batch_demo.py --backend mock --render

Outputs are organized under outputs/batch_tests/<scene_name>/.
Summary reports are saved to test/batch_reports/ and outputs/batch_tests/.
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure project root is on the path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.json_utils import save_json, load_json
from core.file_utils import ensure_dir
from core.pipeline import SceneGenerationPipeline
from schema.scene_schema import SceneGraph, ValidationReport

# ---------------------------------------------------------------------------
# Expected objects per prompt (from TESTING.md §4-§7)
# ---------------------------------------------------------------------------
EXPECTED_OBJECTS: dict[str, set[str]] = {
    # Complex test prompts (TESTING.md §4)
    "cyberpunk_bedroom_complex": {
        "bed", "desk", "monitor", "keyboard", "chair", "carpet",
        "poster", "window", "neon_light",
    },
    "warm_study_room_complex": {
        "desk", "chair", "bookshelf", "book", "lamp", "carpet",
        "plant", "window", "poster", "wall_decoration",
    },
    "small_coffee_shop_complex": {
        "counter", "menu_board", "table", "chair", "cup", "lamp",
        "plant", "window",
    },
    "modern_classroom_complex": {
        "blackboard", "projector_screen", "desk", "chair", "window",
        "lamp", "bookshelf", "poster",
    },
    "sci_fi_laboratory_complex": {
        "table", "desk", "monitor", "glowing_tube", "shelf",
        "warning_sign", "neon_light",
    },
    "artist_studio_complex": {
        "table", "chair", "book", "cup", "shelf",
        "poster", "wall_decoration", "window", "carpet", "plant", "lamp",
    },
    "dense_gamer_room_stress": {
        "bed", "desk", "monitor", "keyboard", "cup", "chair",
        "bookshelf", "carpet", "neon_light", "poster", "window", "plant",
    },
    "cozy_living_room_stress": {
        "sofa", "table", "cup", "book", "carpet", "monitor",
        "bookshelf", "plant", "poster", "wall_decoration", "lamp",
    },
    "japanese_tea_room_stress": {
        "table", "chair", "sofa", "cup", "carpet", "shelf",
        "plant", "window", "wall_decoration", "lamp",
    },
    "futuristic_medical_room_stress": {
        "bed", "monitor", "table", "cup", "book", "shelf",
        "warning_sign", "glowing_tube", "window",
    },
    "wizard_study_room_repair_test": {
        "desk", "book", "lamp", "bookshelf", "wall_decoration",
        "window", "carpet", "neon_light", "glowing_tube",
    },
    # Legacy prompts (simpler versions)
    "cyberpunk_bedroom": {
        "bed", "desk", "monitor", "neon_light", "poster", "carpet", "window",
    },
    "cozy_study_room": {
        "desk", "chair", "bookshelf", "book", "lamp", "carpet", "plant", "window",
    },
    "small_coffee_shop": {
        "table", "chair", "counter", "menu_board", "plant", "lamp", "cup", "window",
    },
    "modern_classroom": {
        "blackboard", "projector_screen", "desk", "chair", "window", "lamp", "bookshelf",
    },
    "sci_fi_laboratory": {
        "desk", "table", "monitor", "glowing_tube", "shelf", "warning_sign", "neon_light",
    },
}

# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

def load_prompts(prompts_dir: Path) -> list[tuple[str, str]]:
    """Load all test prompt files.

    Args:
        prompts_dir: Directory containing .txt prompt files.

    Returns:
        List of (filename_stem, prompt_text) tuples.
    """
    results = []
    for prompt_file in sorted(prompts_dir.glob("*.txt")):
        name = prompt_file.stem
        with open(prompt_file, "r", encoding="utf-8") as f:
            text = f.read().strip()
        results.append((name, text))
    return results


# ---------------------------------------------------------------------------
# Layout report generation (pure Python, no Blender needed)
# ---------------------------------------------------------------------------

def generate_layout_report(scene_graph_dict: dict) -> dict | None:
    """Run the pure-Python layout pipeline and return a layout report.

    This runs the same geometry-safe layout pipeline that Blender uses,
    but without requiring Blender. Produces AABB, collision, and
    out-of-bounds information.

    Args:
        scene_graph_dict: The scene graph as a dict.

    Returns:
        Layout report dict, or None if generation failed.
    """
    try:
        from blender.layout import run_layout_pipeline, DEFAULT_SIZES
    except ImportError as e:
        logging.getLogger(__name__).warning("Cannot import layout module: %s", e)
        return None

    objects = scene_graph_dict.get("objects", [])
    relations = scene_graph_dict.get("relations", [])
    room = scene_graph_dict.get("room", {})
    scene_type = scene_graph_dict.get("scene_type", "generic_room")

    if not objects:
        return None

    # Convert objects/relations to the format expected by run_layout_pipeline
    layout_objects = []
    for obj in objects:
        obj_dict = {
            "id": obj.get("id", "unknown"),
            "type": obj.get("type", "unknown"),
            "size": obj.get("size", [1.0, 1.0, 1.0]),
            "semantic_position": obj.get("semantic_position", "center of the room"),
        }
        layout_objects.append(obj_dict)

    layout_relations = []
    for rel in relations:
        layout_relations.append({
            "subject": rel.get("subject", ""),
            "predicate": rel.get("predicate", ""),
            "object": rel.get("object", ""),
        })

    room_dict = {
        "width": room.get("width", 6.0),
        "depth": room.get("depth", 5.0),
        "height": room.get("height", 3.0),
    }

    try:
        result = run_layout_pipeline(
            objects=layout_objects,
            relations=layout_relations,
            room=room_dict,
            scene_type=scene_type,
            debug=False,
        )
        report = result.get("report", {})

        # Add per-object detail matching TESTING.md §9 format
        objects_detail = []
        placed = result.get("placed", {})
        for oid, pobj in placed.items():
            aabb = pobj.aabb
            objects_detail.append({
                "id": oid,
                "type": pobj.obj_type,
                "center": list(aabb.center),
                "size": list(aabb.size),
                "aabb_min": [aabb.min_x, aabb.min_y, aabb.min_z],
                "aabb_max": [aabb.max_x, aabb.max_y, aabb.max_z],
                "placement_rule": getattr(pobj, "placement_rule", "unknown"),
            })

        report["scene_id"] = scene_graph_dict.get("scene_id", "unknown")
        report["objects"] = objects_detail
        return report
    except Exception as e:
        logging.getLogger(__name__).warning("Layout pipeline failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Relation accuracy evaluation
# ---------------------------------------------------------------------------

def evaluate_relation_accuracy(
    relations: list[dict],
    objects: list[dict],
    layout_report: dict | None,
) -> tuple[int, int]:
    """Check how many relations are valid based on layout data.

    Args:
        relations: List of relation dicts.
        objects: List of object dicts.
        layout_report: Layout report from the pipeline (may be None).

    Returns:
        (num_valid, total) tuple.
    """
    object_ids = {obj["id"] for obj in objects}
    room_surfaces = {"back_wall", "front_wall", "left_wall", "right_wall", "ceiling", "floor"}
    valid_predicates = {"on", "near", "left_of", "right_of", "in_front_of", "behind", "attached_to", "inside", "facing"}

    total = len(relations)
    num_valid = 0

    if layout_report is None or "objects" not in layout_report:
        # Fall back to structural check only
        for rel in relations:
            subj = rel.get("subject", "")
            pred = rel.get("predicate", "")
            obj = rel.get("object", "")
            if (subj in object_ids and
                pred in valid_predicates and
                (obj in object_ids or obj in room_surfaces)):
                num_valid += 1
        return num_valid, total

    # Use layout data for geometric checks
    layout_objs = {o["id"]: o for o in layout_report.get("objects", [])}

    for rel in relations:
        subj = rel.get("subject", "")
        pred = rel.get("predicate", "")
        tgt = rel.get("object", "")

        # Basic structural check
        if not (subj in object_ids and pred in valid_predicates and (tgt in object_ids or tgt in room_surfaces)):
            continue

        # Geometric checks
        subj_data = layout_objs.get(subj)
        tgt_data = layout_objs.get(tgt)

        if pred == "on" and subj_data and tgt_data:
            # A on B: A.min_z >= B.max_z - tolerance
            subj_min_z = subj_data.get("aabb_min", [0, 0, 0])[2]
            tgt_max_z = tgt_data.get("aabb_max", [0, 0, 0])[2]
            if subj_min_z >= tgt_max_z - 0.05:
                num_valid += 1
                continue
        elif pred == "attached_to" and subj_data:
            # Wall attachment check — if target is a wall surface
            if tgt in room_surfaces:
                num_valid += 1
                continue
        elif pred == "near" and subj_data and tgt_data:
            # Distance check
            sc = subj_data.get("center", [0, 0, 0])
            tc = tgt_data.get("center", [0, 0, 0])
            dist = ((sc[0] - tc[0])**2 + (sc[1] - tc[1])**2) ** 0.5
            if dist < 4.0:  # within 4m
                num_valid += 1
                continue
        elif pred in ("left_of", "right_of", "in_front_of", "behind") and subj_data and tgt_data:
            num_valid += 1
            continue
        else:
            # Structurally valid, can't geometrically verify
            num_valid += 1
            continue

    return num_valid, total


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def compute_object_coverage(
    generated_types: set[str],
    expected_types: set[str],
    scene_name: str,
) -> float:
    """Compute the fraction of expected object types present.

    Some expected types are "fuzzy" — alternatives that count as one match.
    """
    if not expected_types:
        return 1.0

    # Some expected types have acceptable alternatives
    alternatives: dict[str, set[str]] = {
        "poster": {"poster", "wall_decoration"},
        "wall_decoration": {"poster", "wall_decoration"},
        "lamp": {"lamp", "neon_light"},
        "desk": {"desk", "table"},
        "table": {"desk", "table"},
        "sofa": {"sofa", "chair"},
        "chair": {"chair", "sofa"},
    }

    matched = 0
    for expected in expected_types:
        candidates = alternatives.get(expected, {expected})
        if candidates & generated_types:
            matched += 1

    return matched / len(expected_types) if expected_types else 1.0


def compute_layout_score(
    collisions_after: int,
    out_of_bounds_after: int,
    render_success: bool,
    render_attempted: bool,
    warnings_count: int,
) -> int:
    """Compute a 0-10 layout score (TESTING.md §13.4).

    10: no major layout issue
    8: minor overlaps but visually acceptable
    6: some visible collisions but scene still understandable
    4: several objects misplaced or intersecting
    2: scene mostly broken
    0: render explicitly failed (not skipped)

    When render is skipped, score is computed purely from collision/OOB data.
    """
    # Only score 0 when render was attempted but failed
    if render_attempted and not render_success:
        return 0
    if collisions_after == 0 and out_of_bounds_after == 0:
        return 10
    if collisions_after <= 1 and out_of_bounds_after == 0:
        return 8
    if collisions_after <= 2 and out_of_bounds_after <= 1:
        return 6
    if collisions_after <= 4 and out_of_bounds_after <= 2:
        return 4
    return 2


# ---------------------------------------------------------------------------
# Summary generation
# ---------------------------------------------------------------------------

def generate_summary_csv(results: list[dict], output_path: Path) -> None:
    """Generate summary.csv (TESTING.md §12).

    Args:
        results: List of per-scene result dicts.
        output_path: Where to write the CSV.
    """
    fieldnames = [
        "scene_name",
        "render_success",
        "num_objects_requested",
        "num_objects_generated",
        "object_coverage",
        "num_relations",
        "num_valid_relations",
        "relation_accuracy",
        "collisions_before",
        "collisions_after",
        "out_of_bounds_after",
        "num_warnings",
        "layout_score",
        "notes",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            row = {
                "scene_name": r.get("scene_name", ""),
                "render_success": r.get("render_success", False),
                "num_objects_requested": r.get("num_objects_requested", 0),
                "num_objects_generated": r.get("num_objects_generated", 0),
                "object_coverage": f"{r.get('object_coverage', 0):.2f}",
                "num_relations": r.get("num_relations", 0),
                "num_valid_relations": r.get("num_valid_relations", 0),
                "relation_accuracy": f"{r.get('relation_accuracy', 0):.2f}",
                "collisions_before": r.get("collisions_before", 0),
                "collisions_after": r.get("collisions_after", 0),
                "out_of_bounds_after": r.get("out_of_bounds_after", 0),
                "num_warnings": r.get("num_warnings", 0),
                "layout_score": r.get("layout_score", 0),
                "notes": r.get("notes", ""),
            }
            writer.writerow(row)
    print(f"  Summary CSV saved: {output_path}")


def generate_summary_md(results: list[dict], output_path: Path) -> None:
    """Generate summary.md (TESTING.md §12).

    Args:
        results: List of per-scene result dicts.
        output_path: Where to write the markdown.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rendered = [r for r in results if r.get("render_success")]
    render_failed = [r for r in results if not r.get("render_success") and r.get("status") == "success"]
    pipeline_fail = [r for r in results if r.get("status") != "success"]
    pipeline_ok = [r for r in results if r.get("status") == "success"]

    lines = [
        "# BlenderSceneAgent — Batch Test Summary",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Total scenes:** {len(results)}",
        "",
        "---",
        "",
        "## 1. Overall Results",
        "",
        f"| Status | Count |",
        f"|--------|-------|",
        f"| Pipeline OK | {len(pipeline_ok)} |",
        f"| Pipeline Failed | {len(pipeline_fail)} |",
        f"| Rendered | {len(rendered)} |",
        f"| Render Skipped/Failed | {len(render_failed)} |",
        "",
    ]

    # Per-scene table
    lines += [
        "## 2. Per-Scene Results",
        "",
        "| Scene | Status | Objects | Coverage | Relations | Rel.Acc. | Collisions (after) | Layout Score |",
        "|-------|--------|---------|----------|-----------|----------|---------------------|--------------|",
    ]

    for r in results:
        name = r.get("scene_name", "?")
        status = "✅" if r.get("status") == "success" else "❌"
        obj_info = f"{r.get('num_objects_generated', 0)}/{r.get('num_objects_requested', 0)}"
        cov = f"{r.get('object_coverage', 0):.0%}"
        rel_info = str(r.get("num_relations", 0))
        rel_acc = f"{r.get('relation_accuracy', 0):.0%}"
        coll = str(r.get("collisions_after", "N/A"))
        score = str(r.get("layout_score", "N/A"))
        lines.append(
            f"| {name} | {status} | {obj_info} | {cov} | {rel_info} | {rel_acc} | {coll} | {score} |"
        )

    # Scenes that passed
    lines += [
        "",
        "## 3. Passing Scenes",
        "",
    ]
    for r in pipeline_ok:
        lines.append(f"- **{r['scene_name']}** — coverage={r.get('object_coverage', 0):.0%}, score={r.get('layout_score', 'N/A')}")

    # Scenes that failed
    if pipeline_fail:
        lines += [
            "",
            "## 4. Failing Scenes",
            "",
            "| Scene | Error |",
            "|-------|-------|",
        ]
        for r in pipeline_fail:
            lines.append(f"| {r['scene_name']} | {r.get('error', 'unknown')} |")

    # Common collision problems
    lines += [
        "",
        "## 5. Common Collision Problems",
        "",
    ]
    collision_scenes = [r for r in results if r.get("collisions_after", 0) > 0]
    if collision_scenes:
        for r in collision_scenes:
            lines.append(f"- **{r['scene_name']}**: {r.get('collisions_after', 0)} collisions after resolution")
    else:
        lines.append("No collision issues found across all scenes.")

    # Unsupported object mappings
    lines += [
        "",
        "## 6. Common Unsupported Object Mappings",
        "",
        "| Scene | Unsupported Objects (Removed/Repaired) |",
        "|-------|----------------------------------------|",
    ]
    for r in results:
        unsupported = r.get("unsupported_objects", [])
        if unsupported:
            lines.append(f"| {r['scene_name']} | {', '.join(unsupported)} |")
        else:
            lines.append(f"| {r['scene_name']} | (none) |")

    # Recommended fixes
    lines += [
        "",
        "## 7. Recommended Fixes",
        "",
    ]
    low_coverage = [r for r in results if r.get("object_coverage", 1.0) < 0.75]
    low_relations = [r for r in results if r.get("relation_accuracy", 1.0) < 0.70]
    high_collisions = [r for r in results if r.get("collisions_after", 0) > 2]

    if low_coverage:
        names = ", ".join(r["scene_name"] for r in low_coverage)
        lines.append(f"- **Low object coverage (<75%):** {names} — consider adding more object types to the mock planner or expanding DEFAULT_SIZES.")
    if low_relations:
        names = ", ".join(r["scene_name"] for r in low_relations)
        lines.append(f"- **Low relation accuracy (<70%):** {names} — review relation predicates and layout anchor rules.")
    if high_collisions:
        names = ", ".join(r["scene_name"] for r in high_collisions)
        lines.append(f"- **High collision count (>2):** {names} — tune collision resolution shift distances or add object-specific exclusions.")
    if not low_coverage and not low_relations and not high_collisions:
        lines.append("No critical fixes needed based on automated metrics.")

    lines += [
        "",
        "## 8. Notes",
        "",
        "- Layout reports are generated in pure Python (no Blender required).",
        "- Render column shows `True` only when `--render` was used and Blender was available.",
        "- Object coverage uses fuzzy matching (e.g., `poster` ↔ `wall_decoration`, `desk` ↔ `table`).",
        "- Layout score: 10=perfect, 8=minor overlaps, 6=visible issues, 4=misplaced, 2=broken, 0=failed.",
        "",
        "---",
        "",
        f"*Report generated by batch_demo.py*",
    ]

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Summary Markdown saved: {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Batch demo: run BlenderSceneAgent pipeline on all test prompts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all tests without Blender:
  python scripts/batch_demo.py --backend mock --skip-render

  # Run all tests with Blender rendering:
  python scripts/batch_demo.py --backend mock --render

  # Custom prompts directory:
  python scripts/batch_demo.py --backend mock --skip-render --prompts-dir my_prompts/
        """,
    )
    parser.add_argument(
        "--backend", "-b",
        type=str,
        default="mock",
        choices=["mock", "openai_compatible"],
        help="Agent backend mode (default: mock).",
    )
    parser.add_argument(
        "--skip-render",
        action="store_true",
        default=True,
        help="Skip Blender render step (default).",
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
        help="Directory containing prompt .txt files (default: examples/prompts).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Root output directory (default: outputs/batch_tests).",
    )
    parser.add_argument(
        "--blender",
        type=str,
        default=None,
        help="Path to Blender executable (default: auto-detect via PATH).",
    )
    return parser.parse_args()


def setup_scene_logger(scene_dir: Path, scene_name: str) -> logging.Logger:
    """Create a per-scene logger that writes to run.log."""
    logger = logging.getLogger(f"batch.{scene_name}")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    # File handler
    log_path = scene_dir / "run.log"
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)

    # Also log to parent (root logger with console output)
    root = logging.getLogger()
    logger.parent = root

    return logger


def main() -> None:
    """Run the batch demo."""
    args = parse_args()

    # Resolve render flag
    if args.render:
        args.skip_render = False
    do_render = not args.skip_render

    # Prompt directory
    prompts_dir = Path(args.prompts_dir) if args.prompts_dir else (
        _PROJECT_ROOT / "examples" / "prompts"
    )

    if not prompts_dir.exists():
        print(f"[ERROR] Prompts directory not found: {prompts_dir}")
        sys.exit(1)

    prompts = load_prompts(prompts_dir)
    if not prompts:
        print(f"[ERROR] No .txt prompt files found in: {prompts_dir}")
        sys.exit(1)
    print(f"Found {len(prompts)} test prompts\n")

    # Output directories
    batch_dir = Path(args.output_dir) if args.output_dir else (
        _PROJECT_ROOT / "outputs" / "batch_tests"
    )
    batch_dir = ensure_dir(batch_dir)

    # Summary output dir (also under test/)
    test_reports_dir = ensure_dir(_PROJECT_ROOT.parent / "test" / "batch_reports")

    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if root_logger.handlers:
        root_logger.handlers.clear()
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    root_logger.addHandler(ch)

    # Check Blender availability for render
    blender_exe = None
    if do_render:
        if args.blender:
            blender_path = Path(args.blender)
            if blender_path.exists():
                blender_exe = str(blender_path.resolve())
            else:
                print(f"[WARNING] Blender not found at: {args.blender}")
        if blender_exe is None:
            blender_exe = shutil.which("blender") or shutil.which("blender.exe")
        if blender_exe is None:
            print("[WARNING] Blender not found. Render step will be skipped.\n"
                  "  Use --blender PATH to specify the Blender executable.")
        else:
            print(f"[INFO] Blender: {blender_exe}\n")

    # ------------------------------------------------------------------
    # Run each prompt through the pipeline
    # ------------------------------------------------------------------
    results: list[dict] = []
    start_time = time.time()

    for idx, (name, prompt_text) in enumerate(prompts, 1):
        print(f"{'=' * 60}")
        print(f"[{idx}/{len(prompts)}] {name}")
        print(f"  Prompt: {prompt_text[:100]}{'...' if len(prompt_text) > 100 else ''}")
        print(f"{'=' * 60}")

        scene_dir = ensure_dir(batch_dir / name)
        scene_logger = setup_scene_logger(scene_dir, name)
        scene_logger.info("Batch test started: %s", name)
        scene_logger.info("Prompt: %s", prompt_text)

        # Save prompt.txt
        prompt_path = scene_dir / "prompt.txt"
        prompt_path.write_text(prompt_text, encoding="utf-8")
        scene_logger.info("Saved prompt.txt")

        result: dict[str, Any] = {
            "scene_name": name,
            "status": "pending",
            "render_success": False,
            "num_objects_requested": 0,
            "num_objects_generated": 0,
            "object_coverage": 0.0,
            "num_relations": 0,
            "num_valid_relations": 0,
            "relation_accuracy": 0.0,
            "collisions_before": 0,
            "collisions_after": 0,
            "out_of_bounds_after": 0,
            "num_warnings": 0,
            "layout_score": 0,
            "unsupported_objects": [],
            "notes": "",
            "error": "",
        }

        try:
            # Run pipeline
            pipeline = SceneGenerationPipeline(
                backend=args.backend,
                output_dir=str(scene_dir),
                debug_layout=True,
            )

            pipeline_results = pipeline.run(
                user_prompt=prompt_text,
                skip_render=True,
            )

            result["status"] = "success"
            scene_logger.info("Pipeline completed successfully")

            # --- Collect data from pipeline output ---

            # Load initial scene graph
            initial_sg_path = pipeline_results.get("initial_scene_graph")
            initial_sg = {}
            if initial_sg_path and Path(initial_sg_path).exists():
                initial_sg = load_json(initial_sg_path)
                # Copy to standardized name
                save_json(initial_sg, scene_dir / "initial_scene_graph.json")

            # Load validation report
            validation_path = pipeline_results.get("validation_report")
            validation_data = {}
            if validation_path and Path(validation_path).exists():
                validation_data = load_json(validation_path)
                save_json(validation_data, scene_dir / "validation_report.json")

            # Load repaired scene graph (if exists)
            repaired_path = pipeline_results.get("repaired_scene_graph")
            repaired_sg = None
            if repaired_path and Path(repaired_path).exists():
                repaired_sg = load_json(repaired_path)
                save_json(repaired_sg, scene_dir / "repaired_scene_graph.json")

            # Determine the final scene graph for layout
            final_sg = repaired_sg or initial_sg

            # --- Object coverage ---
            generated_types = set()
            for obj in final_sg.get("objects", []):
                generated_types.add(obj.get("type", ""))
            result["num_objects_generated"] = len(generated_types)

            expected = EXPECTED_OBJECTS.get(name, set())
            result["num_objects_requested"] = len(expected)
            result["object_coverage"] = compute_object_coverage(generated_types, expected, name)

            # --- Relations ---
            relations = final_sg.get("relations", [])
            result["num_relations"] = len(relations)

            # --- Layout report (pure Python) ---
            layout_report = generate_layout_report(final_sg)
            if layout_report:
                save_json(layout_report, scene_dir / "layout_report.json")
                result["collisions_before"] = layout_report.get("collision_count_before", len(
                    layout_report.get("collisions_before", [])))
                result["collisions_after"] = layout_report.get("collision_count_after", len(
                    layout_report.get("collisions_after", [])))
                result["out_of_bounds_after"] = len(layout_report.get("out_of_bounds_after", []))
                result["num_warnings"] = len(layout_report.get("warnings", []))
                scene_logger.info("Layout report generated in pure Python")
            else:
                scene_logger.warning("Layout report generation skipped (no objects or import error)")

            # --- Relation accuracy ---
            num_valid, total = evaluate_relation_accuracy(
                relations, final_sg.get("objects", []), layout_report,
            )
            result["num_valid_relations"] = num_valid
            result["relation_accuracy"] = num_valid / total if total > 0 else 1.0

            # --- Validation data ---
            result["num_warnings"] = max(
                result["num_warnings"],
                len(validation_data.get("warnings", [])),
            )
            result["unsupported_objects"] = validation_data.get("unsupported_objects", [])

            # --- Render (if enabled) ---
            if do_render and blender_exe:
                scene_logger.info("Attempting Blender render...")
                render_sg_path = Path(repaired_path or initial_sg_path).resolve()
                render_output = (scene_dir / "render.png").resolve()
                blend_output = (scene_dir / "scene.blend").resolve()
                run_script = (_PROJECT_ROOT / "scripts" / "run_blender_scene.py").resolve()

                # ------------------------------------------------------------------
                # Convert paths for Windows Blender (wslpath -w)
                # ------------------------------------------------------------------
                def _to_blender_path(p: Path) -> str:
                    """Convert a WSL path to a path Blender.exe can understand.

                    For Windows Blender: use wslpath -w to get Windows-native path.
                    For Linux Blender: use the WSL path directly.
                    Falls back to relative path if wslpath fails.
                    """
                    try:
                        r = subprocess.run(
                            ["wslpath", "-w", str(p)],
                            capture_output=True, text=True, timeout=5,
                        )
                        if r.returncode == 0:
                            return r.stdout.strip()
                    except Exception:
                        pass
                    # Fallback: use relative path from project root
                    try:
                        return str(p.relative_to(_PROJECT_ROOT))
                    except ValueError:
                        return str(p)

                cmd = [
                    blender_exe,
                    "--background",
                    "--python", _to_blender_path(run_script),
                    "--",
                    "--scene-json", _to_blender_path(render_sg_path),
                    "--output", _to_blender_path(render_output),
                    "--debug-layout",
                    "--save-blend", _to_blender_path(blend_output),
                ]

                try:
                    subprocess.run(cmd, check=True, timeout=300,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                    # Check the expected output location
                    if render_output.exists():
                        result["render_success"] = True
                        scene_logger.info("Render completed: %s", render_output)
                    else:
                        # Check Windows C: drive fallback (Blender default output drive)
                        win_render = Path(
                            str(render_output).replace("/mnt/e/", "E:\\").replace("/", "\\")
                        )
                        if win_render.exists():
                            import shutil as _shutil
                            _shutil.copy2(str(win_render), str(render_output))
                            result["render_success"] = True
                            scene_logger.info("Render copied from %s to %s", win_render, render_output)
                        else:
                            scene_logger.warning("Render output not found at %s or %s",
                                                 render_output, win_render)
                except subprocess.CalledProcessError as e:
                    scene_logger.error("Blender render failed (exit code %d)", e.returncode)
                    if e.stderr:
                        scene_logger.error("Stderr: %s", e.stderr.decode(errors="replace")[:500])
                    result["notes"] = f"Render failed: exit code {e.returncode}"
                except subprocess.TimeoutExpired:
                    scene_logger.error("Blender render timed out (300s)")
                    result["notes"] = "Render timed out"
                except Exception as e:
                    scene_logger.error("Blender render error: %s", e)
                    result["notes"] = f"Render error: {e}"

            # --- Layout score (after render so render_success is final) ---
            result["layout_score"] = compute_layout_score(
                result["collisions_after"],
                result["out_of_bounds_after"],
                result["render_success"],
                render_attempted=do_render,
                warnings_count=result["num_warnings"],
            )

            # Compile notes
            notes_parts = []
            if result["object_coverage"] < 0.75:
                missing = expected - generated_types
                notes_parts.append(f"Low coverage: missing {missing}")
            if result["collisions_after"] > 2:
                notes_parts.append(f"High collisions: {result['collisions_after']}")
            if result["unsupported_objects"]:
                notes_parts.append(f"Unsupported: {result['unsupported_objects']}")
            if validation_data.get("weak_style_elements"):
                notes_parts.append(f"Weak style: {validation_data['weak_style_elements']}")
            result["notes"] = "; ".join(notes_parts) or result.get("notes", "")

            scene_logger.info(
                "Summary: objects=%d/%d (%.0f%%), relations=%d (%.0f%%), collisions=%d, score=%d",
                result["num_objects_generated"], result["num_objects_requested"],
                result["object_coverage"] * 100,
                result["num_relations"], result["relation_accuracy"] * 100,
                result["collisions_after"], result["layout_score"],
            )

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            scene_logger.error("Pipeline FAILED: %s", e)
            import traceback
            scene_logger.error(traceback.format_exc())
            print(f"  [FAILED] {e}")

        results.append(result)
        print(f"  Result: {result['status']} | objects={result['num_objects_generated']}/{result['num_objects_requested']} | collisions={result['collisions_after']} | score={result['layout_score']}\n")

    # ------------------------------------------------------------------
    # Generate summaries
    # ------------------------------------------------------------------
    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"Batch Complete — {len(results)} scenes in {elapsed:.1f}s")
    print(f"{'=' * 60}")

    # Save per-scene results as JSON
    save_json(results, batch_dir / "batch_results.json")

    # Generate summary CSV + MD
    generate_summary_csv(results, batch_dir / "summary.csv")
    generate_summary_md(results, batch_dir / "summary.md")

    # Also save to test/batch_reports/
    generate_summary_csv(results, test_reports_dir / "summary.csv")
    generate_summary_md(results, test_reports_dir / "summary.md")

    # Quick console summary
    success_count = sum(1 for r in results if r["status"] == "success")
    render_count = sum(1 for r in results if r.get("render_success"))
    print(f"\n  Pipeline OK: {success_count}/{len(results)}")
    if do_render:
        print(f"  Rendered:    {render_count}/{len(results)}")
    print(f"  Output:      {batch_dir}")
    print(f"  Reports:     {test_reports_dir}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
