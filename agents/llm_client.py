"""OpenAI-compatible LLM client wrapper (placeholder for future use).

This module provides a minimal client that will be used when real LLM backends
are integrated. For the MVP, it is not required — the mock backend handles everything.
"""

from __future__ import annotations

import json
import os
from typing import Any


class LLMClient:
    """OpenAI-compatible chat completion client.

    Reads configuration from environment variables:
        LLM_API_BASE: Base URL of the API endpoint.
        LLM_API_KEY: API key for authentication.
        LLM_MODEL: Model name to use.

    This is a placeholder for the MVP. The chat_json method raises NotImplementedError
    until a real backend is configured.
    """

    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_base = api_base or os.getenv("LLM_API_BASE", "")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.model = model or os.getenv("LLM_MODEL", "")

    @property
    def is_configured(self) -> bool:
        """Return True if all required credentials are set."""
        return bool(self.api_base and self.api_key and self.model)

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Send a chat completion request and return the text response.

        Args:
            system_prompt: System-level instruction.
            user_prompt: User message content.

        Returns:
            The model's text response.

        Raises:
            NotImplementedError: In MVP — real implementation coming later.
        """
        if not self.is_configured:
            raise RuntimeError(
                "LLM client is not configured. Set LLM_API_BASE, LLM_API_KEY, "
                "and LLM_MODEL environment variables."
            )
        raise NotImplementedError(
            "Real LLM API calls are not implemented in the MVP. "
            "Use --backend mock instead."
        )

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Send a chat completion request and parse the response as JSON.

        Args:
            system_prompt: System-level instruction.
            user_prompt: User message content.

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            NotImplementedError: In MVP — real implementation coming later.
        """
        response = self.chat(system_prompt, user_prompt)
        # Attempt to extract JSON from markdown code blocks if present
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove opening and closing fences
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        return json.loads(text)
