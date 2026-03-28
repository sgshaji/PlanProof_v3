# Phase 3: Representation Layer (M5) — Design Spec

**Date:** 2026-03-28 | **Depends on:** Phase 2 (M1-M3)

## Goal

Normalise extracted entities to canonical units, populate a Neo4j knowledge graph with entities + reference geometry, and provide queryable evidence for downstream reasoning.

## Sub-components

### 1. Normalisation
- Extensible unit conversion registry: `{("feet","metres"): fn, ("inches","mm"): fn, ...}`
- Address canonicalisation: abbreviation expansion, postcode formatting
- Numeric precision normalisation per unit type
- Registry-based — new conversions are data, not code

### 2. SNKG (Neo4j graph)

Neo4j schema:
```
(:Application {set_id})
(:SourceDocument {file_path, doc_type})         -[:BELONGS_TO]->   (:Application)
(:ExtractedEntity {type, attribute, value...})   -[:EXTRACTED_FROM]-> (:SourceDocument)
(:Parcel {parcel_id, geometry_wkt})              -[:BELONGS_TO]->   (:Application)
(:Zone {code, name})                             -[:APPLIES_TO]->   (:Parcel)
(:Rule {rule_id, description})                   -[:APPLICABLE_IN]-> (:Zone)
(:ExtractedEntity)                               -[:EVIDENCE_FOR]->  (:Rule)
```

`Neo4jSNKG` class implements all 4 existing Protocols: EntityPopulator, ReferenceDataLoader, EvidenceProvider, RuleProvider.

Spatial: shapely for polygon containment/intersection (arbitrary polygons, not just rectangles). Geometry stored as WKT. Spatial predicates computed in Python before graph insertion.

### 3. FlatEvidenceProvider (Ablation B)
- Implements EvidenceProvider Protocol without Neo4j
- Attribute-name matching against flat entity list
- Used when `config.ablation.use_snkg = False`

## Files

**New:** `representation/normalisation.py`, `representation/snkg.py`, `representation/reference_data.py`, `representation/flat_evidence.py` + corresponding tests

**Modified:** `pipeline/steps/normalisation.py`, `pipeline/steps/graph_population.py`, `bootstrap.py`

## Constraints
- shapely in optional `[geo]` dep, spatial tests skip on ARM64 Windows, run in CI
- Zone boundaries support arbitrary polygon complexity
- No live geocoding (scope exclusion)

## Deferred
- Live OS/Land Registry API calls
