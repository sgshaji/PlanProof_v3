"""Tests for YAML prompt template loading and rendering."""
from __future__ import annotations

import pytest
from pathlib import Path

from planproof.ingestion.prompt_loader import PromptLoader


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    """Create a temp directory with a sample prompt template."""
    template = tmp_path / "form_extraction.yaml"
    template.write_text(
        "system_message: 'You are a planning document extraction assistant.'\n"
        "user_message_template: 'Extract entities from this text:\\n{text}'\n"
        "output_schema:\n"
        "  type: object\n"
        "  properties:\n"
        "    entities:\n"
        "      type: array\n"
        "few_shot_examples:\n"
        "  - input: 'Height: 7.5m'\n"
        "    output: '[{\"entity_type\": \"MEASUREMENT\", \"value\": 7.5}]'\n"
    )
    return tmp_path


def test_load_template(prompts_dir: Path) -> None:
    loader = PromptLoader(prompts_dir)
    template = loader.load("form_extraction")
    assert template.system_message == "You are a planning document extraction assistant."
    assert "{text}" in template.user_message_template


def test_render_prompt_with_text(prompts_dir: Path) -> None:
    loader = PromptLoader(prompts_dir)
    template = loader.load("form_extraction")
    rendered = template.render(text="Height: 7.5m")
    assert "Height: 7.5m" in rendered
    assert "Extract entities from this text:" in rendered


def test_render_prompt_includes_few_shot(prompts_dir: Path) -> None:
    loader = PromptLoader(prompts_dir)
    template = loader.load("form_extraction")
    rendered = template.render(text="Height: 7.5m")
    assert "MEASUREMENT" in rendered


def test_load_missing_template_raises(prompts_dir: Path) -> None:
    loader = PromptLoader(prompts_dir)
    with pytest.raises(FileNotFoundError):
        loader.load("nonexistent_template")


def test_template_has_output_schema(prompts_dir: Path) -> None:
    loader = PromptLoader(prompts_dir)
    template = loader.load("form_extraction")
    assert template.output_schema is not None
    assert template.output_schema["type"] == "object"
