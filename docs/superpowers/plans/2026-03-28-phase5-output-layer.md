# Phase 5: Output Layer (M10-M12) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce structured compliance reports and actionable evidence requests. CLI Markdown output instead of web dashboard.

**Architecture:** ComplianceScorer aggregates verdicts into reports, MinEvidenceRequestGenerator computes missing evidence from NOT_ASSESSABLE results, MarkdownReportRenderer outputs human-readable reports.

**Tech Stack:** Python 3.11+, pydantic, pyyaml

**Spec:** `docs/superpowers/specs/2026-03-28-phase5-output-layer-design.md`

---

## File Structure

### New Files
- `src/planproof/output/scoring.py` — `ComplianceScorer` implementing `ReportGenerator` Protocol
- `src/planproof/output/evidence_request.py` — `MinEvidenceRequestGenerator` implementing `EvidenceRequestGenerator` Protocol
- `src/planproof/output/markdown_renderer.py` — `MarkdownReportRenderer` for CLI output
- `configs/evidence_guidance.yaml` — Guidance text templates per attribute
- `tests/unit/output/__init__.py`
- `tests/unit/output/test_scoring.py`
- `tests/unit/output/test_evidence_request.py`
- `tests/unit/output/test_markdown_renderer.py`
- `tests/integration/test_output_pipeline.py`

### Modified Files
- `src/planproof/pipeline/steps/scoring.py` — Implement execute()
- `src/planproof/pipeline/steps/evidence_request.py` — Implement execute()
- `src/planproof/bootstrap.py` — Wire concrete output components, remove stubs

---

## Task 1: ComplianceScorer (M10)

**Files:**
- Create: `src/planproof/output/scoring.py`
- Create: `tests/unit/output/test_scoring.py`

**What:** Implement `ComplianceScorer` satisfying `ReportGenerator` Protocol.

`generate(verdicts, assessability_results) -> ComplianceReport`:
- Count PASS, FAIL, NOT_ASSESSABLE from verdicts + assessability_results
- Build `ReportSummary` with total_rules, passed, failed, not_assessable
- Return `ComplianceReport` with application_id from metadata, verdicts, assessability_results, summary, generated_at=now

Tests: empty verdicts, all PASS, mixed verdicts, NOT_ASSESSABLE counted correctly.

- [ ] Write tests, implement, lint, typecheck, commit

---

## Task 2: MinEvidenceRequestGenerator (M11)

**Files:**
- Create: `src/planproof/output/evidence_request.py`
- Create: `configs/evidence_guidance.yaml`
- Create: `tests/unit/output/test_evidence_request.py`

**What:** Implement `MinEvidenceRequestGenerator` satisfying `EvidenceRequestGenerator` Protocol.

`generate_requests(not_assessable: list[AssessabilityResult]) -> list[EvidenceRequest]`:
- For each NOT_ASSESSABLE result: iterate its `missing_evidence` list
- For each missing EvidenceRequirement: create `MissingEvidence` with attribute, acceptable_document_types, and guidance text from YAML template
- Guidance templates loaded from `configs/evidence_guidance.yaml` keyed by attribute name
- Fallback guidance if attribute not in config: "Please provide {attribute} from an acceptable source document."

YAML format:
```yaml
building_height: "Provide a dimensioned elevation drawing showing the overall building height in metres."
rear_garden_depth: "Provide a dimensioned site plan showing the rear garden depth from building rear wall to rear boundary."
site_coverage: "Provide floor plans with dimensions, or state the building footprint area and total site area."
zone_category: "Confirm the zoning classification on the application form or provide council zoning certificate."
```

Tests: generates requests for NOT_ASSESSABLE rules, uses YAML guidance, falls back for unknown attributes, empty input returns empty.

- [ ] Write tests, implement, lint, typecheck, commit

---

## Task 3: Implement ScoringStep and EvidenceRequestStep

**Files:**
- Modify: `src/planproof/pipeline/steps/scoring.py`
- Modify: `src/planproof/pipeline/steps/evidence_request.py`
- Create: `tests/unit/output/test_pipeline_steps.py`

**What:**

**ScoringStep.execute():**
- Get verdicts from `context.get("verdicts", [])`
- Get assessability_results from `context.get("assessability_results", [])`
- Create ComplianceScorer, call generate()
- Store report in context (add to metadata or a new key)
- Return success with summary counts

**EvidenceRequestStep.execute():**
- Get assessability_results, filter to NOT_ASSESSABLE
- Call `self._generator.generate_requests(not_assessable)`
- Store evidence requests in context
- Return success with request count

Tests: 2-3 per step with mocked dependencies.

- [ ] Write tests, implement, lint, typecheck, commit

---

## Task 4: MarkdownReportRenderer (M12 simplified)

**Files:**
- Create: `src/planproof/output/markdown_renderer.py`
- Create: `tests/unit/output/test_markdown_renderer.py`

**What:** Render a `ComplianceReport` + `list[EvidenceRequest]` as a Markdown string.

Format:
```
# Compliance Report: {application_id}
Generated: {timestamp}

## Summary
| Metric | Count |
|--------|-------|
| Total Rules | N |
| Passed | N |
| Failed | N |
| Not Assessable | N |

## Rule Verdicts
### R001: Maximum Building Height
- **Verdict:** PASS
- **Evaluated Value:** 7.5 metres
- **Threshold:** ≤ 8.0 metres
- **Evidence:** elevation.png (VLM_ZEROSHOT, confidence: 0.85)

## Evidence Requests
### R002: Minimum Rear Garden Depth
**Status:** NOT_ASSESSABLE — Missing Evidence
**What's needed:**
- rear_garden_depth: Provide a dimensioned site plan...
```

Tests: renders with verdicts, renders with evidence requests, renders empty report.

- [ ] Write tests, implement, lint, typecheck, commit

---

## Task 5: Wire into bootstrap + update status

**Files:**
- Modify: `src/planproof/bootstrap.py`
- Modify: `docs/EXECUTION_STATUS.md`

**What:**
- Import and wire ComplianceScorer, MinEvidenceRequestGenerator
- Remove `_StubEvidenceRequestGenerator` and its factory
- Load evidence_guidance.yaml for the generator
- Update EXECUTION_STATUS: Phase 5 → Complete

- [ ] Wire, run full test suite, lint, typecheck, commit

---

## Task 6: Integration test + docs + push

**Files:**
- Create: `tests/integration/test_output_pipeline.py`

**What:** End-to-end test: feed verdicts + assessability results → ComplianceReport + EvidenceRequests + Markdown output. Verify structure and content.

- [ ] Write tests, commit docs, push to GitHub
