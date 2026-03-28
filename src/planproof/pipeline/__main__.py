"""CLI entry point for the PlanProof pipeline.

Usage
-----
    python -m planproof.pipeline --input data/synthetic_diverse/compliant/SET_COMPLIANT_100000
    python -m planproof.pipeline --input <dir> --ablation configs/ablation/ablation_b.yaml
    python -m planproof.pipeline --input <dir> --output report.json --markdown report.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m planproof.pipeline",
        description="Run the PlanProof compliance pipeline against an application set.",
    )
    parser.add_argument(
        "--input",
        required=True,
        metavar="DIR",
        help="Path to the application set directory.",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help="Pipeline config override (YAML). When omitted, env vars / PipelineConfig defaults are used.",
    )
    parser.add_argument(
        "--ablation",
        metavar="PATH",
        default=None,
        help="Ablation config YAML path. Ablation toggles are merged into the active config.",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        default=None,
        help="Write JSON compliance report to this file. When omitted, report is printed to stdout.",
    )
    parser.add_argument(
        "--markdown",
        metavar="PATH",
        default=None,
        help="Write Markdown compliance report to this file.",
    )
    parser.add_argument(
        "--application-id",
        metavar="ID",
        default=None,
        dest="application_id",
        help="Application ID recorded in the report. Defaults to the input directory name.",
    )
    return parser


def _load_config(config_path: str | None) -> dict:
    """Load a YAML config file and return it as a plain dict.

    Returns an empty dict when no path is given.
    """
    if config_path is None:
        return {}

    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        print(
            "ERROR: PyYAML is required for --config / --ablation. "
            "Install it with: pip install pyyaml",
            file=sys.stderr,
        )
        sys.exit(1)

    path = Path(config_path)
    if not path.is_file():
        print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with path.open() as fh:
        data = yaml.safe_load(fh) or {}

    if not isinstance(data, dict):
        print(
            f"ERROR: Config file must be a YAML mapping, got {type(data).__name__}: {config_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    return data


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    input_dir = Path(args.input)
    if not input_dir.is_dir():
        print(f"ERROR: Input directory does not exist: {args.input}", file=sys.stderr)
        sys.exit(1)

    application_id = args.application_id or input_dir.name

    # ------------------------------------------------------------------
    # Build PipelineConfig
    # ------------------------------------------------------------------
    try:
        from planproof.schemas.config import AblationConfig, PipelineConfig

        # Start from env-var / defaults
        config_overrides: dict = _load_config(args.config)
        config = PipelineConfig(**config_overrides) if config_overrides else PipelineConfig()

        # Merge ablation toggles on top
        if args.ablation:
            ablation_data: dict = _load_config(args.ablation)
            # Ablation YAML may have a top-level "ablation" key or be flat
            ablation_section = ablation_data.get("ablation", ablation_data)
            current = config.ablation.model_dump()
            current.update(ablation_section)
            config = config.model_copy(update={"ablation": AblationConfig(**current)})

    except Exception as exc:
        print(f"ERROR: Failed to load configuration: {exc}", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Build pipeline
    # ------------------------------------------------------------------
    try:
        from planproof.bootstrap import build_pipeline

        pipeline = build_pipeline(config)
    except Exception as exc:
        print(f"ERROR: Failed to build pipeline: {exc}", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Run pipeline
    # ------------------------------------------------------------------
    try:
        report = pipeline.run(input_dir=input_dir)
        # Inject the resolved application_id so the report reflects it
        report = report.model_copy(update={"application_id": application_id})
    except Exception as exc:
        print(f"ERROR: Pipeline execution failed: {exc}", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Write outputs
    # ------------------------------------------------------------------
    report_json = report.model_dump_json(indent=2)

    if args.output:
        try:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(report_json, encoding="utf-8")
            print(f"JSON report written to: {output_path}")
        except Exception as exc:
            print(f"ERROR: Failed to write JSON report: {exc}", file=sys.stderr)
            sys.exit(1)

    if args.markdown:
        try:
            from planproof.output.markdown_renderer import MarkdownReportRenderer

            md_path = Path(args.markdown)
            md_path.parent.mkdir(parents=True, exist_ok=True)
            renderer = MarkdownReportRenderer()
            md_content = renderer.render(report)
            md_path.write_text(md_content, encoding="utf-8")
            print(f"Markdown report written to: {md_path}")
        except Exception as exc:
            print(f"ERROR: Failed to write Markdown report: {exc}", file=sys.stderr)
            sys.exit(1)

    if not args.output and not args.markdown:
        from planproof.output.markdown_renderer import MarkdownReportRenderer

        renderer = MarkdownReportRenderer()
        print(renderer.render(report))


if __name__ == "__main__":
    main()
