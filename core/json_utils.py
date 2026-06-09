"""JSON load/save utilities for scene graphs and reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def save_json(data: Any, filepath: str | Path, indent: int = 2) -> Path:
    """Save data as JSON to the given path, creating parent directories as needed.

    Args:
        data: The data to serialize. Pydantic models are converted via .model_dump().
        filepath: Destination file path.
        indent: JSON indentation level.

    Returns:
        The Path to the saved file.
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Support Pydantic models
    if hasattr(data, "model_dump"):
        data = data.model_dump()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False, default=str)

    return path


def load_json(filepath: str | Path) -> dict[str, Any]:
    """Load a JSON file and return its contents as a dictionary.

    Args:
        filepath: Path to the JSON file.

    Returns:
        Parsed JSON as a dictionary.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    path = Path(filepath)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def json_to_str(data: Any, indent: int = 2) -> str:
    """Convert data to a JSON string.

    Args:
        data: The data to serialize.
        indent: JSON indentation level.

    Returns:
        JSON string representation.
    """
    if hasattr(data, "model_dump"):
        data = data.model_dump()
    return json.dumps(data, indent=indent, ensure_ascii=False, default=str)
