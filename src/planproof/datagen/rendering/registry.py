"""Document generator registry — Protocol-based plugin dispatch.

# DESIGN: Generators are registered by DocumentType key rather than by class
# inheritance.  This means any object that implements the DocumentGenerator
# Protocol can be plugged in without inheriting from a base class, keeping the
# rendering plugins decoupled from this registry module entirely.  New document
# types (e.g. CERTIFICATE, OTHER) can be added at runtime by calling
# `register()` without modifying any existing code.

# WHY: Using a Protocol instead of an abstract base class means third-party or
# test implementations do not need to import from this module at all — duck
# typing with static verification.  The registry stores Protocol instances, so
# mypy can verify conformance at the call site where `register()` is called.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from planproof.datagen.rendering.models import GeneratedDocument
from planproof.datagen.scenario.models import DocumentSpec, Scenario


@runtime_checkable
class DocumentGenerator(Protocol):
    """Contract: a plugin that renders one document from a Scenario spec.

    # WHY: Accepting `seed` as an explicit parameter (rather than reading it
    # from the Scenario) allows the registry to override the seed for targeted
    # reproduction of individual documents without constructing a full new
    # Scenario.  It also makes the determinism contract explicit in the
    # function signature — callers know they must supply a seed.
    """

    def generate(
        self,
        scenario: Scenario,
        doc_spec: DocumentSpec,
        seed: int,
    ) -> GeneratedDocument:
        """Render one document and return its bytes plus ground-truth placements.

        Args:
            scenario:  The parent scenario supplying ground-truth values.
            doc_spec:  Per-document instructions (type, format, which values).
            seed:      Random seed for deterministic layout and content choices.

        Returns:
            A GeneratedDocument containing the raw bytes and all PlacedValues.
        """
        ...


class DocumentGeneratorRegistry:
    """Maps DocumentType keys to DocumentGenerator plugin instances.

    # WHY: Centralising generator lookup here means the top-level corpus
    # generator (which iterates over Scenarios) does not need to import or
    # know about any specific rendering implementation.  Adding a new document
    # type is a single `register()` call at startup, with no changes required
    # to the iteration logic.

    # DESIGN: The internal store is a plain dict.  We do not use a frozen
    # structure here because registrations happen at application-startup time
    # before any generation begins.  If we needed to support concurrent
    # registrations we would use a threading.Lock, but that complexity is not
    # warranted for a single-process corpus generator.
    """

    def __init__(self) -> None:
        # WHY: Typed as dict[str, DocumentGenerator] so callers can register by
        # both DocumentType values (e.g. "FORM") and subtype strings (e.g.
        # "site_plan", "floor_plan", "elevation") without needing a separate
        # registry per dispatch level.
        self._generators: dict[str, DocumentGenerator] = {}

    def register(self, doc_type: str, generator: DocumentGenerator) -> None:
        """Associate a generator with a document type.

        Calling register() with an already-registered doc_type replaces the
        previous generator.  This makes it straightforward to override a
        default generator with a specialised one in test environments.

        Args:
            doc_type:  The DocumentType key this generator handles.
            generator: Any object satisfying the DocumentGenerator Protocol.
        """
        self._generators[doc_type] = generator

    def get(self, doc_type: str) -> DocumentGenerator:
        """Retrieve the generator for a given document type.

        Args:
            doc_type: The DocumentType to look up.

        Returns:
            The registered DocumentGenerator for this type.

        Raises:
            KeyError: If no generator has been registered for doc_type.

        # WHY: Raising KeyError (not returning None) forces callers to handle
        # missing registrations explicitly.  A None return would propagate
        # silently until generate() is called, making the error much harder to
        # diagnose.
        """
        if doc_type not in self._generators:
            raise KeyError(
                f"No generator registered for DocumentType '{doc_type}'. "
                f"Call registry.register({doc_type!r}, generator) before use."
            )
        return self._generators[doc_type]
