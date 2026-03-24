"""Rule evaluator implementations for PlanProof.

Each evaluator handles a specific *type* of compliance check (numeric
threshold, ratio comparison, enum membership, etc.).  The ``RuleFactory``
maps ``evaluation_type`` strings from YAML rule configs to the appropriate
evaluator class.

Modules
-------
factory             -- ``RuleFactory`` with evaluator registry (OCP pattern)
numeric_threshold   -- Absolute numeric comparisons (R001, R002)
ratio_threshold     -- Ratio-based comparisons (R003)
enum_check          -- Enumeration membership checks (C1)
fuzzy_match         -- Fuzzy string matching for addresses/names (C2)
numeric_tolerance   -- Numeric equality within tolerance (C3)
attribute_diff      -- Cross-attribute difference checks (C4)
"""
