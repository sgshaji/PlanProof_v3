"""BCC data annotation helper.

Guides the user through annotating ground truth extractions for real BCC
architectural drawing sets. Generates ground_truth.json in the same format
as synthetic data.

Usage::
    python scripts/annotate_bcc.py --data-dir data/anonymised --output-dir data/annotated
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DRAWING_ATTRIBUTES = [
    ("building_height", "metres", "MEASUREMENT"),
    ("rear_garden_depth", "metres", "MEASUREMENT"),
    ("site_coverage", "percent", "MEASUREMENT"),
    ("building_footprint_area", "m²", "MEASUREMENT"),
    ("ridge_height", "metres", "MEASUREMENT"),
    ("eaves_height", "metres", "MEASUREMENT"),
    ("number_of_storeys", "count", "MEASUREMENT"),
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Annotate BCC application sets with ground truth.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/anonymised"), help="BCC data directory.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/annotated"), help="Output directory for annotations.")
    return parser.parse_args()


def list_available_sets(data_dir: Path) -> list[Path]:
    """List all BCC sets with their document counts."""
    sets: list[Path] = []
    for d in sorted(data_dir.iterdir()):
        if d.is_dir():
            docs = list(d.glob("*.pdf")) + list(d.glob("*.png")) + list(d.glob("*.jpg"))
            print(f"  [{len(sets)}] {d.name} ({len(docs)} documents)")
            sets.append(d)
    return sets


def annotate_document(doc_path: Path) -> list[dict]:
    """Interactively annotate one document."""
    print(f"\n  Document: {doc_path.name}")
    print(f"  Path: {doc_path}")
    print(f"  (Open this file to inspect it)")
    print()

    extractions: list[dict] = []

    for attr_name, unit, entity_type in DRAWING_ATTRIBUTES:
        response = input(f"    Is '{attr_name}' visible? (y/n/skip/done): ").strip().lower()

        if response == "done":
            break
        if response != "y":
            continue

        value_str = input(f"    Value of '{attr_name}' (in {unit}): ").strip()
        page_str = input(f"    Page number (default 1): ").strip() or "1"

        try:
            value: str | float = float(value_str)
        except ValueError:
            value = value_str

        extractions.append({
            "attribute": attr_name,
            "value": value,
            "unit": unit,
            "entity_type": entity_type,
            "page": int(page_str),
            "text_rendered": value_str,
            "bounding_box": None,
        })

    return extractions


def annotate_set(bcc_dir: Path, output_dir: Path) -> None:
    """Annotate all documents in one BCC set."""
    set_id = bcc_dir.name
    print(f"\n=== Annotating: {set_id} ===")

    docs = sorted(list(bcc_dir.glob("*.pdf")) + list(bcc_dir.glob("*.png")) + list(bcc_dir.glob("*.jpg")))
    print(f"  Found {len(docs)} documents")

    documents: list[dict] = []

    for doc_path in docs:
        suffix = doc_path.suffix.lower()
        doc_type = "DRAWING"  # BCC sets are drawings-only

        extractions = annotate_document(doc_path)

        documents.append({
            "filename": doc_path.name,
            "doc_type": doc_type,
            "file_format": suffix.lstrip("."),
            "extractions": extractions,
        })

    ground_truth = {
        "set_id": set_id,
        "category": "real_bcc",
        "source": "manual_annotation",
        "annotated_at": datetime.now(timezone.utc).isoformat(),
        "documents": documents,
        "values": [],
        "rule_verdicts": [],
    }

    dest = output_dir / set_id / "ground_truth.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")
    print(f"\n  Saved: {dest}")

    total_extractions = sum(len(d["extractions"]) for d in documents)
    print(f"  Total annotations: {total_extractions}")


def main() -> int:
    args = _parse_args()
    data_dir: Path = args.data_dir
    output_dir: Path = args.output_dir

    if not data_dir.exists():
        print(f"ERROR: data directory does not exist: {data_dir}", file=sys.stderr)
        return 1

    print("Available BCC application sets:")
    available = list_available_sets(data_dir)

    if not available:
        print("No sets found.", file=sys.stderr)
        return 1

    print("\nSelect 3 sets to annotate (enter indices separated by spaces):")
    indices_str = input("> ").strip()
    try:
        indices = [int(x) for x in indices_str.split()][:3]
    except ValueError:
        print("Invalid input. Using first 3 sets.")
        indices = [0, 1, 2]

    selected = [available[i] for i in indices if i < len(available)]
    print(f"\nAnnotating {len(selected)} sets: {[s.name for s in selected]}")

    for bcc_dir in selected:
        annotate_set(bcc_dir, output_dir)

    print("\nDone! Annotated sets saved to:", output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
