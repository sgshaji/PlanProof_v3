"""Gemini vision client and OpenAI-compatible adapter.

Provides two public types:

* ``GeminiClient`` — thin wrapper around google-genai for direct use.
* ``GeminiVisionAdapter`` — drop-in replacement for an OpenAI client that
  translates ``chat.completions.create()`` calls into Gemini API calls.
  VisionExtractor and VLMSpatialExtractor accept ``Any`` as their client,
  so passing an adapter requires no changes to those classes.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any


class GeminiClient:
    """Thin wrapper around google-genai for text and vision completions.

    Parameters
    ----------
    api_key:
        Gemini API key (from Google AI Studio).
    model:
        Gemini model ID, e.g. ``"gemini-2.0-flash"``.
    """

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        from google import genai
        from google.genai import types as _types  # noqa: F401

        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._genai = genai

    def complete(self, prompt: str) -> str:
        """Send a text-only prompt and return the response text."""
        from google.genai import types

        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0),
        )
        return response.text or ""

    def complete_with_image(self, prompt: str, image_path: Path) -> str:
        """Send a text + image prompt and return the response text.

        Parameters
        ----------
        prompt:
            The text portion of the request.
        image_path:
            Path to the image file (PNG / JPEG / TIFF).
        """
        from google.genai import types

        image_bytes = image_path.read_bytes()
        suffix = image_path.suffix.lower().lstrip(".")
        _mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "tiff": "image/tiff"}
        mime_type = _mime_map.get(suffix, "image/png")

        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        response = self._client.models.generate_content(
            model=self._model,
            contents=[prompt, image_part],
            config=types.GenerateContentConfig(temperature=0),
        )
        return response.text or ""


# ---------------------------------------------------------------------------
# OpenAI-compatible shim
# ---------------------------------------------------------------------------

class _FakeMessage:
    """Mimics openai.types.chat.ChatCompletionMessage."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.role = "assistant"


class _FakeChoice:
    """Mimics openai.types.chat.Choice."""

    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)
        self.finish_reason = "stop"
        self.index = 0


class _FakeCompletion:
    """Mimics openai.types.chat.ChatCompletion."""

    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]
        self.model = ""
        self.id = ""


class GeminiVisionAdapter:
    """Adapts the Gemini API to the OpenAI ``chat.completions.create()`` interface.

    VisionExtractor and VLMSpatialExtractor call:

        response = client.chat.completions.create(
            model=..., messages=[...], temperature=0, max_tokens=4096
        )
        content = response.choices[0].message.content

    This adapter provides exactly that surface, translating the OpenAI message
    format (with base64 ``image_url`` parts) into Gemini ``Part`` objects.

    Parameters
    ----------
    api_key:
        Gemini API key.
    model:
        Gemini model ID. Defaults to ``"gemini-2.0-flash"``.
    """

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        from google import genai

        self._raw_client = genai.Client(api_key=api_key)
        self._model = model
        # Expose openai-compatible attribute chain: self.chat.completions.create
        self.chat = self
        self.completions = self

    # ------------------------------------------------------------------
    # Public interface — called as adapter.chat.completions.create(...)
    # ------------------------------------------------------------------

    def create(
        self,
        *,
        model: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        temperature: float = 0,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> _FakeCompletion:
        """Translate an OpenAI chat request into a Gemini API call."""
        from google.genai import types

        messages = messages or []
        gemini_model = model or self._model

        contents: list[Any] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                # Prepend system message as plain text
                if isinstance(content, str) and content.strip():
                    contents.insert(0, content)
                continue

            # User message — may be str or list of parts
            if isinstance(content, str):
                contents.append(content)
            elif isinstance(content, list):
                for part in content:
                    if part.get("type") == "text":
                        contents.append(part["text"])
                    elif part.get("type") == "image_url":
                        image_part = self._decode_image_url(part["image_url"]["url"], types)
                        if image_part is not None:
                            contents.append(image_part)

        response = self._raw_client.models.generate_content(
            model=gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(temperature=temperature),
        )
        return _FakeCompletion(response.text or "")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_image_url(url: str, types: Any) -> Any | None:
        """Parse a data-URI (base64 image) and return a Gemini Part."""
        # Format: data:<mime_type>;base64,<data>
        match = re.match(r"data:([^;]+);base64,(.+)", url, re.DOTALL)
        if not match:
            return None
        mime_type = match.group(1)
        image_bytes = base64.b64decode(match.group(2))
        return types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
