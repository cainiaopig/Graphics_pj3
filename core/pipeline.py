"""Main scene generation pipeline.

Orchestrates the full flow:
  User Prompt -> Planner -> Scene Graph -> Validator -> (Repair) -> Output Files
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from agents.planner_agent import PlannerAgent
from agents.repair_agent import RepairAgent
from agents.validator_agent import ValidatorAgent
from agents.visual_critic_agent import VisualCriticAgent
from core.file_utils import ensure_dir, latest_symlink, timestamped_filename
from core.json_utils import save_json
from core.logging_utils import setup_logger
from schema.scene_schema import SceneGraph, ValidationReport

logger = logging.getLogger(__name__)


class SceneGenerationPipeline:
    """Orchestrates the full scene generation pipeline.

    Steps:
    1. Plan: Generate initial scene graph from user prompt.
    2. Save: Write initial scene graph to disk.
    3. Validate: Run rule-based validation.
    4. Save: Write validation report to disk.
    5. Repair (if needed): Fix issues identified by validation.
    6. Save: Write repaired scene graph to disk.
    7. Render (optional): Call Blender to render the scene.
    """

    def __init__(
        self,
        backend: str = "mock",
        output_dir: str | Path = "outputs",
        debug_layout: bool = False,
        blender_path: str | None = None,
    ) -> None:
        """Initialize the pipeline.

        Args:
            backend: Agent backend mode ("mock" or "openai_compatible").
            output_dir: Root directory for all output files.
            debug_layout: If True, save layout reports and print debug info.
            blender_path: Optional path to Blender executable.
        """
        self.backend = backend
        self.output_dir = Path(output_dir)
        self.debug_layout = debug_layout
        self.blender_path = blender_path

        # Sub-directories
        self.scene_json_dir = ensure_dir(self.output_dir / "scene_json")
        self.validation_dir = ensure_dir(self.output_dir / "validation")
        self.critique_dir = ensure_dir(self.output_dir / "critique")
        self.blender_dir = ensure_dir(self.output_dir / "blender_scripts")
        self.renders_dir = ensure_dir(self.output_dir / "renders")
        self.logs_dir = ensure_dir(self.output_dir / "logs")

        # Agents
        self.planner = PlannerAgent(backend=backend)
        self.validator = ValidatorAgent(backend=backend)
        self.repair = RepairAgent(backend=backend)
        self.visual_critic = VisualCriticAgent(backend="mock")

    def run(
        self,
        user_prompt: str,
        skip_render: bool = True,
        scene_json_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Run the full pipeline.

        Args:
            user_prompt: Natural language scene description.
            skip_render: If True, skip the Blender render step.
            scene_json_path: If provided, skip planning and use this scene graph.

        Returns:
            Dictionary with paths to all generated outputs and pipeline results.
        """
        results: dict[str, Any] = {
            "prompt": user_prompt,
            "backend": self.backend,
            "timestamp": datetime.now().isoformat(),
        }

        logger.info("=" * 60)
        logger.info("Scene Generation Pipeline Started")
        logger.info("Backend: %s", self.backend)
        logger.info("Prompt: %s", user_prompt[:100] + "..." if len(user_prompt) > 100 else user_prompt)
        logger.info("=" * 60)

        # Step 1: Plan (or load existing)
        if scene_json_path:
            logger.info("Step 1: Loading existing scene graph from %s", scene_json_path)
            from core.json_utils import load_json
            data = load_json(scene_json_path)
            scene_graph = SceneGraph(**data)
        else:
            logger.info("Step 1: Planning scene graph...")
            scene_graph = self.planner.plan(user_prompt)

        # Step 2: Save initial scene graph
        logger.info("Step 2: Saving initial scene graph...")
        initial_filename = timestamped_filename("scene_graph", "json")
        initial_path = self.scene_json_dir / initial_filename
        save_json(scene_graph, initial_path)
        latest_symlink(initial_path, self.scene_json_dir, "latest_scene_graph.json")
        results["initial_scene_graph"] = str(initial_path)
        logger.info("  Saved: %s", initial_path)

        # Step 3: Validate
        logger.info("Step 3: Validating scene graph...")
        validation_report = self.validator.validate(user_prompt, scene_graph)

        # Step 4: Save validation report
        logger.info("Step 4: Saving validation report...")
        report_filename = timestamped_filename("validation_report", "json")
        report_path = self.validation_dir / report_filename
        save_json(validation_report, report_path)
        latest_symlink(report_path, self.validation_dir, "latest_validation_report.json")
        results["validation_report"] = str(report_path)
        results["is_valid"] = validation_report.is_valid
        results["validation_score"] = validation_report.score
        logger.info("  Saved: %s (valid=%s, score=%.2f)",
                     report_path, validation_report.is_valid, validation_report.score)

        # Step 5 & 6: Repair if needed
        if not validation_report.is_valid or validation_report.suggestions:
            logger.info("Step 5: Repairing scene graph...")
            repaired_graph = self.repair.repair(user_prompt, scene_graph, validation_report)

            logger.info("Step 6: Saving repaired scene graph...")
            repaired_filename = timestamped_filename("repaired_scene_graph", "json")
            repaired_path = self.scene_json_dir / repaired_filename
            save_json(repaired_graph, repaired_path)
            latest_symlink(repaired_path, self.scene_json_dir, "latest_repaired_scene_graph.json")
            results["repaired_scene_graph"] = str(repaired_path)
            logger.info("  Saved: %s", repaired_path)

            # Re-validate after repair
            logger.info("  Re-validating after repair...")
            post_report = self.validator.validate(user_prompt, repaired_graph)
            results["post_repair_valid"] = post_report.is_valid
            results["post_repair_score"] = post_report.score
            logger.info("  Post-repair: valid=%s, score=%.2f",
                         post_report.is_valid, post_report.score)
        else:
            logger.info("Step 5-6: No repair needed (scene graph is valid)")

        # Step 7: Render (optional)
        if not skip_render:
            logger.info("Step 7: Rendering with Blender...")
            self._render_step(results)
        else:
            logger.info("Step 7: Render skipped (--skip-render)")

        # Step 8: Offline visual/scene critique
        logger.info("Step 8: Running offline visual critique...")
        self._critique_step(user_prompt, results)

        logger.info("=" * 60)
        logger.info("Pipeline Complete!")
        logger.info("=" * 60)

        return results

    def _critique_step(self, user_prompt: str, results: dict[str, Any]) -> None:
        """Run an offline post-generation critique and save it to disk."""
        scene_json = results.get("repaired_scene_graph") or results.get("initial_scene_graph")
        if not scene_json:
            logger.warning("No scene graph available for critique")
            return

        image_path = results.get("render_output")
        critique = self.visual_critic.critique(
            user_prompt=user_prompt,
            image_path=image_path,
            scene_json_path=scene_json,
        )
        critique_filename = timestamped_filename("visual_critique", "json")
        critique_path = self.critique_dir / critique_filename
        save_json(critique, critique_path)
        latest_symlink(critique_path, self.critique_dir, "latest_visual_critique.json")
        results["visual_critique"] = str(critique_path)
        results["visual_critique_score"] = critique.get("score")
        logger.info("  Critique saved: %s (score=%s)", critique_path, critique.get("score"))

    def _render_step(self, results: dict[str, Any]) -> None:
        """Attempt to render the scene using Blender.

        If Blender is not available, prints instructions instead of failing.

        Args:
            results: Pipeline results dict (mutated in place).
        """
        import platform
        import shutil
        import subprocess

        # Determine which scene graph to render (repaired if available)
        scene_json = results.get("repaired_scene_graph") or results.get("initial_scene_graph")
        if not scene_json:
            logger.warning("No scene graph available for rendering")
            return

        scene_json_path = Path(scene_json)

        # Locate Blender: explicit path > PATH search
        blender_exe = self.blender_path
        if blender_exe and not Path(blender_exe).exists():
            logger.warning("Blender not found at: %s", blender_exe)
            blender_exe = None
        if blender_exe is None:
            blender_exe = shutil.which("blender") or shutil.which("blender.exe")
        if blender_exe is None:
            logger.warning(
                "Blender executable not found. "
                "Use --blender PATH to specify the Blender executable, or:\n"
                "  blender --background --python scripts/run_blender_scene.py -- "
                "--scene-json %s --output outputs/renders/latest_render.png",
                scene_json,
            )
            results["render_status"] = "skipped (Blender not found)"
            return

        output_path = (self.renders_dir / "latest_render.png").resolve()
        blend_path = (self.blender_dir / "latest_scene.blend").resolve()
        run_script = (Path(__file__).resolve().parent.parent / "scripts" / "run_blender_scene.py").resolve()

        # ------------------------------------------------------------------
        # Convert paths for Windows Blender (uses wslpath -w if available)
        # ------------------------------------------------------------------
        def _to_blender_path(p: Path) -> str:
            try:
                import subprocess as sp
                r = sp.run(["wslpath", "-w", str(p)], capture_output=True, text=True, timeout=5)
                if r.returncode == 0:
                    return r.stdout.strip()
            except Exception:
                pass
            return str(p)

        cmd = [
            blender_exe,
            "--background",
            "--python", _to_blender_path(run_script),
            "--",
            "--scene-json", _to_blender_path(scene_json_path.resolve()),
            "--output", _to_blender_path(output_path),
            "--save-blend", _to_blender_path(blend_path),
        ]

        if self.debug_layout:
            cmd.append("--debug-layout")

        logger.info("  Running: %s", " ".join(cmd))
        try:
            subprocess.run(cmd, check=True, timeout=300)
            # Check output exists
            if output_path.exists():
                results["render_output"] = str(output_path)
            else:
                # Check Windows fallback
                try:
                    import subprocess as sp
                    win_out = sp.run(["wslpath", "-w", str(output_path)],
                                     capture_output=True, text=True).stdout.strip()
                    win_path = Path(win_out)
                except Exception:
                    win_path = Path(str(output_path).replace("/mnt/e/", "E:\\").replace("/", "\\"))
                if win_path.exists():
                    shutil.copy2(str(win_path), str(output_path))
                    results["render_output"] = str(output_path)
            results["blend_file"] = str(blend_path) if blend_path.exists() else str(blend_path)
            results["render_status"] = "completed"
            logger.info("  Render saved: %s", output_path)
            logger.info("  Blend saved: %s", blend_path)
        except subprocess.CalledProcessError as e:
            logger.error("  Blender render failed: %s", e)
            results["render_status"] = f"failed: {e}"
        except subprocess.TimeoutExpired:
            logger.error("  Blender render timed out (300s)")
            results["render_status"] = "timeout"

        if self.debug_layout:
            logger.info("  Debug layout mode: layout report saved by Blender script")
