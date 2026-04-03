"""Auto-annotate real BCC drawing sets using GPT-4o vision.

Processes each document in 3 target BCC sets, sends each page to GPT-4o,
and saves ground_truth.json in data/annotated/<set_id>/.

Usage::
    python scripts/auto_annotate_bcc.py

Set PLANPROOF_OPENAI_API_KEY (or OPENAI_API_KEY) in .env before running.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
DATA_RAW = REPO_ROOT / "data" / "raw"
DATA_OUT = REPO_ROOT / "data" / "annotated"

TARGET_SETS = [
    "2025 07100 PA Validated",
    "2025 00841 PA Held",
    "2025 00867 PA Held",
]

# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

api_key = os.environ.get("PLANPROOF_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
if not api_key:
    print("ERROR: No OpenAI API key found. Set PLANPROOF_OPENAI_API_KEY in .env", file=sys.stderr)
    sys.exit(1)

import openai  # noqa: E402

client = openai.OpenAI(api_key=api_key)

# ---------------------------------------------------------------------------
# PDF to image (page list)
# ---------------------------------------------------------------------------

def _try_pdf2image(pdf_path: Path) -> list[Path] | None:
    """Convert PDF to a list of PNG temp files using pdf2image."""
    try:
        from pdf2image import convert_from_path  # type: ignore
        images = convert_from_path(str(pdf_path), dpi=150)
        tmp_dir = pdf_path.parent / f"_tmp_{pdf_path.stem}"
        tmp_dir.mkdir(exist_ok=True)
        out: list[Path] = []
        for i, img in enumerate(images):
            p = tmp_dir / f"page_{i+1:03d}.png"
            img.save(str(p))
            out.append(p)
        return out
    except Exception:  # noqa: BLE001
        return None


def _try_pymupdf(pdf_path: Path) -> list[Path] | None:
    """Convert PDF to PNG pages using PyMuPDF (fitz)."""
    try:
        import fitz  # type: ignore
        doc = fitz.open(str(pdf_path))
        tmp_dir = pdf_path.parent / f"_tmp_{pdf_path.stem}"
        tmp_dir.mkdir(exist_ok=True)
        out: list[Path] = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            mat = fitz.Matrix(2.0, 2.0)  # 2× zoom ≈ 144 dpi
            pix = page.get_pixmap(matrix=mat)
            p = tmp_dir / f"page_{page_num+1:03d}.png"
            pix.save(str(p))
            out.append(p)
        return out
    except Exception:  # noqa: BLE001
        return None


def _try_pdfplumber_text(pdf_path: Path) -> list[str] | None:
    """Extract text from PDF pages using pdfplumber (text-only fallback)."""
    try:
        import pdfplumber  # type: ignore
        with pdfplumber.open(str(pdf_path)) as pdf:
            pages_text: list[str] = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                pages_text.append(text.strip())
        return pages_text
    except Exception:  # noqa: BLE001
        return None


def rasterise_pdf(pdf_path: Path) -> list[Path] | list[str] | None:
    """Return list of image paths OR list of page texts; None on total failure."""
    result = _try_pdf2image(pdf_path)
    if result:
        return result
    result = _try_pymupdf(pdf_path)
    if result:
        return result
    result = _try_pdfplumber_text(pdf_path)
    if result is not None:
        return result
    return None

# ---------------------------------------------------------------------------
# GPT-4o prompting
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert at reading UK planning application architectural drawings.
Extract ALL measurements and attributes you can identify from the drawing.
Respond ONLY with valid JSON — no markdown fences, no prose.
"""

USER_PROMPT = """\
You are examining a UK planning application architectural drawing.
Extract ALL measurements and attributes you can identify.

For each measurement found, provide:
- attribute name (e.g., building_height, rear_garden_depth, site_coverage,
  ridge_height, eaves_height, number_of_storeys, building_footprint_area)
- value (numeric)
- unit (metres, percent, m², count)
- which page/area of the drawing it appears in

Also identify the drawing type: ELEVATION, FLOOR_PLAN, SITE_PLAN,
LOCATION_PLAN, or OTHER.

Respond with ONLY a JSON object:
{
  "drawing_type": "ELEVATION",
  "extractions": [
    {"attribute": "building_height", "value": 7.5, "unit": "metres"},
    {"attribute": "ridge_height", "value": 8.2, "unit": "metres"}
  ]
}

If you cannot identify any measurements, respond:
{"drawing_type": "OTHER", "extractions": []}
"""


def _encode_image(image_path: Path) -> tuple[str, str]:
    """Base64-encode image; return (b64_string, mime_type)."""
    data = image_path.read_bytes()
    b64 = base64.b64encode(data).decode("utf-8")
    suffix = image_path.suffix.lower().lstrip(".")
    mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}
    mime = mime_map.get(suffix, "image/png")
    return b64, mime


def _call_gpt4o_image(image_path: Path, page_label: str) -> dict:
    """Send one image page to GPT-4o and return parsed JSON dict."""
    b64, mime = _encode_image(image_path)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": USER_PROMPT + f"\n\nThis is {page_label}."},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"},
                },
            ],
        },
    ]
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0,
        max_tokens=2048,
    )
    raw = response.choices[0].message.content or ""
    return _parse_json(raw)


def _call_gpt4o_text(page_text: str, page_label: str) -> dict:
    """Send extracted page text to GPT-4o (text-only fallback)."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                USER_PROMPT
                + f"\n\nThis is {page_label}. The document text content is:\n\n"
                + f"<document_text>\n{page_text}\n</document_text>"
            ),
        },
    ]
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0,
        max_tokens=2048,
    )
    raw = response.choices[0].message.content or ""
    return _parse_json(raw)


def _parse_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON, returning a safe default on error."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1])
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        print(f"    [WARN] JSON parse failed; raw: {raw[:120]!r}")
        return {"drawing_type": "OTHER", "extractions": []}

# ---------------------------------------------------------------------------
# Document processing
# ---------------------------------------------------------------------------

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg"})


def process_document(doc_path: Path) -> dict:
    """Annotate one document (PDF or image) and return the doc record."""
    suffix = doc_path.suffix.lower()
    all_extractions: list[dict] = []
    drawing_types: list[str] = []

    if suffix in IMAGE_EXTENSIONS:
        print(f"    Processing image: {doc_path.name}")
        result = _call_gpt4o_image(doc_path, f"page 1 of {doc_path.name}")
        dt = result.get("drawing_type", "OTHER")
        exts = result.get("extractions", [])
        _tag_page(exts, 1)
        drawing_types.append(dt)
        all_extractions.extend(exts)
        print(f"      drawing_type={dt}, extractions={len(exts)}")

    elif suffix == ".pdf":
        print(f"    Rasterising PDF: {doc_path.name}")
        pages = rasterise_pdf(doc_path)

        if pages is None:
            print(f"    [WARN] Cannot rasterise or read {doc_path.name} — skipping")
            return _make_doc_record(doc_path, "OTHER", [], "skipped")

        is_text = isinstance(pages[0], str)
        mode = "text" if is_text else "image"
        print(f"    Mode: {mode}, pages: {len(pages)}")

        for i, page in enumerate(pages):
            page_label = f"page {i+1} of {doc_path.name}"
            try:
                if is_text:
                    if not page:  # blank page text
                        continue
                    result = _call_gpt4o_text(page, page_label)
                else:
                    result = _call_gpt4o_image(page, page_label)

                dt = result.get("drawing_type", "OTHER")
                exts = result.get("extractions", [])
                _tag_page(exts, i + 1)
                drawing_types.append(dt)
                all_extractions.extend(exts)
                print(f"      page {i+1}: drawing_type={dt}, extractions={len(exts)}")

            except Exception as exc:  # noqa: BLE001
                print(f"      [ERROR] page {i+1}: {exc}")
                traceback.print_exc()

    else:
        print(f"    [SKIP] Unsupported format: {doc_path.name}")
        return _make_doc_record(doc_path, "OTHER", [], "unsupported_format")

    # Dominant drawing type across pages
    final_type = _dominant(drawing_types) if drawing_types else "OTHER"
    return _make_doc_record(doc_path, final_type, all_extractions, "ok")


def _tag_page(extractions: list[dict], page: int) -> None:
    for e in extractions:
        e.setdefault("page", page)
        e.setdefault("entity_type", "MEASUREMENT")
        e.setdefault("bounding_box", None)


def _dominant(items: list[str]) -> str:
    if not items:
        return "OTHER"
    counts: dict[str, int] = {}
    for x in items:
        counts[x] = counts.get(x, 0) + 1
    return max(counts, key=lambda k: counts[k])


def _make_doc_record(doc_path: Path, doc_type: str, extractions: list[dict], status: str) -> dict:
    return {
        "filename": doc_path.name,
        "doc_type": "DRAWING",
        "file_format": doc_path.suffix.lower().lstrip("."),
        "drawing_type": doc_type,
        "status": status,
        "extractions": extractions,
    }

# ---------------------------------------------------------------------------
# Set processing
# ---------------------------------------------------------------------------

def process_set(set_id: str) -> dict:
    """Process all documents in one BCC set and return the GT record."""
    raw_dir = DATA_RAW / set_id
    if not raw_dir.exists():
        print(f"[ERROR] Set directory not found: {raw_dir}")
        return {}

    docs = sorted(
        list(raw_dir.glob("*.pdf"))
        + list(raw_dir.glob("*.png"))
        + list(raw_dir.glob("*.jpg"))
        + list(raw_dir.glob("*.jpeg"))
    )
    # Exclude planning application forms — they rarely contain drawing measurements
    drawings = [d for d in docs if "Forms" not in d.name and "Application_Form" not in d.name]
    forms = [d for d in docs if d not in drawings]

    print(f"\n=== {set_id} ===")
    print(f"  Total docs: {len(docs)}  (drawing candidates: {len(drawings)}, forms skipped: {len(forms)})")

    out_dir = DATA_OUT / set_id
    out_dir.mkdir(parents=True, exist_ok=True)
    interim_path = out_dir / "ground_truth.json"

    # Load any already-saved interim results
    existing_filenames: set[str] = set()
    doc_records: list[dict] = []
    if interim_path.exists():
        try:
            prev = json.loads(interim_path.read_text(encoding="utf-8"))
            doc_records = prev.get("documents", [])
            existing_filenames = {d["filename"] for d in doc_records}
            print(f"  Resuming — {len(existing_filenames)} docs already processed")
        except Exception:  # noqa: BLE001
            pass

    for doc_path in drawings:
        if doc_path.name in existing_filenames:
            print(f"  [SKIP] Already processed: {doc_path.name}")
            continue

        print(f"\n  Processing: {doc_path.name}")
        record = process_document(doc_path)
        doc_records.append(record)

        # Save intermediate result
        ground_truth = _build_gt(set_id, doc_records)
        interim_path.write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")
        print(f"  Saved interim -> {interim_path}")

    return _build_gt(set_id, doc_records)


def _build_gt(set_id: str, doc_records: list[dict]) -> dict:
    return {
        "set_id": set_id,
        "category": "real_bcc",
        "source": "vlm_auto_annotation",
        "annotated_at": datetime.now(timezone.utc).isoformat(),
        "documents": doc_records,
        "values": [],
        "rule_verdicts": [],
    }

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(results: list[dict]) -> None:
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for gt in results:
        if not gt:
            continue
        set_id = gt["set_id"]
        docs = gt.get("documents", [])
        total_ext = sum(len(d.get("extractions", [])) for d in docs)
        print(f"\n{set_id}")
        print(f"  documents: {len(docs)}")
        print(f"  total extractions: {total_ext}")
        for d in docs:
            exts = d.get("extractions", [])
            attrs = [e.get("attribute", "?") for e in exts]
            print(f"    {d['filename'][:60]:60s} [{d.get('drawing_type','?'):12s}] {len(exts):2d} extractions")
            if attrs:
                print(f"      -> {', '.join(attrs[:8])}{'...' if len(attrs) > 8 else ''}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("PlanProof — BCC Auto-Annotation with GPT-4o")
    print(f"Output: {DATA_OUT}")
    print(f"Sets: {TARGET_SETS}")

    results: list[dict] = []
    for set_id in TARGET_SETS:
        gt = process_set(set_id)
        if gt:
            results.append(gt)
            # Final save
            out_path = DATA_OUT / set_id / "ground_truth.json"
            out_path.write_text(json.dumps(gt, indent=2), encoding="utf-8")
            print(f"\nFinal GT saved -> {out_path}")

    print_summary(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
