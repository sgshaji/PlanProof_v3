"""Config loader for the synthetic data generator.

Loads and validates YAML configuration files for rules, document-set profiles,
and degradation presets.  All three loaders follow the same pattern:

  1. Enumerate every *.yaml file in the given directory.
  2. Parse the raw YAML into a Python dict.
  3. Validate the dict against the appropriate Pydantic model.
  4. Raise ConfigValidationError (not the raw Pydantic or YAML exception) so
     callers never have to import pydantic.ValidationError themselves.

# WHY: Centralising config loading here means every entry point — CLI, test
# suite, notebook — obtains validated configs through one function call.
# Pydantic validation at load time shifts errors as early as possible:
# a mis-typed field name surfaces immediately rather than silently producing
# None values that corrupt downstream generation.

# DESIGN: Pydantic BaseModel (not dataclass) is used for config schemas because
# we want coercion (e.g. int → float for numeric ranges) and the rich
# ValidationError messages that Pydantic provides.  The scenario *runtime*
# models in models.py use frozen dataclasses because they are pure carriers;
# these config objects are only ever constructed at startup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

# ---------------------------------------------------------------------------
# Public exception — the single error type callers need to catch
# ---------------------------------------------------------------------------


class ConfigValidationError(Exception):
    """Raised when a YAML config file fails schema validation.

    # WHY: Wrapping both yaml.YAMLError and pydantic.ValidationError in one
    # project-specific exception type means callers only need to handle one
    # exception.  The original error is chained via `raise ... from` so
    # tracebacks still show the root cause.
    """


# ---------------------------------------------------------------------------
# Pydantic models — one per YAML structure
# ---------------------------------------------------------------------------


class ValueRange(BaseModel):
    """A closed numeric interval [min, max].

    # WHY: Representing ranges as a typed object rather than a two-element
    # list prevents index-order bugs (is element 0 min or max?) and gives us
    # named attribute access throughout the codebase.
    """

    min: float
    max: float


class ViolationType(BaseModel):
    """A named band of non-compliant values for one rule.

    # WHY: Named bands let the scenario generator request a violation by
    # *severity label* (e.g. "marginal_exceed") without hard-coding numeric
    # ranges in Python.  Adding a new band only requires editing the YAML.
    """

    name: str
    range: ValueRange


class EvidenceLocation(BaseModel):
    """Where a rule's governing value appears in the submission documents.

    # WHY: Storing evidence locations in config (rather than code) decouples
    # the extraction layer from specific document types.  All fields except
    # doc_type are optional because a FORM evidence location needs `field`
    # but not `drawing_type`, while a DRAWING location needs `drawing_type`
    # and `annotation` but not `field`.
    """

    doc_type: str
    field: str | None = None
    drawing_type: str | None = None
    annotation: str | None = None


class DatagenRuleConfig(BaseModel):
    """Full configuration for one planning rule used by the data generator.

    # WHY: This model contains everything the scenario generator needs to
    # produce compliant and non-compliant values for a given rule, and
    # everything the renderer needs to know where to embed those values.
    """

    rule_id: str
    attribute: str
    unit: str
    compliant_range: ValueRange
    violation_types: list[ViolationType]
    evidence_locations: list[EvidenceLocation]
    # Extended fields for multi-attribute and non-numeric rule support.
    # All have defaults so existing R001/R002/R003 configs load without change.
    # WHY: value_type drives dispatch in generate_values; extra_attributes lets
    # R003 carry companion values (footprint_area, zone_category) without
    # needing a separate rule config per companion; valid/invalid_values hold
    # the categorical vocabulary; compliant/noncompliant_pairs hold string and
    # numeric pair fixtures used for C002–C004.
    value_type: str = "numeric"
    extra_attributes: list[dict[str, Any]] = []
    valid_values: list[str] = []
    invalid_values: list[str] = []
    compliant_pairs: list[dict[str, Any]] = []
    noncompliant_pairs: list[dict[str, Any]] = []


class DocumentComposition(BaseModel):
    """Specification for one document type within a profile.

    # WHY: Separating count from subtypes allows the same document type
    # (e.g. DRAWING) to appear in a profile multiple times with different
    # subtype lists, which is how real multi-drawing submissions are structured.
    """

    type: str
    subtypes: list[str] | None = None
    count: int


class ProfileConfig(BaseModel):
    """Document-set profile driving how many and what kind of documents are made.

    # WHY: Profiles abstract "how complex is this test set?" into a named
    # artefact that both the scenario generator and evaluation reports can
    # reference.  Storing difficulty and degradation_preset here means a single
    # profile ID carries the complete rendering context.
    """

    profile_id: str
    document_composition: list[DocumentComposition]
    difficulty: str
    degradation_preset: str


class TransformSpec(BaseModel):
    """One image-degradation transform with its numeric parameters.

    # WHY: Keeping transform name and parameters together in a typed object
    # prevents the renderer from having to unpack arbitrary dicts, and makes
    # it easy to add new transforms without touching the renderer's dispatch
    # logic — it just calls transform_registry[spec.name](**spec.params).
    """

    name: str
    params: dict[str, float]


class DegradationPreset(BaseModel):
    """An ordered sequence of image transforms applied to every document page.

    # WHY: An empty transforms list (the "clean" preset) is a valid config,
    # not an error.  Using an empty list rather than None makes the renderer's
    # loop unconditional: `for transform in preset.transforms` always works.
    """

    preset_id: str
    transforms: list[TransformSpec]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_yaml_file(path: Path) -> dict[str, Any]:
    """Read one YAML file and return its top-level mapping.

    # WHY: This thin wrapper exists so that both the YAML parse error and the
    # "not a mapping" error can be re-raised as ConfigValidationError in one
    # place, rather than handling them separately in every loader function.
    """
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigValidationError(
            f"YAML parse error in {path}: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise ConfigValidationError(
            f"Expected a YAML mapping at top level in {path}, got {type(raw).__name__}"
        )
    return raw


def _iter_yaml_files(directory: Path) -> list[Path]:
    """Return all *.yaml files in *directory*, sorted for determinism.

    # WHY: Sorting ensures that the order of returned configs is the same
    # across operating systems and file systems, making test assertions that
    # check list length or set membership fully deterministic.
    """
    return sorted(directory.glob("*.yaml"))


# ---------------------------------------------------------------------------
# Public loader functions
# ---------------------------------------------------------------------------


def load_rule_configs(rules_dir: Path | str) -> list[DatagenRuleConfig]:
    """Load and validate all rule configs from *rules_dir*.

    Each *.yaml file must conform to the DatagenRuleConfig schema.  Any
    file that fails validation causes the entire load to abort with a
    ConfigValidationError — partial loads would leave the caller with an
    incomplete rule catalogue, which is worse than failing fast.

    Args:
        rules_dir: Directory containing rule YAML files (e.g. r001_*.yaml).

    Returns:
        Validated list of DatagenRuleConfig objects, one per file.

    Raises:
        ConfigValidationError: If any file fails YAML parsing or schema
            validation.
    """
    directory = Path(rules_dir)
    configs: list[DatagenRuleConfig] = []

    for yaml_path in _iter_yaml_files(directory):
        raw = _load_yaml_file(yaml_path)
        try:
            configs.append(DatagenRuleConfig.model_validate(raw))
        except ValidationError as exc:
            raise ConfigValidationError(
                f"Schema validation failed for rule config {yaml_path}: {exc}"
            ) from exc

    return configs


def load_profiles(profiles_dir: Path | str) -> list[ProfileConfig]:
    """Load and validate all document-set profiles from *profiles_dir*.

    Each *.yaml file must conform to the ProfileConfig schema.

    Args:
        profiles_dir: Directory containing profile YAML files.

    Returns:
        Validated list of ProfileConfig objects, one per file.

    Raises:
        ConfigValidationError: If any file fails YAML parsing or schema
            validation.
    """
    directory = Path(profiles_dir)
    profiles: list[ProfileConfig] = []

    for yaml_path in _iter_yaml_files(directory):
        raw = _load_yaml_file(yaml_path)
        try:
            profiles.append(ProfileConfig.model_validate(raw))
        except ValidationError as exc:
            raise ConfigValidationError(
                f"Schema validation failed for profile {yaml_path}: {exc}"
            ) from exc

    return profiles


def load_degradation_presets(presets_dir: Path | str) -> list[DegradationPreset]:
    """Load and validate all degradation presets from *presets_dir*.

    Each *.yaml file must conform to the DegradationPreset schema.

    Args:
        presets_dir: Directory containing degradation preset YAML files.

    Returns:
        Validated list of DegradationPreset objects, one per file.

    Raises:
        ConfigValidationError: If any file fails YAML parsing or schema
            validation.
    """
    directory = Path(presets_dir)
    presets: list[DegradationPreset] = []

    for yaml_path in _iter_yaml_files(directory):
        raw = _load_yaml_file(yaml_path)
        try:
            presets.append(DegradationPreset.model_validate(raw))
        except ValidationError as exc:
            raise ConfigValidationError(
                f"Schema validation failed for degradation preset {yaml_path}: {exc}"
            ) from exc

    return presets
