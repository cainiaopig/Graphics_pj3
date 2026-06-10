"""LLM client for OpenAI-compatible APIs (Google AI Studio, GLM, OpenAI, etc.).

Supports any OpenAI-compatible chat completions endpoint.
Configured via environment variables or direct parameters.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

# Default to Google AI Studio's OpenAI-compatible endpoint
DEFAULT_API_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULT_MODEL = "gemini-2.5-flash"

# Fallback models (Google AI Studio OpenAI-compatible endpoint names)
FALLBACK_MODELS = ["gemini-2.0-flash-001"]

# Max retries for transient errors (503, 429) and initial delay
MAX_RETRIES = 4
RETRY_DELAY = 8  # seconds base, increases exponentially


class LLMClient:
    """OpenAI-compatible chat completion client.

    Reads configuration from environment variables:
        LLM_API_BASE: Base URL of the API endpoint.
        LLM_API_KEY: API key for authentication.
        LLM_MODEL: Model name to use.

    Defaults to Google AI Studio's free Gemini endpoint.
    """

    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_base = api_base or os.getenv("LLM_API_BASE", DEFAULT_API_BASE)
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)

    @property
    def is_configured(self) -> bool:
        """Return True if all required credentials are set."""
        return bool(self.api_base and self.api_key and self.model)

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        """Send a chat completion request and return the text response.

        Args:
            system_prompt: System-level instruction.
            user_prompt: User message content.
            temperature: Sampling temperature (0.0-2.0). Lower = more deterministic.

        Returns:
            The model's text response.

        Raises:
            RuntimeError: If client is not configured or API call fails.
        """
        if not self.is_configured:
            raise RuntimeError(
                "LLM client is not configured. Set LLM_API_BASE, LLM_API_KEY, "
                "and LLM_MODEL environment variables."
            )

        url = f"{self.api_base.rstrip('/')}/chat/completions"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": 4096,
        }

        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        # Retry loop with fallback models for transient errors
        last_error = None
        models_to_try = [self.model] + [m for m in FALLBACK_MODELS if m != self.model]

        for attempt in range(MAX_RETRIES):
            for try_model in models_to_try:
                payload["model"] = try_model
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")

                try:
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                    # Success — update model if we fell back
                    if try_model != self.model:
                        logger.info("LLM: fell back to model %s", try_model)
                    break  # out of models loop
                except urllib.error.HTTPError as e:
                    error_body = e.read().decode("utf-8") if e.fp else ""
                    last_error = RuntimeError(f"LLM API HTTP {e.code}: {error_body[:500]}")
                    if e.code in (429, 503):
                        logger.warning(
                            "LLM: model=%s HTTP %d (attempt %d/%d), retrying...",
                            try_model, e.code, attempt + 1, MAX_RETRIES,
                        )
                        continue  # try next model
                    # Non-retryable error
                    raise last_error from e
                except urllib.error.URLError as e:
                    last_error = RuntimeError(f"LLM API connection failed: {e.reason}")
                    logger.warning("LLM: connection error (attempt %d/%d), retrying...",
                                   attempt + 1, MAX_RETRIES)
                    continue  # try next model
            else:
                # All models failed this attempt
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_DELAY * (2 ** attempt)  # exponential: 5, 10, 20s
                    logger.info("LLM: all models failed, waiting %ds before retry %d/%d",
                                wait, attempt + 2, MAX_RETRIES)
                    time.sleep(wait)
                    continue
                # Last attempt — all models exhausted
                raise last_error or RuntimeError("LLM API call failed after all retries")
            break  # success — exit retry loop

        # Extract content from OpenAI-compatible response
        choices = body.get("choices", [])
        if not choices:
            raise RuntimeError(f"LLM API returned no choices: {json.dumps(body)[:500]}")

        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise RuntimeError(f"LLM returned empty content. Finish reason: {choices[0].get('finish_reason')}")

        # Log token usage for monitoring
        usage = body.get("usage", {})
        if usage:
            logger.info(
                "LLM tokens: prompt=%d, completion=%d, total=%d",
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
                usage.get("total_tokens", 0),
            )

        return content

    def chat_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> dict[str, Any]:
        """Send a chat completion request and parse the response as JSON.

        Args:
            system_prompt: System-level instruction.
            user_prompt: User message content.
            temperature: Sampling temperature.

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            RuntimeError: If API call fails or response cannot be parsed as JSON.
        """
        response = self.chat(system_prompt, user_prompt, temperature=temperature)
        text = response.strip()

        # --- Step 1: Strip markdown code fences ---
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # --- Step 2: Try parsing directly ---
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # --- Step 3: Repair common LLM JSON mistakes ---
        repaired = self._repair_json(text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as e:
            logger.error("JSON parse failed. Raw (first 1000 chars): %s", text[:1000])
            logger.error("Repaired (first 1000 chars): %s", repaired[:1000])
            raise RuntimeError(
                f"LLM returned invalid JSON: {e}\n"
                f"Raw output (first 500 chars): {text[:500]}"
            ) from e

    @staticmethod
    def _repair_json(text: str) -> str:
        """Attempt to repair common JSON formatting errors from LLM output.

        Handles: trailing commas, single quotes, unescaped newlines in strings,
        missing quotes on keys, and extra text after the JSON object.
        """
        import re

        # Remove trailing commas before ] or }
        text = re.sub(r',\s*([}\]])', r'\1', text)

        # Fix single-quoted keys and values (simple heuristic)
        # Only apply if the JSON looks like it uses single quotes throughout
        if text.count("'") > text.count('"') * 2:
            # Replace single quotes that appear to be JSON quotes
            # This is tricky — we look for patterns like 'key': or : 'value'
            text = re.sub(r"'([^']*)'(\s*:)", r'"\1"\2', text)  # 'key':
            text = re.sub(r"(:\s*)'([^']*)'", r'\1"\2"', text)  # : 'value'

        # Fix missing quotes around keys (e.g., {key: "value"} -> {"key": "value"})
        text = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)', r'\1"\2"\3', text)

        # Find the outermost { } pair and extract just that
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        if first_brace >= 0 and last_brace > first_brace:
            text = text[first_brace:last_brace + 1]

        return text
