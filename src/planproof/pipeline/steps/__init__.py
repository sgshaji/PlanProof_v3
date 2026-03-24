"""Concrete pipeline step implementations.

Each module defines a single ``PipelineStep`` that performs one stage of
the PlanProof processing pipeline.  Steps are registered with the
``Pipeline`` orchestrator in ``planproof.bootstrap`` based on the active
``AblationConfig``.

Modules
-------
classification      -- Document type classification
text_extraction     -- OCR + LLM entity extraction from text documents
vlm_extraction      -- VLM-based extraction from architectural drawings
normalisation       -- Entity normalisation and unit conversion
graph_population    -- Populate the Spatial Normative Knowledge Graph
reconciliation      -- Cross-source evidence reconciliation
confidence_gating   -- Filter low-confidence extractions
assessability       -- Determine whether rules can be evaluated
rule_evaluation     -- Evaluate compliance rules against evidence
scoring             -- Aggregate verdicts into scores
evidence_request    -- Generate requests for missing evidence
"""
