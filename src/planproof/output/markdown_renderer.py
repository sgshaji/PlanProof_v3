"""Markdown renderer for ComplianceReport output.

Converts a ComplianceReport (and optional EvidenceRequests) into a
human-readable Markdown string suitable for CLI display or file export.
Sections are omitted when they have no content.
"""
from __future__ import annotations

from planproof.schemas.pipeline import ComplianceReport, EvidenceRequest


class MarkdownReportRenderer:
    """Render a ComplianceReport as a Markdown string."""

    def render(
        self,
        report: ComplianceReport,
        evidence_requests: list[EvidenceRequest] | None = None,
    ) -> str:
        parts: list[str] = []

        parts.append(self._render_header(report))
        parts.append(self._render_summary(report))

        verdict_section = self._render_verdicts(report)
        if verdict_section:
            parts.append(verdict_section)

        not_assessable_section = self._render_not_assessable(report)
        if not_assessable_section:
            parts.append(not_assessable_section)

        evidence_section = self._render_evidence_requests(evidence_requests)
        if evidence_section:
            parts.append(evidence_section)

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Section renderers
    # ------------------------------------------------------------------

    def _render_header(self, report: ComplianceReport) -> str:
        generated = report.generated_at.strftime("%Y-%m-%d %H:%M:%S")
        return (
            f"# Compliance Report: {report.application_id}\n"
            f"Generated: {generated}"
        )

    def _render_summary(self, report: ComplianceReport) -> str:
        s = report.summary
        lines = [
            "## Summary",
            "| Metric | Count |",
            "|--------|-------|",
            f"| Total Rules | {s.total_rules} |",
            f"| Passed | {s.passed} |",
            f"| Failed | {s.failed} |",
            f"| Not Assessable | {s.not_assessable} |",
        ]
        return "\n".join(lines)

    def _render_verdicts(self, report: ComplianceReport) -> str:
        if not report.verdicts:
            return ""

        lines = ["## Rule Verdicts"]
        for verdict in report.verdicts:
            lines.append(f"\n### {verdict.rule_id}")
            lines.append(f"- **Verdict:** {verdict.outcome}")
            lines.append(f"- **Evaluated Value:** {verdict.evaluated_value}")
            lines.append(f"- **Threshold:** {verdict.threshold}")

            # Evidence — use first entity for the evidence line; if multiple
            # exist, render each on its own line.
            for entity in verdict.evidence_used:
                lines.append(
                    f"- **Evidence:** {entity.source_document}"
                    f" ({entity.extraction_method},"
                    f" confidence: {entity.confidence})"
                )

            lines.append(f"- **Explanation:** {verdict.explanation}")

        return "\n".join(lines)

    def _render_not_assessable(self, report: ComplianceReport) -> str:
        not_assessable = [
            r for r in report.assessability_results if r.status == "NOT_ASSESSABLE"
        ]
        if not not_assessable:
            return ""

        lines = ["## Not Assessable Rules"]
        for result in not_assessable:
            lines.append(f"\n### {result.rule_id}")
            lines.append("- **Status:** NOT_ASSESSABLE")
            lines.append(f"- **Reason:** {result.blocking_reason}")

        return "\n".join(lines)

    def _render_evidence_requests(
        self, evidence_requests: list[EvidenceRequest] | None
    ) -> str:
        if not evidence_requests:
            return ""

        lines = ["## Evidence Requests"]
        for request in evidence_requests:
            lines.append(f"\n### {request.rule_id}")
            lines.append("**What's needed:**")
            for item in request.missing:
                lines.append(f"- {item.attribute}: {item.guidance}")

        return "\n".join(lines)
