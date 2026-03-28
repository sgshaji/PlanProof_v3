# Phase 5: Output Layer (M10-M12) — Design Spec

**Date:** 2026-03-28 | **Depends on:** Phase 4 (M6-M9)

## Goal

Produce structured compliance reports and actionable evidence requests from pipeline verdicts. Dashboard simplified to CLI Markdown output per scope reduction guidelines.

## Components

### M10: Compliance Scoring
- `ComplianceScorer` implementing `ReportGenerator` Protocol
- Aggregates verdicts + assessability results into `ComplianceReport`
- Summary counts: total_rules, passed, failed, not_assessable
- Output as structured JSON and rendered Markdown

### M11: Evidence Request Generator
- `MinEvidenceRequestGenerator` implementing `EvidenceRequestGenerator` Protocol
- For each NOT_ASSESSABLE result: compute set-difference between required_evidence and available evidence
- Generate actionable guidance text from templates in `configs/evidence_guidance.yaml`
- Output: `list[EvidenceRequest]` with per-attribute missing evidence + human-readable guidance

### M12: CLI Report (simplified from dashboard)
- Markdown compliance report rendered to stdout/file
- Per-rule section: verdict, evidence trail, confidence
- Summary table at top
- Evidence requests section for NOT_ASSESSABLE rules
- No FastAPI/React — dissertation doesn't need a web UI

## Key decisions
- Dashboard dropped per F11 scope reduction — CLI Markdown is sufficient
- Guidance templates in YAML config, not hardcoded
- ComplianceReport schema already defined in schemas/pipeline.py
