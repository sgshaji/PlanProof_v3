"""Tests for the pipeline CLI argument parser.

Only argument parsing is tested here. End-to-end execution is covered
by the integration tests.
"""
from __future__ import annotations

import pytest

from planproof.pipeline.__main__ import _build_parser


class TestArgParser:
    def test_input_required(self) -> None:
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_input_only(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["--input", "data/some_set"])
        assert args.input == "data/some_set"
        assert args.config is None
        assert args.ablation is None
        assert args.output is None
        assert args.markdown is None
        assert args.application_id is None

    def test_all_flags(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([
            "--input", "data/some_set",
            "--config", "configs/custom.yaml",
            "--ablation", "configs/ablation/ablation_b.yaml",
            "--output", "report.json",
            "--markdown", "report.md",
            "--application-id", "APP-42",
        ])
        assert args.input == "data/some_set"
        assert args.config == "configs/custom.yaml"
        assert args.ablation == "configs/ablation/ablation_b.yaml"
        assert args.output == "report.json"
        assert args.markdown == "report.md"
        assert args.application_id == "APP-42"

    def test_application_id_defaults_to_none(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["--input", "data/some_set"])
        assert args.application_id is None
