# Phase 2a: Document Classifier (M1) + Text Extraction Pipeline (M2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the ingestion layer that classifies planning application documents and extracts structured entities via a two-path router (text path: pdfplumber + Groq, vision path: GPT-4o).

**Architecture:** M1 (rule-based classifier) determines document type and text-layer availability. M2 routes each document through either a text extraction path (pdfplumber → Groq LLM) or a vision extraction path (GPT-4o). Both paths produce `ExtractedEntity` objects stored in `PipelineContext["entities"]`. All LLM calls go through the existing `CachedLLMClient`.

**Tech Stack:** pdfplumber (new dep), openai SDK (vision API), Groq API (text extraction), Pydantic v2 schemas, PyYAML prompt templates.

**Spec:** `docs/superpowers/specs/2026-03-26-phase2a-ingestion-m1-m2-design.md`

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `src/planproof/ingestion/classifier.py` | `RuleBasedClassifier` — filename patterns + text density + image heuristics |
| `src/planproof/ingestion/text_extractor.py` | `PdfPlumberExtractor` — PDF text-layer extraction via pdfplumber |
| `src/planproof/ingestion/entity_extractor.py` | `LLMEntityExtractor` — LLM structured extraction with prompt templates |
| `src/planproof/ingestion/vision_extractor.py` | `VisionExtractor` — GPT-4o image-based extraction |
| `src/planproof/ingestion/rasteriser.py` | `rasterise()` — thin utility for image format handling |
| `src/planproof/ingestion/prompt_loader.py` | `PromptLoader` — load and render YAML prompt templates |
| `configs/classifier_patterns.yaml` | Regex patterns for filename-based classification |
| `configs/prompts/form_extraction.yaml` | Prompt template for FORM documents |
| `configs/prompts/report_extraction.yaml` | Prompt template for REPORT documents |
| `configs/prompts/certificate_extraction.yaml` | Prompt template for CERTIFICATE documents |
| `configs/prompts/drawing_extraction.yaml` | Prompt template for DRAWING documents (vision path) |
| `tests/unit/ingestion/test_classifier.py` | Classifier unit tests |
| `tests/unit/ingestion/test_text_extractor.py` | PdfPlumber extractor unit tests |
| `tests/unit/ingestion/test_entity_extractor.py` | LLM entity extractor unit tests |
| `tests/unit/ingestion/test_vision_extractor.py` | Vision extractor unit tests |
| `tests/unit/ingestion/test_prompt_loader.py` | Prompt loader unit tests |
| `tests/unit/ingestion/test_rasteriser.py` | Rasteriser unit tests |
| `tests/integration/test_ingestion_pipeline.py` | End-to-end ingestion integration tests |
| `tests/fixtures/sample_text_layer.pdf` | Test fixture: PDF with text layer |

### Modified files

| File | Change |
|------|--------|
| `src/planproof/schemas/entities.py` | Add `has_text_layer: bool` to `ClassifiedDocument` |
| `src/planproof/interfaces/pipeline.py` | Add `classified_documents` key to `PipelineContext` |
| `src/planproof/pipeline/steps/classification.py` | Implement `ClassificationStep.execute()` |
| `src/planproof/pipeline/steps/text_extraction.py` | Implement `TextExtractionStep.execute()` with two-path routing |
| `src/planproof/bootstrap.py` | Replace stubs with concrete classifier, OCR, entity extractor factories |
| `src/planproof/ingestion/__init__.py` | Public exports |
| `tests/conftest.py` | Update `sample_classified_doc` fixture with `has_text_layer` |
| `pyproject.toml` | Add `pdfplumber` dependency |

---

## Task 1: Add `pdfplumber` dependency and update schema

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/planproof/schemas/entities.py:82-89`
- Modify: `src/planproof/interfaces/pipeline.py:15-27`
- Modify: `tests/conftest.py:36-42`
- Test: `tests/unit/schemas/test_entities.py` (existing)

- [ ] **Step 1: Add pdfplumber to dependencies**

In `pyproject.toml`, add `pdfplumber` to the main dependencies list:

```toml
dependencies = [
    "pydantic>=2.0",
    "pydantic-settings",
    "structlog",
    "neo4j",
    "openai",
    "pyyaml",
    "requests",
    "groq",
    "reportlab",
    "Pillow",
    "numpy",
    "pdfplumber",
]
```

- [ ] **Step 2: Install updated dependencies**

Run: `pip install -e ".[dev]"`
Expected: pdfplumber installs successfully (pure Python, no build issues)

- [ ] **Step 3: Add `has_text_layer` to ClassifiedDocument**

In `src/planproof/schemas/entities.py`, update `ClassifiedDocument`:

```python
class ClassifiedDocument(BaseModel):
    """A document that has been classified into a known type."""

    file_path: str
    doc_type: DocumentType
    confidence: float = Field(ge=0, le=1)
    has_text_layer: bool = False

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Add `classified_documents` to PipelineContext**

In `src/planproof/interfaces/pipeline.py`, add the import and key:

```python
from planproof.schemas.entities import ClassifiedDocument, ExtractedEntity

class PipelineContext(TypedDict, total=False):
    classified_documents: list[ClassifiedDocument]
    entities: list[ExtractedEntity]
    graph_ref: Any
    verdicts: list[RuleVerdict]
    assessability_results: list[AssessabilityResult]
    metadata: dict[str, Any]
```

- [ ] **Step 5: Update test fixture**

In `tests/conftest.py`, update `sample_classified_doc`:

```python
@pytest.fixture
def sample_classified_doc() -> ClassifiedDocument:
    """A valid ClassifiedDocument for testing."""
    return ClassifiedDocument(
        file_path="test_form.pdf",
        doc_type=DocumentType.FORM,
        confidence=0.95,
        has_text_layer=True,
    )
```

- [ ] **Step 6: Run existing tests to verify no regressions**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All existing tests pass. The `has_text_layer=False` default ensures backward compatibility.

- [ ] **Step 7: Run type checker**

Run: `python -m mypy src/planproof/ --strict`
Expected: 0 errors

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/planproof/schemas/entities.py src/planproof/interfaces/pipeline.py tests/conftest.py
git commit -m "feat: add pdfplumber dep, has_text_layer to ClassifiedDocument, classified_documents to PipelineContext"
```

---

## Task 2: Classifier patterns config and prompt loader

**Files:**
- Create: `configs/classifier_patterns.yaml`
- Create: `src/planproof/ingestion/prompt_loader.py`
- Create: `tests/unit/ingestion/test_prompt_loader.py`

- [ ] **Step 1: Write failing test for prompt loader**

Create `tests/unit/ingestion/test_prompt_loader.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/ingestion/test_prompt_loader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'planproof.ingestion.prompt_loader'`

- [ ] **Step 3: Implement PromptLoader**

Create `src/planproof/ingestion/prompt_loader.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/ingestion/test_prompt_loader.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Create classifier patterns config**

Create `configs/classifier_patterns.yaml`:

```yaml
# Document classification patterns — regex-based filename matching.
# Each pattern maps to a DocumentType. Patterns are evaluated in order;
# first match wins. Add new patterns here to classify new document types.
patterns:
  - pattern: "(?i)(form|application)"
    doc_type: FORM
    confidence: 0.90
  - pattern: "(?i)(elevation|section)"
    doc_type: DRAWING
    confidence: 0.90
  - pattern: "(?i)(site.?plan|block.?plan)"
    doc_type: DRAWING
    confidence: 0.90
  - pattern: "(?i)(floor.?plan)"
    doc_type: DRAWING
    confidence: 0.90
  - pattern: "(?i)(certificate|lawful)"
    doc_type: CERTIFICATE
    confidence: 0.90
  - pattern: "(?i)(report|statement|assessment)"
    doc_type: REPORT
    confidence: 0.85

# Text density thresholds (characters per page)
text_density:
  high_threshold: 200    # Above → FORM or REPORT
  low_threshold: 50      # Below → likely DRAWING

# Image heuristic thresholds
image_heuristics:
  landscape_ratio: 1.2   # width/height > this → landscape → DRAWING
```

- [ ] **Step 6: Run type checker**

Run: `python -m mypy src/planproof/ingestion/prompt_loader.py --strict`
Expected: 0 errors

- [ ] **Step 7: Commit**

```bash
git add configs/classifier_patterns.yaml src/planproof/ingestion/prompt_loader.py tests/unit/ingestion/test_prompt_loader.py
git commit -m "feat: add prompt loader and classifier patterns config"
```

---

## Task 3: RuleBasedClassifier (M1)

**Files:**
- Create: `src/planproof/ingestion/classifier.py`
- Create: `tests/unit/ingestion/test_classifier.py`
- Create: `tests/fixtures/sample_text_layer.pdf`

- [ ] **Step 1: Write failing tests for classifier**

Create `tests/unit/ingestion/test_classifier.py`:

```python
"""Tests for RuleBasedClassifier."""
from __future__ import annotations

from pathlib import Path

import pytest

from planproof.ingestion.classifier import RuleBasedClassifier
from planproof.schemas.entities import DocumentType


@pytest.fixture
def classifier() -> RuleBasedClassifier:
    """Classifier using the project's default patterns."""
    patterns_path = Path("configs/classifier_patterns.yaml")
    return RuleBasedClassifier(patterns_path=patterns_path)


class TestFilenamePatterns:
    """Signal 1: filename pattern matching."""

    def test_form_filename(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(Path("test_data/FORM.pdf"))
        assert result.doc_type == DocumentType.FORM
        assert result.confidence >= 0.85

    def test_application_filename(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(Path("test_data/planning_application.pdf"))
        assert result.doc_type == DocumentType.FORM

    def test_elevation_filename(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(Path("test_data/elevation_drawing.png"))
        assert result.doc_type == DocumentType.DRAWING

    def test_site_plan_filename(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(Path("test_data/site_plan.pdf"))
        assert result.doc_type == DocumentType.DRAWING

    def test_floor_plan_filename(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(Path("test_data/floor_plan_2.pdf"))
        assert result.doc_type == DocumentType.DRAWING

    def test_certificate_filename(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(Path("test_data/certificate_a.pdf"))
        assert result.doc_type == DocumentType.CERTIFICATE

    def test_report_filename(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(Path("test_data/design_statement.pdf"))
        assert result.doc_type == DocumentType.REPORT

    def test_unknown_filename(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(Path("test_data/random_file.pdf"))
        assert result.doc_type == DocumentType.OTHER
        assert result.confidence <= 0.60


class TestTextLayerDetection:
    """Signal 2: text density heuristic."""

    def test_image_file_has_no_text_layer(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(Path("test_data/elevation.png"))
        assert result.has_text_layer is False

    def test_pdf_with_text_layer(
        self, classifier: RuleBasedClassifier, tmp_path: Path
    ) -> None:
        """PDF created with reportlab has a text layer."""
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        pdf_path = tmp_path / "text_form.pdf"
        c = canvas.Canvas(str(pdf_path), pagesize=A4)
        c.drawString(100, 700, "Application for Planning Permission")
        c.drawString(100, 680, "Site Address: 123 Test Street, Bristol, BS1 1AA")
        c.drawString(100, 660, "Building Height: 7.5m")
        c.save()

        result = classifier.classify(pdf_path)
        assert result.has_text_layer is True


class TestSyntheticDataClassification:
    """Verify classifier works on actual synthetic data filenames."""

    def test_synthetic_form(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(
            Path("data/synthetic/compliant/SET_COMPLIANT_42000/SET_COMPLIANT_42000-compliant-FORM.pdf")
        )
        assert result.doc_type == DocumentType.FORM

    def test_synthetic_site_plan(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(
            Path("data/synthetic/compliant/SET_COMPLIANT_42000/SET_COMPLIANT_42000-compliant-SITE_PLAN_1.pdf")
        )
        assert result.doc_type == DocumentType.DRAWING

    def test_synthetic_elevation(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(
            Path("data/synthetic/compliant/SET_COMPLIANT_42000/SET_COMPLIANT_42000-compliant-ELEVATION_3.png")
        )
        assert result.doc_type == DocumentType.DRAWING

    def test_synthetic_floor_plan(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(
            Path("data/synthetic/compliant/SET_COMPLIANT_42000/SET_COMPLIANT_42000-compliant-FLOOR_PLAN_2.pdf")
        )
        assert result.doc_type == DocumentType.DRAWING

    def test_synthetic_scan_is_no_text_layer(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(
            Path("data/synthetic/compliant/SET_COMPLIANT_42000/SET_COMPLIANT_42000-compliant-FORM_scan.png")
        )
        assert result.has_text_layer is False


class TestConfidenceBoosting:
    """Multiple signals agreeing should boost confidence."""

    def test_filename_match_gives_high_confidence(
        self, classifier: RuleBasedClassifier
    ) -> None:
        result = classifier.classify(Path("test_data/FORM.pdf"))
        assert result.confidence >= 0.85

    def test_no_match_gives_low_confidence(
        self, classifier: RuleBasedClassifier
    ) -> None:
        result = classifier.classify(Path("test_data/mystery.xyz"))
        assert result.confidence <= 0.60
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/ingestion/test_classifier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'planproof.ingestion.classifier'`

- [ ] **Step 3: Implement RuleBasedClassifier**

Create `src/planproof/ingestion/classifier.py`:

```python
"""Rule-based document classifier (M1).

Three-signal cascade: filename patterns → text density → image heuristics.
No LLM involvement — intentionally simple.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from PIL import Image

from planproof.infrastructure.logging import get_logger
from planproof.schemas.entities import ClassifiedDocument, DocumentType

logger = get_logger(__name__)

# File extensions considered images (no text layer by definition)
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"})


class RuleBasedClassifier:
    """Classify documents using filename patterns, text density, and image heuristics.

    Implements the ``DocumentClassifier`` Protocol.
    """

    def __init__(self, patterns_path: Path) -> None:
        with open(patterns_path, encoding="utf-8") as f:
            config: dict[str, Any] = yaml.safe_load(f)

        self._patterns: list[dict[str, Any]] = config.get("patterns", [])
        td = config.get("text_density", {})
        self._high_threshold: int = td.get("high_threshold", 200)
        self._low_threshold: int = td.get("low_threshold", 50)
        ih = config.get("image_heuristics", {})
        self._landscape_ratio: float = ih.get("landscape_ratio", 1.2)

    def classify(self, file_path: Path) -> ClassifiedDocument:
        """Classify a single document file.

        Parameters
        ----------
        file_path:
            Path to the document file (PDF, PNG, JPG, etc.)

        Returns
        -------
        ClassifiedDocument:
            Classification result with doc_type, confidence, has_text_layer.
        """
        filename = file_path.name
        suffix = file_path.suffix.lower()
        is_image = suffix in IMAGE_EXTENSIONS

        # Signal 1: filename pattern matching
        pattern_match = self._match_filename(filename)

        # Signal 2: text density (PDF only)
        has_text_layer = False
        text_density_type: DocumentType | None = None
        if not is_image and suffix == ".pdf" and file_path.exists():
            has_text_layer, text_density_type = self._check_text_density(file_path)

        # Signal 3: image heuristics (fallback for images with no filename match)
        image_type: DocumentType | None = None
        if is_image and pattern_match is None and file_path.exists():
            image_type = self._check_image_heuristics(file_path)

        # Combine signals into final classification
        doc_type, confidence = self._combine_signals(
            pattern_match=pattern_match,
            text_density_type=text_density_type,
            image_type=image_type,
            has_text_layer=has_text_layer,
        )

        logger.info(
            "document_classified",
            file=filename,
            doc_type=doc_type.value,
            confidence=round(confidence, 2),
            has_text_layer=has_text_layer,
        )

        return ClassifiedDocument(
            file_path=str(file_path),
            doc_type=doc_type,
            confidence=confidence,
            has_text_layer=has_text_layer,
        )

    def _match_filename(
        self, filename: str
    ) -> tuple[DocumentType, float] | None:
        """Try to match filename against configured regex patterns."""
        for entry in self._patterns:
            if re.search(entry["pattern"], filename):
                return DocumentType(entry["doc_type"]), float(entry["confidence"])
        return None

    def _check_text_density(
        self, pdf_path: Path
    ) -> tuple[bool, DocumentType | None]:
        """Check PDF text layer density using pdfplumber.

        Returns (has_text_layer, inferred_doc_type).
        """
        try:
            import pdfplumber

            with pdfplumber.open(pdf_path) as pdf:
                total_chars = 0
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    total_chars += len(text)

                if not pdf.pages:
                    return False, None

                avg_chars = total_chars / len(pdf.pages)

            if avg_chars == 0:
                return False, None
            if avg_chars >= self._high_threshold:
                return True, DocumentType.FORM
            if avg_chars < self._low_threshold:
                return True, DocumentType.DRAWING
            return True, None

        except Exception:
            logger.warning("pdfplumber_failed", path=str(pdf_path))
            return False, None

    def _check_image_heuristics(self, image_path: Path) -> DocumentType | None:
        """Use aspect ratio to guess document type for image files."""
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                ratio = width / height if height > 0 else 1.0

            if ratio > self._landscape_ratio:
                return DocumentType.DRAWING
            return None

        except Exception:
            logger.warning("image_heuristic_failed", path=str(image_path))
            return None

    def _combine_signals(
        self,
        pattern_match: tuple[DocumentType, float] | None,
        text_density_type: DocumentType | None,
        image_type: DocumentType | None,
        has_text_layer: bool,
    ) -> tuple[DocumentType, float]:
        """Combine classification signals into final (doc_type, confidence)."""
        if pattern_match is not None:
            doc_type, base_conf = pattern_match

            # Boost if text density agrees
            if text_density_type is not None and text_density_type == doc_type:
                return doc_type, min(base_conf + 0.05, 1.0)

            return doc_type, base_conf

        # No filename match — try text density
        if text_density_type is not None:
            return text_density_type, 0.75

        # No filename or text density — try image heuristics
        if image_type is not None:
            return image_type, 0.65

        # Nothing matched
        return DocumentType.OTHER, 0.50
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/ingestion/test_classifier.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run type checker**

Run: `python -m mypy src/planproof/ingestion/classifier.py --strict`
Expected: 0 errors

- [ ] **Step 6: Commit**

```bash
git add src/planproof/ingestion/classifier.py tests/unit/ingestion/test_classifier.py
git commit -m "feat(M1): add RuleBasedClassifier with filename, text density, image heuristics"
```

---

## Task 4: PdfPlumber text extractor

**Files:**
- Create: `src/planproof/ingestion/text_extractor.py`
- Create: `tests/unit/ingestion/test_text_extractor.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/ingestion/test_text_extractor.py`:

```python
"""Tests for PdfPlumberExtractor."""
from __future__ import annotations

from pathlib import Path

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from planproof.ingestion.text_extractor import PdfPlumberExtractor


@pytest.fixture
def text_pdf(tmp_path: Path) -> Path:
    """Create a multi-page PDF with known text content."""
    pdf_path = tmp_path / "test_form.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=A4)

    # Page 1
    c.drawString(100, 700, "Application for Planning Permission")
    c.drawString(100, 680, "Site Address: 123 Test Street, Bristol, BS1 1AA")
    c.showPage()

    # Page 2
    c.drawString(100, 700, "Building Height: 7.5m")
    c.drawString(100, 680, "Rear Garden Depth: 12.0m")
    c.showPage()

    c.save()
    return pdf_path


@pytest.fixture
def extractor() -> PdfPlumberExtractor:
    return PdfPlumberExtractor()


class TestPdfPlumberExtractor:
    def test_extracts_text_from_pdf(
        self, extractor: PdfPlumberExtractor, text_pdf: Path
    ) -> None:
        result = extractor.extract_text(text_pdf)
        assert "Planning Permission" in result.text
        assert "123 Test Street" in result.text

    def test_preserves_page_numbers(
        self, extractor: PdfPlumberExtractor, text_pdf: Path
    ) -> None:
        result = extractor.extract_text(text_pdf)
        assert result.source_pages == [1, 2]

    def test_source_document_is_set(
        self, extractor: PdfPlumberExtractor, text_pdf: Path
    ) -> None:
        result = extractor.extract_text(text_pdf)
        assert result.source_document == str(text_pdf)

    def test_extraction_method_is_pdfplumber(
        self, extractor: PdfPlumberExtractor, text_pdf: Path
    ) -> None:
        result = extractor.extract_text(text_pdf)
        assert result.extraction_method == "PDFPLUMBER"

    def test_second_page_content(
        self, extractor: PdfPlumberExtractor, text_pdf: Path
    ) -> None:
        result = extractor.extract_text(text_pdf)
        assert "7.5m" in result.text
        assert "12.0m" in result.text

    def test_nonexistent_file_raises(self, extractor: PdfPlumberExtractor) -> None:
        with pytest.raises(FileNotFoundError):
            extractor.extract_text(Path("/nonexistent/file.pdf"))

    def test_empty_pdf(
        self, extractor: PdfPlumberExtractor, tmp_path: Path
    ) -> None:
        """PDF with no text content returns empty text."""
        pdf_path = tmp_path / "empty.pdf"
        c = canvas.Canvas(str(pdf_path), pagesize=A4)
        c.showPage()
        c.save()

        result = extractor.extract_text(pdf_path)
        assert result.text.strip() == ""
        assert result.source_pages == [1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/ingestion/test_text_extractor.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement PdfPlumberExtractor**

Create `src/planproof/ingestion/text_extractor.py`:

```python
"""PDF text extraction via pdfplumber.

Implements the ``OCRExtractor`` Protocol — extracts raw text from
text-layer PDFs, preserving page boundaries.
"""
from __future__ import annotations

from pathlib import Path

import pdfplumber

from planproof.infrastructure.logging import get_logger
from planproof.schemas.entities import RawTextResult

logger = get_logger(__name__)


class PdfPlumberExtractor:
    """Extract text from PDFs using pdfplumber.

    Implements the ``OCRExtractor`` Protocol.
    """

    def extract_text(self, document: Path) -> RawTextResult:
        """Extract text from all pages of a PDF.

        Parameters
        ----------
        document:
            Path to a PDF file with an extractable text layer.

        Returns
        -------
        RawTextResult:
            Concatenated text from all pages with page tracking.

        Raises
        ------
        FileNotFoundError:
            If the document path does not exist.
        """
        if not document.exists():
            msg = f"Document not found: {document}"
            raise FileNotFoundError(msg)

        page_texts: list[str] = []
        page_numbers: list[int] = []

        with pdfplumber.open(document) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                page_texts.append(text)
                page_numbers.append(i)

        full_text = "\n\n".join(page_texts)

        logger.info(
            "text_extracted",
            document=str(document),
            pages=len(page_numbers),
            chars=len(full_text),
        )

        return RawTextResult(
            text=full_text,
            source_document=str(document),
            source_pages=page_numbers,
            extraction_method="PDFPLUMBER",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/ingestion/test_text_extractor.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Run type checker**

Run: `python -m mypy src/planproof/ingestion/text_extractor.py --strict`
Expected: 0 errors

- [ ] **Step 6: Commit**

```bash
git add src/planproof/ingestion/text_extractor.py tests/unit/ingestion/test_text_extractor.py
git commit -m "feat(M2): add PdfPlumberExtractor for text-layer PDF extraction"
```

---

## Task 5: LLM entity extractor

**Files:**
- Create: `src/planproof/ingestion/entity_extractor.py`
- Create: `tests/unit/ingestion/test_entity_extractor.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/ingestion/test_entity_extractor.py`:

```python
"""Tests for LLMEntityExtractor."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from planproof.ingestion.entity_extractor import LLMEntityExtractor
from planproof.schemas.entities import (
    DocumentType,
    EntityType,
    ExtractionMethod,
    RawTextResult,
)


def _make_raw_text(text: str = "Height: 7.5m") -> RawTextResult:
    return RawTextResult(
        text=text,
        source_document="test.pdf",
        source_pages=[1],
        extraction_method="PDFPLUMBER",
    )


def _mock_llm_response() -> str:
    """Return a valid JSON response matching the expected extraction schema."""
    return json.dumps({
        "entities": [
            {
                "entity_type": "MEASUREMENT",
                "attribute": "building_height",
                "value": 7.5,
                "unit": "metres",
                "source_page": 1,
            },
            {
                "entity_type": "ADDRESS",
                "attribute": "site_address",
                "value": "123 Test Street, Bristol, BS1 1AA",
                "unit": None,
                "source_page": 1,
            },
        ]
    })


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    """Create prompt templates for testing."""
    form_template = tmp_path / "form_extraction.yaml"
    form_template.write_text(
        "system_message: 'Extract structured entities from planning documents.'\n"
        "user_message_template: 'Extract all entities from:\\n{text}'\n"
        "output_schema:\n"
        "  type: object\n"
        "  properties:\n"
        "    entities:\n"
        "      type: array\n"
        "few_shot_examples: []\n"
    )
    return tmp_path


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.complete.return_value = _mock_llm_response()
    return llm


@pytest.fixture
def extractor(prompts_dir: Path, mock_llm: MagicMock) -> LLMEntityExtractor:
    return LLMEntityExtractor(
        llm=mock_llm,
        prompts_dir=prompts_dir,
        model="llama-3.1-70b-versatile",
    )


class TestLLMEntityExtractor:
    def test_extracts_entities_from_text(
        self, extractor: LLMEntityExtractor
    ) -> None:
        raw = _make_raw_text("Height: 7.5m\nAddress: 123 Test Street")
        entities = extractor.extract_entities(raw)
        assert len(entities) == 2

    def test_entity_types_correct(
        self, extractor: LLMEntityExtractor
    ) -> None:
        raw = _make_raw_text()
        entities = extractor.extract_entities(raw)
        types = {e.entity_type for e in entities}
        assert EntityType.MEASUREMENT in types
        assert EntityType.ADDRESS in types

    def test_extraction_method_is_ocr_llm(
        self, extractor: LLMEntityExtractor
    ) -> None:
        raw = _make_raw_text()
        entities = extractor.extract_entities(raw)
        for entity in entities:
            assert entity.extraction_method == ExtractionMethod.OCR_LLM

    def test_source_document_propagated(
        self, extractor: LLMEntityExtractor
    ) -> None:
        raw = _make_raw_text()
        entities = extractor.extract_entities(raw)
        for entity in entities:
            assert entity.source_document == "test.pdf"

    def test_confidence_assigned_from_defaults(
        self, extractor: LLMEntityExtractor
    ) -> None:
        raw = _make_raw_text()
        entities = extractor.extract_entities(raw)
        for entity in entities:
            assert 0.0 < entity.confidence <= 1.0

    def test_llm_called_with_rendered_prompt(
        self, extractor: LLMEntityExtractor, mock_llm: MagicMock
    ) -> None:
        raw = _make_raw_text("Height: 7.5m")
        extractor.extract_entities(raw)
        mock_llm.complete.assert_called_once()
        call_args = mock_llm.complete.call_args
        assert "7.5m" in call_args[1].get("prompt", call_args[0][0])

    def test_malformed_json_returns_empty(
        self, prompts_dir: Path
    ) -> None:
        bad_llm = MagicMock()
        bad_llm.complete.return_value = "not valid json {{"
        extractor = LLMEntityExtractor(
            llm=bad_llm, prompts_dir=prompts_dir, model="test"
        )
        raw = _make_raw_text()
        entities = extractor.extract_entities(raw)
        assert entities == []

    def test_empty_entities_list_is_valid(
        self, prompts_dir: Path
    ) -> None:
        empty_llm = MagicMock()
        empty_llm.complete.return_value = json.dumps({"entities": []})
        extractor = LLMEntityExtractor(
            llm=empty_llm, prompts_dir=prompts_dir, model="test"
        )
        raw = _make_raw_text()
        entities = extractor.extract_entities(raw)
        assert entities == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/ingestion/test_entity_extractor.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement LLMEntityExtractor**

Create `src/planproof/ingestion/entity_extractor.py`:

```python
"""LLM-based structured entity extraction from raw text.

Implements the ``EntityExtractor`` Protocol — takes raw text and produces
structured ``ExtractedEntity`` objects via LLM with prompt templates.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from planproof.infrastructure.logging import get_logger
from planproof.ingestion.prompt_loader import PromptLoader
from planproof.schemas.entities import (
    EntityType,
    ExtractedEntity,
    ExtractionMethod,
    RawTextResult,
)

logger = get_logger(__name__)

# Default confidence scores by entity type for OCR_LLM extraction.
# These are pre-calibration defaults — calibrated in Phase 2 checkpoint.
DEFAULT_CONFIDENCE: dict[str, float] = {
    "ADDRESS": 0.85,
    "MEASUREMENT": 0.80,
    "CERTIFICATE": 0.90,
    "BOUNDARY": 0.75,
    "ZONE": 0.85,
    "OWNERSHIP": 0.80,
}

# Map from doc_type to prompt template name
DOC_TYPE_TO_TEMPLATE: dict[str, str] = {
    "FORM": "form_extraction",
    "REPORT": "report_extraction",
    "CERTIFICATE": "certificate_extraction",
    "DRAWING": "drawing_extraction",
}


class LLMEntityExtractor:
    """Extract structured entities from raw text via LLM.

    Implements the ``EntityExtractor`` Protocol.
    """

    def __init__(
        self,
        llm: Any,  # CachedLLMClient or any LLMClient Protocol
        prompts_dir: Path,
        model: str = "llama-3.1-70b-versatile",
        doc_type: str = "FORM",
    ) -> None:
        self._llm = llm
        self._loader = PromptLoader(prompts_dir)
        self._model = model
        self._doc_type = doc_type

    def extract_entities(
        self, text: RawTextResult, doc_type: str | None = None
    ) -> list[ExtractedEntity]:
        """Extract structured entities from raw text via LLM.

        Parameters
        ----------
        text:
            Raw text result from OCR/pdfplumber extraction.
        doc_type:
            Override document type for template selection.
            Defaults to the instance's configured doc_type.

        Returns
        -------
        list[ExtractedEntity]:
            Extracted entities with confidence scores. Empty list if
            LLM response is malformed or contains no entities.
        """
        effective_type = doc_type or self._doc_type
        template_name = DOC_TYPE_TO_TEMPLATE.get(effective_type, "form_extraction")

        try:
            template = self._loader.load(template_name)
        except FileNotFoundError:
            logger.warning(
                "prompt_template_missing",
                template=template_name,
                fallback="form_extraction",
            )
            template = self._loader.load("form_extraction")

        prompt = template.render(text=text.text)
        doc_hash = hashlib.sha256(text.text.encode("utf-8")).hexdigest()

        try:
            response = self._llm.complete(
                prompt=prompt, model=self._model, doc_hash=doc_hash
            )
        except Exception as e:
            logger.error("llm_call_failed", error=str(e))
            return []

        return self._parse_response(response, text)

    def _parse_response(
        self, response: str, source: RawTextResult
    ) -> list[ExtractedEntity]:
        """Parse LLM JSON response into ExtractedEntity objects."""
        try:
            # Strip markdown code fences if present
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1])

            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(
                "llm_json_parse_failed",
                error=str(e),
                response_preview=response[:200],
            )
            return []

        raw_entities: list[dict[str, Any]] = data.get("entities", [])
        entities: list[ExtractedEntity] = []
        now = datetime.now(UTC)

        for raw in raw_entities:
            try:
                entity_type_str = raw.get("entity_type", "")
                entity_type = EntityType(entity_type_str)
                confidence = DEFAULT_CONFIDENCE.get(entity_type_str, 0.70)

                entity = ExtractedEntity(
                    entity_type=entity_type,
                    value=raw.get("value"),
                    unit=raw.get("unit"),
                    confidence=confidence,
                    source_document=source.source_document,
                    source_page=raw.get("source_page"),
                    source_region=None,
                    extraction_method=ExtractionMethod.OCR_LLM,
                    timestamp=now,
                )
                entities.append(entity)
            except (ValueError, KeyError) as e:
                logger.warning(
                    "entity_parse_skipped",
                    error=str(e),
                    raw=raw,
                )
                continue

        logger.info(
            "entities_extracted",
            count=len(entities),
            source=source.source_document,
        )
        return entities
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/ingestion/test_entity_extractor.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Run type checker**

Run: `python -m mypy src/planproof/ingestion/entity_extractor.py --strict`
Expected: 0 errors

- [ ] **Step 6: Commit**

```bash
git add src/planproof/ingestion/entity_extractor.py tests/unit/ingestion/test_entity_extractor.py
git commit -m "feat(M2): add LLMEntityExtractor with prompt templates and JSON parsing"
```

---

## Task 6: Vision extractor and rasteriser

**Files:**
- Create: `src/planproof/ingestion/vision_extractor.py`
- Create: `src/planproof/ingestion/rasteriser.py`
- Create: `tests/unit/ingestion/test_vision_extractor.py`
- Create: `tests/unit/ingestion/test_rasteriser.py`

- [ ] **Step 1: Write failing tests for rasteriser**

Create `tests/unit/ingestion/test_rasteriser.py`:

```python
"""Tests for image rasterisation utility."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from planproof.ingestion.rasteriser import load_image, is_image_file


@pytest.fixture
def png_file(tmp_path: Path) -> Path:
    """Create a test PNG image."""
    img = Image.new("RGB", (200, 100), color="white")
    path = tmp_path / "test.png"
    img.save(path)
    return path


@pytest.fixture
def jpg_file(tmp_path: Path) -> Path:
    """Create a test JPEG image."""
    img = Image.new("RGB", (200, 100), color="white")
    path = tmp_path / "test.jpg"
    img.save(path)
    return path


def test_load_png_returns_image(png_file: Path) -> None:
    img = load_image(png_file)
    assert img is not None
    assert img.size == (200, 100)


def test_load_jpg_returns_image(jpg_file: Path) -> None:
    img = load_image(jpg_file)
    assert img is not None


def test_load_nonexistent_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_image(Path("/nonexistent.png"))


def test_is_image_file_png(png_file: Path) -> None:
    assert is_image_file(png_file) is True


def test_is_image_file_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    assert is_image_file(pdf) is False


def test_is_image_file_nonexistent() -> None:
    assert is_image_file(Path("/nonexistent.xyz")) is False
```

- [ ] **Step 2: Run rasteriser tests to verify they fail**

Run: `python -m pytest tests/unit/ingestion/test_rasteriser.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement rasteriser**

Create `src/planproof/ingestion/rasteriser.py`:

```python
"""Image loading and rasterisation utility.

Thin wrapper around Pillow for image format handling. PDF rasterisation
is deferred until pymupdf is available — for now, synthetic data provides
pre-rendered _scan.png variants.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"})


def is_image_file(path: Path) -> bool:
    """Check if a file path has an image extension."""
    return path.suffix.lower() in IMAGE_EXTENSIONS


def load_image(path: Path) -> Image.Image:
    """Load an image file and return a PIL Image.

    Raises FileNotFoundError if path does not exist.
    """
    if not path.exists():
        msg = f"Image not found: {path}"
        raise FileNotFoundError(msg)
    return Image.open(path)
```

- [ ] **Step 4: Run rasteriser tests to verify they pass**

Run: `python -m pytest tests/unit/ingestion/test_rasteriser.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Write failing tests for vision extractor**

Create `tests/unit/ingestion/test_vision_extractor.py`:

```python
"""Tests for VisionExtractor (GPT-4o image-based extraction)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from planproof.ingestion.vision_extractor import VisionExtractor
from planproof.schemas.entities import EntityType, ExtractionMethod


def _mock_vision_response() -> str:
    return json.dumps({
        "entities": [
            {
                "entity_type": "MEASUREMENT",
                "attribute": "building_height",
                "value": 7.5,
                "unit": "metres",
                "source_page": 1,
            }
        ]
    })


@pytest.fixture
def test_image(tmp_path: Path) -> Path:
    """Create a test PNG image."""
    img = Image.new("RGB", (800, 600), color="white")
    path = tmp_path / "elevation.png"
    img.save(path)
    return path


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    """Create a drawing extraction prompt template."""
    template = tmp_path / "prompts" / "drawing_extraction.yaml"
    template.parent.mkdir(parents=True, exist_ok=True)
    template.write_text(
        "system_message: 'Extract measurements from architectural drawings.'\n"
        "user_message_template: 'Analyze this drawing and extract entities.'\n"
        "output_schema:\n"
        "  type: object\n"
        "few_shot_examples: []\n"
    )
    return template.parent


@pytest.fixture
def mock_openai_client() -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = _mock_vision_response()
    client.chat.completions.create.return_value = response
    return client


@pytest.fixture
def extractor(
    prompts_dir: Path, mock_openai_client: MagicMock
) -> VisionExtractor:
    return VisionExtractor(
        openai_client=mock_openai_client,
        prompts_dir=prompts_dir,
        model="gpt-4o",
    )


class TestVisionExtractor:
    def test_extracts_entities_from_image(
        self, extractor: VisionExtractor, test_image: Path
    ) -> None:
        entities = extractor.extract_from_image(test_image, doc_type="DRAWING")
        assert len(entities) == 1
        assert entities[0].entity_type == EntityType.MEASUREMENT

    def test_extraction_method_is_ocr_llm(
        self, extractor: VisionExtractor, test_image: Path
    ) -> None:
        entities = extractor.extract_from_image(test_image, doc_type="DRAWING")
        assert entities[0].extraction_method == ExtractionMethod.OCR_LLM

    def test_source_document_set(
        self, extractor: VisionExtractor, test_image: Path
    ) -> None:
        entities = extractor.extract_from_image(test_image, doc_type="DRAWING")
        assert entities[0].source_document == str(test_image)

    def test_openai_called_with_image(
        self, extractor: VisionExtractor, test_image: Path,
        mock_openai_client: MagicMock
    ) -> None:
        extractor.extract_from_image(test_image, doc_type="DRAWING")
        mock_openai_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_openai_client.chat.completions.create.call_args[1]
        messages = call_kwargs["messages"]
        # Should have image content in the user message
        user_msg = messages[-1]
        assert any(
            isinstance(c, dict) and c.get("type") == "image_url"
            for c in user_msg["content"]
        )

    def test_nonexistent_image_raises(
        self, extractor: VisionExtractor
    ) -> None:
        with pytest.raises(FileNotFoundError):
            extractor.extract_from_image(
                Path("/nonexistent.png"), doc_type="DRAWING"
            )

    def test_malformed_response_returns_empty(
        self, prompts_dir: Path
    ) -> None:
        bad_client = MagicMock()
        bad_response = MagicMock()
        bad_response.choices = [MagicMock()]
        bad_response.choices[0].message.content = "not json"
        bad_client.chat.completions.create.return_value = bad_response
        extractor = VisionExtractor(
            openai_client=bad_client, prompts_dir=prompts_dir, model="gpt-4o"
        )
        img_path = prompts_dir.parent / "test.png"
        Image.new("RGB", (100, 100)).save(img_path)
        entities = extractor.extract_from_image(img_path, doc_type="DRAWING")
        assert entities == []
```

- [ ] **Step 6: Run vision extractor tests to verify they fail**

Run: `python -m pytest tests/unit/ingestion/test_vision_extractor.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 7: Implement VisionExtractor**

Create `src/planproof/ingestion/vision_extractor.py`:

```python
"""GPT-4o vision-based entity extraction from document images.

Sends images to GPT-4o's vision API and parses structured entity JSON
from the response. Used for scanned documents and images without text layers.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from planproof.infrastructure.logging import get_logger
from planproof.ingestion.prompt_loader import PromptLoader
from planproof.ingestion.rasteriser import is_image_file
from planproof.schemas.entities import (
    EntityType,
    ExtractedEntity,
    ExtractionMethod,
)

logger = get_logger(__name__)

DEFAULT_CONFIDENCE: dict[str, float] = {
    "ADDRESS": 0.85,
    "MEASUREMENT": 0.80,
    "CERTIFICATE": 0.90,
    "BOUNDARY": 0.75,
    "ZONE": 0.85,
    "OWNERSHIP": 0.80,
}

DOC_TYPE_TO_TEMPLATE: dict[str, str] = {
    "FORM": "form_extraction",
    "REPORT": "report_extraction",
    "CERTIFICATE": "certificate_extraction",
    "DRAWING": "drawing_extraction",
}


class VisionExtractor:
    """Extract entities from document images via GPT-4o vision API.

    Uses the OpenAI client directly (not CachedLLMClient) because
    vision API calls require structured message format with image content.
    """

    def __init__(
        self,
        openai_client: Any,  # openai.OpenAI instance
        prompts_dir: Path,
        model: str = "gpt-4o",
    ) -> None:
        self._client = openai_client
        self._loader = PromptLoader(prompts_dir)
        self._model = model

    def extract_from_image(
        self, image_path: Path, doc_type: str = "DRAWING"
    ) -> list[ExtractedEntity]:
        """Extract structured entities from a document image.

        Parameters
        ----------
        image_path:
            Path to an image file (PNG, JPG, etc.)
        doc_type:
            Document type for prompt template selection.

        Returns
        -------
        list[ExtractedEntity]:
            Extracted entities. Empty list on failure.
        """
        if not image_path.exists():
            msg = f"Image not found: {image_path}"
            raise FileNotFoundError(msg)

        template_name = DOC_TYPE_TO_TEMPLATE.get(doc_type, "drawing_extraction")
        try:
            template = self._loader.load(template_name)
        except FileNotFoundError:
            template = self._loader.load("drawing_extraction")

        system_prompt = template.render(text="[image provided]")

        # Encode image as base64
        image_bytes = image_path.read_bytes()
        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        suffix = image_path.suffix.lower().lstrip(".")
        mime_map = {"png": "png", "jpg": "jpeg", "jpeg": "jpeg", "tiff": "tiff"}
        mime_type = f"image/{mime_map.get(suffix, 'png')}"

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": template.system_message},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Extract all structured entities (measurements, addresses, "
                            "certificate references) from this document image. "
                            "Respond with valid JSON containing an 'entities' array."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{b64_image}",
                        },
                    },
                ],
            },
        ]

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0,
                max_tokens=4096,
            )
            content = response.choices[0].message.content or ""
        except Exception as e:
            logger.error("vision_api_failed", error=str(e), path=str(image_path))
            return []

        return self._parse_response(content, str(image_path))

    def _parse_response(
        self, response: str, source_document: str
    ) -> list[ExtractedEntity]:
        """Parse vision API JSON response into ExtractedEntity objects."""
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1])

            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(
                "vision_json_parse_failed",
                error=str(e),
                response_preview=response[:200],
            )
            return []

        raw_entities: list[dict[str, Any]] = data.get("entities", [])
        entities: list[ExtractedEntity] = []
        now = datetime.now(UTC)

        for raw in raw_entities:
            try:
                entity_type_str = raw.get("entity_type", "")
                entity_type = EntityType(entity_type_str)
                confidence = DEFAULT_CONFIDENCE.get(entity_type_str, 0.70)

                entity = ExtractedEntity(
                    entity_type=entity_type,
                    value=raw.get("value"),
                    unit=raw.get("unit"),
                    confidence=confidence,
                    source_document=source_document,
                    source_page=raw.get("source_page"),
                    source_region=None,
                    extraction_method=ExtractionMethod.OCR_LLM,
                    timestamp=now,
                )
                entities.append(entity)
            except (ValueError, KeyError) as e:
                logger.warning("vision_entity_parse_skipped", error=str(e), raw=raw)
                continue

        logger.info(
            "vision_entities_extracted",
            count=len(entities),
            source=source_document,
        )
        return entities
```

- [ ] **Step 8: Run all vision extractor tests**

Run: `python -m pytest tests/unit/ingestion/test_vision_extractor.py tests/unit/ingestion/test_rasteriser.py -v`
Expected: All tests PASS

- [ ] **Step 9: Run type checker**

Run: `python -m mypy src/planproof/ingestion/vision_extractor.py src/planproof/ingestion/rasteriser.py --strict`
Expected: 0 errors

- [ ] **Step 10: Commit**

```bash
git add src/planproof/ingestion/vision_extractor.py src/planproof/ingestion/rasteriser.py tests/unit/ingestion/test_vision_extractor.py tests/unit/ingestion/test_rasteriser.py
git commit -m "feat(M2): add VisionExtractor (GPT-4o) and rasteriser utility"
```

---

## Task 7: Prompt templates

**Files:**
- Create: `configs/prompts/form_extraction.yaml`
- Create: `configs/prompts/report_extraction.yaml`
- Create: `configs/prompts/certificate_extraction.yaml`
- Create: `configs/prompts/drawing_extraction.yaml`

- [ ] **Step 1: Create form extraction prompt**

Create `configs/prompts/form_extraction.yaml`:

```yaml
system_message: |
  You are a planning document extraction assistant. You extract structured
  information from planning application forms submitted to local councils
  in the UK. Be precise with measurements and addresses. Extract only
  information that is explicitly stated in the text.

user_message_template: |
  Extract all structured entities from this planning application form text.
  For each entity found, provide the entity_type, attribute name, value,
  unit (if applicable), and the page number where it appears.

  Entity types to look for:
  - ADDRESS: site addresses, applicant addresses, agent addresses
  - MEASUREMENT: building height, garden depth, site area, floor area, coverage
  - CERTIFICATE: certificate type (A, B, C, D), ownership declarations
  - OWNERSHIP: owner names, applicant names
  - ZONE: planning zone, conservation area, flood zone references

  Text to extract from:
  {text}

output_schema:
  type: object
  properties:
    entities:
      type: array
      items:
        type: object
        required: [entity_type, attribute, value]
        properties:
          entity_type:
            type: string
            enum: [ADDRESS, MEASUREMENT, CERTIFICATE, OWNERSHIP, ZONE]
          attribute:
            type: string
            description: "Specific attribute name, e.g. building_height, site_address"
          value:
            description: "The extracted value — number for measurements, string for text"
          unit:
            type: string
            nullable: true
            description: "Unit of measurement, e.g. metres, percent, square_metres"
          source_page:
            type: integer
            description: "Page number where this entity was found"

few_shot_examples:
  - input: |
      Page 1: Site Address: 42 Oak Lane, Bristol, BS3 4QR
      Applicant: John Smith
      Certificate of Ownership: Certificate A
      Page 3: Proposed building height: 6.8m
      Rear garden depth after development: 11.2m
    output: |
      {"entities": [
        {"entity_type": "ADDRESS", "attribute": "site_address", "value": "42 Oak Lane, Bristol, BS3 4QR", "unit": null, "source_page": 1},
        {"entity_type": "OWNERSHIP", "attribute": "applicant_name", "value": "John Smith", "unit": null, "source_page": 1},
        {"entity_type": "CERTIFICATE", "attribute": "certificate_type", "value": "A", "unit": null, "source_page": 1},
        {"entity_type": "MEASUREMENT", "attribute": "building_height", "value": 6.8, "unit": "metres", "source_page": 3},
        {"entity_type": "MEASUREMENT", "attribute": "rear_garden_depth", "value": 11.2, "unit": "metres", "source_page": 3}
      ]}
```

- [ ] **Step 2: Create report extraction prompt**

Create `configs/prompts/report_extraction.yaml`:

```yaml
system_message: |
  You are a planning document extraction assistant. You extract structured
  information from planning reports, design & access statements, and
  supporting documents. Focus on measurements, boundary descriptions,
  and zone references embedded in narrative text.

user_message_template: |
  Extract all structured entities from this planning report text.
  Focus on measurements, boundary information, and zone references.
  Many values will be embedded in narrative paragraphs.

  Entity types to look for:
  - MEASUREMENT: building height, garden depth, site area, floor area, coverage ratios
  - BOUNDARY: site boundary descriptions, setback distances, boundary treatments
  - ZONE: planning zone, conservation area, listed building references

  Text to extract from:
  {text}

output_schema:
  type: object
  properties:
    entities:
      type: array
      items:
        type: object
        required: [entity_type, attribute, value]
        properties:
          entity_type:
            type: string
            enum: [MEASUREMENT, BOUNDARY, ZONE]
          attribute:
            type: string
          value:
            description: "The extracted value"
          unit:
            type: string
            nullable: true
          source_page:
            type: integer

few_shot_examples:
  - input: |
      The proposed extension will have a maximum ridge height of 7.2 metres,
      which is below the 8 metre limit set by Policy DM30. The rear garden
      will retain a depth of 14.5 metres after construction. The site falls
      within the BS3 residential zone and is not within a conservation area.
    output: |
      {"entities": [
        {"entity_type": "MEASUREMENT", "attribute": "building_height", "value": 7.2, "unit": "metres", "source_page": 1},
        {"entity_type": "MEASUREMENT", "attribute": "rear_garden_depth", "value": 14.5, "unit": "metres", "source_page": 1},
        {"entity_type": "ZONE", "attribute": "planning_zone", "value": "BS3 residential zone", "unit": null, "source_page": 1}
      ]}
```

- [ ] **Step 3: Create certificate extraction prompt**

Create `configs/prompts/certificate_extraction.yaml`:

```yaml
system_message: |
  You are a planning document extraction assistant. You extract structured
  information from ownership certificates and related legal declarations
  in planning applications.

user_message_template: |
  Extract all structured entities from this certificate document.
  Focus on certificate type, ownership details, and property references.

  Entity types to look for:
  - CERTIFICATE: certificate type (A, B, C, D), date signed, declaration details
  - ADDRESS: property address referenced in the certificate
  - OWNERSHIP: owner names, notice recipients

  Text to extract from:
  {text}

output_schema:
  type: object
  properties:
    entities:
      type: array
      items:
        type: object
        required: [entity_type, attribute, value]
        properties:
          entity_type:
            type: string
            enum: [CERTIFICATE, ADDRESS, OWNERSHIP]
          attribute:
            type: string
          value:
            description: "The extracted value"
          unit:
            type: string
            nullable: true
          source_page:
            type: integer

few_shot_examples:
  - input: |
      CERTIFICATE OF OWNERSHIP - CERTIFICATE A
      I certify that on the day 21 days before the date of the application
      nobody except the applicant was the owner of any part of the land.
      Signed: Jane Doe, Date: 15/01/2026
      Property: 42 Oak Lane, Bristol, BS3 4QR
    output: |
      {"entities": [
        {"entity_type": "CERTIFICATE", "attribute": "certificate_type", "value": "A", "unit": null, "source_page": 1},
        {"entity_type": "OWNERSHIP", "attribute": "signatory", "value": "Jane Doe", "unit": null, "source_page": 1},
        {"entity_type": "ADDRESS", "attribute": "property_address", "value": "42 Oak Lane, Bristol, BS3 4QR", "unit": null, "source_page": 1}
      ]}
```

- [ ] **Step 4: Create drawing extraction prompt**

Create `configs/prompts/drawing_extraction.yaml`:

```yaml
system_message: |
  You are a planning document extraction assistant specializing in
  architectural drawings. You extract measurements, dimension annotations,
  and spatial information from site plans, floor plans, and elevation drawings.

user_message_template: |
  Analyze this architectural drawing and extract all structured entities.
  Focus on dimension annotations, measurements, labels, and scale information.

  Entity types to look for:
  - MEASUREMENT: building height, width, depth, setback distances, garden depth,
    floor areas, site area, coverage ratios, scale annotations
  - BOUNDARY: property boundary dimensions, setback distances from boundaries

  {text}

output_schema:
  type: object
  properties:
    entities:
      type: array
      items:
        type: object
        required: [entity_type, attribute, value]
        properties:
          entity_type:
            type: string
            enum: [MEASUREMENT, BOUNDARY]
          attribute:
            type: string
          value:
            description: "The extracted value — numeric for measurements"
          unit:
            type: string
            nullable: true
          source_page:
            type: integer

few_shot_examples:
  - input: "[Elevation drawing showing building dimensions]"
    output: |
      {"entities": [
        {"entity_type": "MEASUREMENT", "attribute": "building_height", "value": 7.2, "unit": "metres", "source_page": 1},
        {"entity_type": "MEASUREMENT", "attribute": "building_width", "value": 8.5, "unit": "metres", "source_page": 1},
        {"entity_type": "BOUNDARY", "attribute": "rear_setback", "value": 12.0, "unit": "metres", "source_page": 1}
      ]}
```

- [ ] **Step 5: Verify prompts load correctly**

Run: `python -c "from planproof.ingestion.prompt_loader import PromptLoader; from pathlib import Path; loader = PromptLoader(Path('configs/prompts')); [print(f'{n}: OK') for n in ['form_extraction','report_extraction','certificate_extraction','drawing_extraction'] if loader.load(n)]"`
Expected: All 4 templates print "OK"

- [ ] **Step 6: Commit**

```bash
git add configs/prompts/
git commit -m "feat: add extraction prompt templates for form, report, certificate, drawing"
```

---

## Task 8: Pipeline step implementations

**Files:**
- Modify: `src/planproof/pipeline/steps/classification.py`
- Modify: `src/planproof/pipeline/steps/text_extraction.py`
- Modify: `src/planproof/ingestion/__init__.py`

- [ ] **Step 1: Update ingestion __init__.py with public exports**

Update `src/planproof/ingestion/__init__.py`:

```python
"""Ingestion layer — document classification and entity extraction."""
from planproof.ingestion.classifier import RuleBasedClassifier
from planproof.ingestion.entity_extractor import LLMEntityExtractor
from planproof.ingestion.prompt_loader import PromptLoader, PromptTemplate
from planproof.ingestion.rasteriser import is_image_file, load_image
from planproof.ingestion.text_extractor import PdfPlumberExtractor
from planproof.ingestion.vision_extractor import VisionExtractor

__all__ = [
    "LLMEntityExtractor",
    "PdfPlumberExtractor",
    "PromptLoader",
    "PromptTemplate",
    "RuleBasedClassifier",
    "VisionExtractor",
    "is_image_file",
    "load_image",
]
```

- [ ] **Step 2: Implement ClassificationStep.execute()**

Replace `src/planproof/pipeline/steps/classification.py`:

```python
"""Pipeline step: document classification."""
from __future__ import annotations

import time
from pathlib import Path

from planproof.infrastructure.logging import get_logger
from planproof.interfaces.extraction import DocumentClassifier
from planproof.interfaces.pipeline import PipelineContext
from planproof.interfaces.pipeline import StepResult as StepResultDict
from planproof.schemas.entities import ClassifiedDocument

logger = get_logger(__name__)

# File extensions the classifier will process
SUPPORTED_EXTENSIONS = frozenset({
    ".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp",
})


class ClassificationStep:
    """Classify each input document into a known type (FORM, DRAWING, etc.).

    Uses the ``DocumentClassifier`` Protocol to determine document types,
    which downstream steps use to select the appropriate extraction strategy.
    """

    def __init__(self, classifier: DocumentClassifier) -> None:
        self._classifier = classifier

    @property
    def name(self) -> str:
        return "classification"

    def execute(self, context: PipelineContext) -> StepResultDict:
        input_dir_str = context.get("metadata", {}).get("input_dir", "")
        input_dir = Path(input_dir_str)

        if not input_dir.exists():
            logger.error("input_dir_not_found", path=input_dir_str)
            return {"success": False, "message": f"Input dir not found: {input_dir_str}"}

        files = sorted(
            f for f in input_dir.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        )

        classified: list[ClassifiedDocument] = []
        for file_path in files:
            try:
                result = self._classifier.classify(file_path)
                classified.append(result)
            except Exception as e:
                logger.warning(
                    "classification_failed",
                    file=str(file_path),
                    error=str(e),
                )

        context["classified_documents"] = classified

        logger.info(
            "classification_complete",
            total_files=len(files),
            classified=len(classified),
        )

        return {
            "success": True,
            "message": f"Classified {len(classified)}/{len(files)} documents",
            "artifacts": {
                "classified_count": len(classified),
                "by_type": {
                    doc_type: sum(1 for d in classified if d.doc_type.value == doc_type)
                    for doc_type in {"FORM", "DRAWING", "REPORT", "CERTIFICATE", "OTHER"}
                },
            },
        }
```

- [ ] **Step 3: Implement TextExtractionStep.execute()**

Replace `src/planproof/pipeline/steps/text_extraction.py`:

```python
"""Pipeline step: text extraction via OCR + LLM entity parsing."""
from __future__ import annotations

from pathlib import Path

from planproof.infrastructure.logging import get_logger
from planproof.interfaces.extraction import EntityExtractor, OCRExtractor
from planproof.interfaces.pipeline import PipelineContext
from planproof.interfaces.pipeline import StepResult as StepResultDict
from planproof.schemas.entities import ClassifiedDocument, ExtractedEntity

logger = get_logger(__name__)


class TextExtractionStep:
    """Extract structured entities from text-based documents (PDFs, forms).

    Routes documents through text path (pdfplumber → LLM) or vision path
    based on ``has_text_layer`` from the classification step.
    """

    def __init__(
        self,
        ocr: OCRExtractor,
        entity_extractor: EntityExtractor,
        vision_extractor: object | None = None,
    ) -> None:
        self._ocr = ocr
        self._entity_extractor = entity_extractor
        self._vision = vision_extractor

    @property
    def name(self) -> str:
        return "text_extraction"

    def execute(self, context: PipelineContext) -> StepResultDict:
        classified_docs: list[ClassifiedDocument] = context.get(
            "classified_documents", []
        )

        if not classified_docs:
            logger.warning("no_classified_documents")
            return {
                "success": True,
                "message": "No documents to extract from",
                "artifacts": {"entity_count": 0},
            }

        all_entities: list[ExtractedEntity] = []
        errors: list[str] = []

        for doc in classified_docs:
            try:
                entities = self._extract_from_document(doc)
                all_entities.extend(entities)
            except Exception as e:
                error_msg = f"{doc.file_path}: {type(e).__name__}: {e}"
                errors.append(error_msg)
                logger.warning("extraction_failed", file=doc.file_path, error=str(e))

        # Merge with any existing entities (e.g. from a previous step)
        existing = context.get("entities", [])
        context["entities"] = existing + all_entities

        success = len(errors) == 0 or len(all_entities) > 0

        logger.info(
            "text_extraction_complete",
            entities=len(all_entities),
            errors=len(errors),
        )

        return {
            "success": success,
            "message": f"Extracted {len(all_entities)} entities, {len(errors)} errors",
            "artifacts": {
                "entity_count": len(all_entities),
                "error_count": len(errors),
                "errors": errors,
            },
        }

    def _extract_from_document(
        self, doc: ClassifiedDocument
    ) -> list[ExtractedEntity]:
        """Route a document through the appropriate extraction path."""
        if doc.has_text_layer:
            return self._text_path(doc)

        if self._vision is not None:
            return self._vision_path(doc)

        logger.info(
            "no_vision_extractor_skipping",
            file=doc.file_path,
            doc_type=doc.doc_type.value,
        )
        return []

    def _text_path(self, doc: ClassifiedDocument) -> list[ExtractedEntity]:
        """Text path: pdfplumber → LLM structured extraction."""
        raw_text = self._ocr.extract_text(Path(doc.file_path))
        return self._entity_extractor.extract_entities(raw_text)

    def _vision_path(self, doc: ClassifiedDocument) -> list[ExtractedEntity]:
        """Vision path: image → GPT-4o extraction."""
        # VisionExtractor.extract_from_image is not part of the Protocol —
        # it's specific to the vision implementation.
        extractor = self._vision
        if hasattr(extractor, "extract_from_image"):
            return extractor.extract_from_image(  # type: ignore[union-attr]
                Path(doc.file_path), doc_type=doc.doc_type.value
            )
        return []
```

- [ ] **Step 4: Run existing pipeline tests to verify no regressions**

Run: `python -m pytest tests/unit/pipeline/ -v`
Expected: All existing pipeline tests pass

- [ ] **Step 5: Run type checker on modified files**

Run: `python -m mypy src/planproof/pipeline/steps/classification.py src/planproof/pipeline/steps/text_extraction.py --strict`
Expected: 0 errors

- [ ] **Step 6: Commit**

```bash
git add src/planproof/ingestion/__init__.py src/planproof/pipeline/steps/classification.py src/planproof/pipeline/steps/text_extraction.py
git commit -m "feat: implement ClassificationStep and TextExtractionStep with two-path routing"
```

---

## Task 9: Bootstrap wiring — replace stubs with concrete implementations

**Files:**
- Modify: `src/planproof/bootstrap.py`

- [ ] **Step 1: Update bootstrap.py**

In `src/planproof/bootstrap.py`, add imports at the top (after existing imports):

```python
from planproof.ingestion.classifier import RuleBasedClassifier
from planproof.ingestion.entity_extractor import LLMEntityExtractor
from planproof.ingestion.text_extractor import PdfPlumberExtractor
from planproof.ingestion.vision_extractor import VisionExtractor
```

Replace the `_stub_classifier`, `_stub_ocr`, and `_stub_entity_extractor` factory functions:

```python
def _create_classifier(config: PipelineConfig) -> RuleBasedClassifier:
    """Create a concrete document classifier."""
    return RuleBasedClassifier(
        patterns_path=config.configs_dir / "classifier_patterns.yaml"
    )


def _create_ocr() -> PdfPlumberExtractor:
    """Create a concrete PDF text extractor."""
    return PdfPlumberExtractor()


def _create_entity_extractor(
    config: PipelineConfig, cached_llm: CachedLLMClient
) -> LLMEntityExtractor:
    """Create a concrete LLM entity extractor."""
    return LLMEntityExtractor(
        llm=cached_llm,
        prompts_dir=config.configs_dir / "prompts",
        model=config.llm_model,
    )


def _create_vision_extractor(config: PipelineConfig) -> VisionExtractor | None:
    """Create a vision extractor if OpenAI API key is available."""
    api_key = config.vlm_api_key if hasattr(config, "vlm_api_key") else config.llm_api_key
    if not api_key:
        logger.warning("no_openai_key_vision_disabled")
        return None
    import openai
    client = openai.OpenAI(api_key=api_key)
    return VisionExtractor(
        openai_client=client,
        prompts_dir=config.configs_dir / "prompts",
        model=config.vlm_model,
    )
```

Update the `build_pipeline` function to use the new factories:

```python
    # Layer 1: Ingestion — always active
    classifier = _create_classifier(config)
    ocr = _create_ocr()
    entity_extractor = _create_entity_extractor(config, _cached_llm)
    vision_extractor = _create_vision_extractor(config)

    pipeline.register(ClassificationStep(classifier=classifier))
    pipeline.register(
        TextExtractionStep(
            ocr=ocr,
            entity_extractor=entity_extractor,
            vision_extractor=vision_extractor,
        )
    )
```

Remove the `_StubClassifier`, `_StubOCR`, `_StubEntityExtractor` classes and their factory functions (`_stub_classifier`, `_stub_ocr`, `_stub_entity_extractor`). Keep `_StubVLM` and all other stubs for later phases.

Update `TextExtractionStep` constructor call to pass the new `vision_extractor` parameter.

- [ ] **Step 2: Run existing tests to verify no regressions**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All existing tests pass. The stubs are gone but the concrete implementations now handle the same Protocol interfaces.

- [ ] **Step 3: Run type checker**

Run: `python -m mypy src/planproof/bootstrap.py --strict`
Expected: 0 errors

- [ ] **Step 4: Commit**

```bash
git add src/planproof/bootstrap.py
git commit -m "feat: wire concrete classifier, text extractor, entity extractor into bootstrap"
```

---

## Task 10: Integration test — full ingestion pipeline

**Files:**
- Create: `tests/integration/test_ingestion_pipeline.py`

- [ ] **Step 1: Write integration test**

Create `tests/integration/test_ingestion_pipeline.py`:

```python
"""Integration tests for the ingestion pipeline (M1 + M2).

Tests the full flow: classify documents → extract entities from a
synthetic application set, then compare against ground truth.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from planproof.ingestion.classifier import RuleBasedClassifier
from planproof.ingestion.entity_extractor import LLMEntityExtractor
from planproof.ingestion.text_extractor import PdfPlumberExtractor
from planproof.pipeline.steps.classification import ClassificationStep
from planproof.pipeline.steps.text_extraction import TextExtractionStep
from planproof.schemas.entities import DocumentType, EntityType

SYNTHETIC_SET = Path(
    "data/synthetic/compliant/SET_COMPLIANT_42000"
)


@pytest.fixture
def classifier() -> RuleBasedClassifier:
    return RuleBasedClassifier(
        patterns_path=Path("configs/classifier_patterns.yaml")
    )


class TestClassificationIntegration:
    """Test M1 classification on real synthetic data."""

    @pytest.mark.skipif(
        not SYNTHETIC_SET.exists(),
        reason="Synthetic data not generated",
    )
    def test_classifies_all_files_in_set(
        self, classifier: RuleBasedClassifier
    ) -> None:
        files = sorted(
            f for f in SYNTHETIC_SET.iterdir()
            if f.is_file() and f.suffix.lower() in {".pdf", ".png"}
        )
        classified = [classifier.classify(f) for f in files]

        assert len(classified) > 0
        # Every file should get a classification
        assert all(c.confidence > 0 for c in classified)

    @pytest.mark.skipif(
        not SYNTHETIC_SET.exists(),
        reason="Synthetic data not generated",
    )
    def test_form_classified_correctly(
        self, classifier: RuleBasedClassifier
    ) -> None:
        form_path = SYNTHETIC_SET / "SET_COMPLIANT_42000-compliant-FORM.pdf"
        if not form_path.exists():
            pytest.skip("Form file not found")
        result = classifier.classify(form_path)
        assert result.doc_type == DocumentType.FORM
        assert result.has_text_layer is True

    @pytest.mark.skipif(
        not SYNTHETIC_SET.exists(),
        reason="Synthetic data not generated",
    )
    def test_elevation_classified_as_drawing(
        self, classifier: RuleBasedClassifier
    ) -> None:
        elevations = list(SYNTHETIC_SET.glob("*ELEVATION*.png"))
        if not elevations:
            pytest.skip("No elevation files")
        result = classifier.classify(elevations[0])
        assert result.doc_type == DocumentType.DRAWING
        assert result.has_text_layer is False

    @pytest.mark.skipif(
        not SYNTHETIC_SET.exists(),
        reason="Synthetic data not generated",
    )
    def test_scan_png_has_no_text_layer(
        self, classifier: RuleBasedClassifier
    ) -> None:
        scans = list(SYNTHETIC_SET.glob("*_scan.png"))
        if not scans:
            pytest.skip("No scan files")
        for scan in scans:
            result = classifier.classify(scan)
            assert result.has_text_layer is False


class TestClassificationStepIntegration:
    """Test ClassificationStep pipeline integration."""

    @pytest.mark.skipif(
        not SYNTHETIC_SET.exists(),
        reason="Synthetic data not generated",
    )
    def test_classification_step_populates_context(
        self, classifier: RuleBasedClassifier
    ) -> None:
        step = ClassificationStep(classifier=classifier)
        context = {
            "entities": [],
            "verdicts": [],
            "assessability_results": [],
            "metadata": {"input_dir": str(SYNTHETIC_SET)},
        }
        result = step.execute(context)
        assert result.get("success") is True
        assert "classified_documents" in context
        assert len(context["classified_documents"]) > 0


class TestTextExtractionWithMockedLLM:
    """Test M2 text extraction with mocked LLM responses."""

    @pytest.mark.skipif(
        not SYNTHETIC_SET.exists(),
        reason="Synthetic data not generated",
    )
    def test_text_path_extracts_from_form(self) -> None:
        """Text path: pdfplumber → mocked LLM → entities."""
        # Load ground truth to know what entities to expect
        gt_path = SYNTHETIC_SET / "ground_truth.json"
        if not gt_path.exists():
            pytest.skip("No ground truth")
        with open(gt_path) as f:
            ground_truth = json.load(f)

        # Build mock LLM response from ground truth
        gt_entities = []
        for doc in ground_truth["documents"]:
            if doc["doc_type"] == "FORM":
                for ext in doc["extractions"]:
                    gt_entities.append({
                        "entity_type": ext["entity_type"],
                        "attribute": ext["attribute"],
                        "value": ext["value"],
                        "unit": "metres" if ext["entity_type"] == "MEASUREMENT" else None,
                        "source_page": ext["page"],
                    })

        mock_llm = MagicMock()
        mock_llm.complete.return_value = json.dumps({"entities": gt_entities})

        extractor = PdfPlumberExtractor()
        entity_extractor = LLMEntityExtractor(
            llm=mock_llm,
            prompts_dir=Path("configs/prompts"),
            model="test",
        )

        # Extract from the PDF form
        form_path = SYNTHETIC_SET / "SET_COMPLIANT_42000-compliant-FORM.pdf"
        if not form_path.exists():
            pytest.skip("Form PDF not found")

        raw = extractor.extract_text(form_path)
        entities = entity_extractor.extract_entities(raw)

        # Verify entities were extracted
        assert len(entities) > 0

        # Verify entity types match ground truth
        extracted_types = {e.entity_type.value for e in entities}
        gt_types = {e["entity_type"] for e in gt_entities}
        assert extracted_types == gt_types


class TestDeterminism:
    """Verify extraction is deterministic."""

    @pytest.mark.skipif(
        not SYNTHETIC_SET.exists(),
        reason="Synthetic data not generated",
    )
    def test_same_input_same_output(self) -> None:
        form_path = SYNTHETIC_SET / "SET_COMPLIANT_42000-compliant-FORM.pdf"
        if not form_path.exists():
            pytest.skip("Form PDF not found")

        extractor = PdfPlumberExtractor()
        result1 = extractor.extract_text(form_path)
        result2 = extractor.extract_text(form_path)

        assert result1.text == result2.text
        assert result1.source_pages == result2.source_pages
```

- [ ] **Step 2: Run integration tests**

Run: `python -m pytest tests/integration/test_ingestion_pipeline.py -v`
Expected: All tests PASS (tests skip gracefully if synthetic data isn't present)

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests pass — both existing and new

- [ ] **Step 4: Run type checker on entire project**

Run: `python -m mypy src/planproof/ --strict`
Expected: 0 errors

- [ ] **Step 5: Run linter**

Run: `python -m ruff check src/planproof/ tests/`
Expected: Clean

- [ ] **Step 6: Commit**

```bash
git add tests/integration/test_ingestion_pipeline.py
git commit -m "test: add ingestion pipeline integration tests against synthetic data"
```

---

## Task 11: Update execution status and final verification

**Files:**
- Modify: `docs/EXECUTION_STATUS.md`

- [ ] **Step 1: Run full verification**

Run: `python -m pytest tests/ -v --tb=short && python -m mypy src/planproof/ --strict && python -m ruff check src/planproof/ tests/`
Expected: All green — tests pass, type checker clean, linter clean

- [ ] **Step 2: Update execution status**

Add Phase 2a status to `docs/EXECUTION_STATUS.md` under a new section:

```markdown
## Phase 2a: Ingestion Layer (M1 + M2) — Detailed Status

### 2.1 Document Classifier (M1) — Complete
- [x] RuleBasedClassifier with three-signal cascade (filename, text density, image heuristics)
- [x] Configurable regex patterns in `configs/classifier_patterns.yaml`
- [x] `has_text_layer` routing signal added to `ClassifiedDocument`
- [x] Unit tests for all classification signals
- [x] Integration tests against synthetic data

### 2.2 Text Extraction Pipeline (M2) — Complete
- [x] PdfPlumberExtractor — text-layer PDF extraction
- [x] LLMEntityExtractor — LLM structured extraction with prompt templates
- [x] VisionExtractor — GPT-4o image-based extraction
- [x] Rasteriser utility for image handling
- [x] PromptLoader with YAML template system
- [x] Four prompt templates (form, report, certificate, drawing)
- [x] Two-path routing in TextExtractionStep (text vs vision)
- [x] Bootstrap wired with concrete implementations
- [x] Unit tests for all components
- [x] Integration tests with mocked LLM
- [x] Determinism test
```

Update the Phase Summary table to mark Phase 2a as complete.

- [ ] **Step 3: Commit**

```bash
git add docs/EXECUTION_STATUS.md
git commit -m "docs: Phase 2a complete — M1 classifier + M2 text extraction pipeline"
```
