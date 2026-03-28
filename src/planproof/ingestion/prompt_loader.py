"""YAML prompt template loading and rendering."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class PromptTemplate(BaseModel):
    """A loaded prompt template with rendering support."""

    system_message: str
    user_message_template: str
    output_schema: dict[str, Any] | None = None
    few_shot_examples: list[dict[str, str]] = []

    model_config = {"from_attributes": True}

    def render(self, **kwargs: str) -> str:
        """Render the full prompt with variable substitution.

        Combines system message, few-shot examples, output schema,
        and the user message with variables substituted.
        """
        parts: list[str] = []

        parts.append(self.system_message)

        if self.output_schema:
            import json

            parts.append(
                f"\nRespond with valid JSON matching this schema:\n"
                f"```json\n{json.dumps(self.output_schema, indent=2)}\n```"
            )

        for example in self.few_shot_examples:
            parts.append(
                f"\nExample input: {example['input']}\n"
                f"Example output: {example['output']}"
            )

        user_msg = self.user_message_template.format(**kwargs)
        parts.append(f"\n{user_msg}")

        return "\n".join(parts)


class PromptLoader:
    """Load YAML prompt templates from a directory."""

    def __init__(self, prompts_dir: Path) -> None:
        self._prompts_dir = prompts_dir

    def load(self, template_name: str) -> PromptTemplate:
        """Load a prompt template by name (without .yaml extension).

        Raises FileNotFoundError if the template file does not exist.
        """
        path = self._prompts_dir / f"{template_name}.yaml"
        if not path.exists():
            msg = f"Prompt template not found: {path}"
            raise FileNotFoundError(msg)

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return PromptTemplate(
            system_message=data["system_message"],
            user_message_template=data["user_message_template"],
            output_schema=data.get("output_schema"),
            few_shot_examples=data.get("few_shot_examples", []),
        )
