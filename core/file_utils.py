"""File system utilities for the pipeline."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def ensure_dir(path: str | Path) -> Path:
    """Create a directory if it does not exist.

    Args:
        path: Directory path to ensure.

    Returns:
        Path object for the directory.
    """
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def timestamped_filename(prefix: str, extension: str) -> str:
    """Generate a filename with a timestamp.

    Args:
        prefix: Filename prefix.
        extension: File extension (without dot).

    Returns:
        Timestamped filename string, e.g. 'scene_graph_20260101_120000.json'.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}.{extension}"


def latest_symlink(target: str | Path, link_dir: str | Path, link_name: str) -> Path:
    """Create or update a symlink pointing to the latest version of a file.

    On Windows/WSL this creates a copy instead if symlinks are not supported.

    Args:
        target: Path to the actual file.
        link_dir: Directory where the symlink should be placed.
        link_name: Name of the symlink (e.g. 'latest_scene_graph.json').

    Returns:
        Path to the created link.
    """
    import shutil

    target_path = Path(target).resolve()
    link_path = Path(link_dir) / link_name

    # Remove existing link/file
    if link_path.is_symlink() or link_path.exists():
        link_path.unlink()

    try:
        link_path.symlink_to(target_path)
    except OSError:
        # Fallback: copy the file
        shutil.copy2(target_path, link_path)

    return link_path


def get_project_root() -> Path:
    """Return the project root directory (where main.py lives).

    Returns:
        Absolute path to the project root.
    """
    return Path(__file__).resolve().parent.parent
