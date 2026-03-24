"""Pipeline orchestration for PlanProof.

Provides the step-registry ``Pipeline`` class that runs registered
``PipelineStep`` implementations in sequence, threading a shared
``PipelineContext`` through each step.

Modules
-------
pipeline    -- Main ``Pipeline`` orchestrator
steps/      -- Concrete step implementations (one per processing stage)
"""
