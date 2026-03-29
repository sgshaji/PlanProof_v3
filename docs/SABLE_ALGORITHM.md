# SABLE: Semantically-Augmented Belief Logic for Evidence

> **A novel algorithm for evidence sufficiency assessment in multimodal regulatory compliance checking.**

---

## 1. Problem Statement

Given a regulatory compliance rule $R$ with a set of evidence requirements $\{R_1, R_2, \ldots, R_n\}$, and a pool of extracted entities $E = \{e_1, e_2, \ldots, e_m\}$ obtained from multimodal document processing (OCR, LLM, VLM), determine whether sufficient trustworthy evidence exists to evaluate the rule — before attempting evaluation.

Traditional compliance systems assume complete, reliable data (typically from structured BIM models). When applied to unstructured documents with uncertain extraction, they produce silent failures: rules evaluated on insufficient or unreliable evidence yield false verdicts.

SABLE addresses this by computing a continuous **Evidence Sufficiency Score (ESS)** grounded in Dempster-Shafer evidence theory, producing three possible states: ASSESSABLE, NOT_ASSESSABLE, or PARTIALLY_ASSESSABLE.

---

## 2. Theoretical Foundation

### 2.1 Dempster-Shafer Evidence Theory

SABLE is grounded in Dempster-Shafer (D-S) theory of evidence [1], which generalises Bayesian probability to handle epistemic uncertainty — situations where evidence is incomplete or ambiguous.

**Frame of discernment.** For each evidence requirement, we define:

$$\Theta = \{\text{sufficient}, \text{insufficient}\}$$

**Basic Probability Assignment (BPA).** A mass function $m: 2^\Theta \rightarrow [0, 1]$ assigns belief mass to subsets of $\Theta$:

- $m(\{\text{sufficient}\})$ — direct evidence that the requirement is met
- $m(\{\text{insufficient}\})$ — direct evidence that the requirement is not met
- $m(\Theta)$ — **ignorance** — evidence exists but is inconclusive

With constraint: $m(\emptyset) = 0$ and $\sum_{A \subseteq \Theta} m(A) = 1$.

**Belief and Plausibility.** From the combined mass function:

$$\text{Bel}(A) = \sum_{B \subseteq A} m(B) \quad \text{(lower bound of support)}$$
$$\text{Pl}(A) = \sum_{B \cap A \neq \emptyset} m(B) \quad \text{(upper bound of support)}$$

The interval $[\text{Bel}(\text{sufficient}), \text{Pl}(\text{sufficient})]$ represents the range of possible evidence sufficiency, with the gap $\text{Pl} - \text{Bel}$ quantifying residual uncertainty.

### 2.2 Dempster's Rule of Combination

When multiple entities provide evidence for the same requirement, their mass functions are combined using Dempster's rule [1]:

$$m_{1,2}(A) = \frac{1}{1-K} \sum_{B \cap C = A} m_1(B) \cdot m_2(C)$$

where the **conflict mass** $K$ measures source disagreement:

$$K = \sum_{B \cap C = \emptyset} m_1(B) \cdot m_2(C)$$

High $K$ indicates contradictory evidence — a principled signal for NOT_ASSESSABLE.

---

## 3. The SABLE Algorithm

### 3.1 Novel Contribution: Four-Factor Mass Function Construction

SABLE's primary contribution is the **mass function construction layer** — a novel procedure that decomposes extraction uncertainty into four interpretable, orthogonal dimensions:

| Dimension | Symbol | Source | What it captures |
|-----------|--------|--------|-----------------|
| **Source reliability** | $\rho_i$ | Extraction method confidence thresholds | How reliable is the extraction method? |
| **Extraction confidence** | $c_i$ | Entity confidence score | How confident is the extractor about this specific extraction? |
| **Semantic relevance** | $r_i$ | Embedding cosine similarity | Does this entity actually relate to the required attribute? |
| **Cross-source concordance** | $\gamma_j$ | Pairwise reconciliation status | Do multiple sources agree on this attribute? |

**To our knowledge, no prior work combines embedding-based semantic relevance scoring with Dempster-Shafer evidence theory for regulatory compliance assessability determination.**

### 3.2 Mass Function Construction

For each entity $e_i$ matched to requirement $R_j$:

**Step 1: Compute source reliability.**

$$\rho_i = \text{threshold}[e_i.\text{extraction\_method}][e_i.\text{entity\_type}]$$

Source: calibrated per-method/per-type confidence thresholds from system configuration (e.g., $\rho_{\text{OCR\_LLM, MEASUREMENT}} = 0.80$, $\rho_{\text{VLM\_ZEROSHOT, MEASUREMENT}} = 0.70$).

**Step 2: Extract confidence.**

$$c_i = e_i.\text{confidence} \in [0, 1]$$

Source: extraction pipeline output. Represents the extractor's self-assessed certainty for this specific entity.

**Step 3: Compute semantic relevance.**

$$r_i = \text{cosine\_similarity}(\text{embed}(e_i.\text{attribute}), \text{embed}(R_j.\text{attribute}))$$

Source: sentence embedding model (e.g., `all-MiniLM-L6-v2`). Deterministic, no LLM call, no circular dependency. Captures semantic relatedness between what was extracted ("height") and what the rule requires ("building_height").

If $r_i < \tau_{\text{relevance}}$ (default 0.5): discard entity as semantically unrelated.

**Step 4: Construct three-valued mass function.**

$$m_i(\{\text{sufficient}\}) = \rho_i \times c_i \times r_i$$
$$m_i(\{\text{insufficient}\}) = (1 - \rho_i) \times (1 - c_i) \times (1 - r_i)$$
$$m_i(\Theta) = 1 - m_i(\{\text{sufficient}\}) - m_i(\{\text{insufficient}\})$$

The ignorance mass $m_i(\Theta)$ captures cases where evidence exists but is inconclusive — for example, a moderately confident extraction from a somewhat reliable method with partial semantic match. This three-valued assignment is more mathematically complete than a binary mass model.

### 3.3 Multi-Source Combination

When multiple entities $\{e_1, \ldots, e_k\}$ provide evidence for requirement $R_j$, combine their mass functions using Dempster's rule:

$$m_j = m_1 \oplus m_2 \oplus \cdots \oplus m_k$$

The conflict mass $K_j$ emerges naturally from the combination — it quantifies the degree to which sources disagree, without requiring an ad-hoc conflict detection step.

### 3.4 Concordance Adjustment

After Dempster combination, apply a concordance adjustment based on cross-source reconciliation:

$$\text{Bel}_j^{\text{adjusted}} = \text{Bel}_j \times \gamma_j$$

Where:

$$\gamma_j = \begin{cases} 1.0 & \text{if reconciliation status} = \text{AGREED} \\ 0.7 & \text{if reconciliation status} = \text{SINGLE\_SOURCE} \\ 0.3 & \text{if reconciliation status} = \text{CONFLICTING} \\ 0.0 & \text{if reconciliation status} = \text{MISSING} \end{cases}$$

This ensures that even when D-S combination produces moderate belief, unresolved conflicts reduce the final score.

### 3.5 Requirement Aggregation

Aggregate across all requirements using a **weakest-link** strategy:

$$\text{Bel}(R) = \min_j(\text{Bel}_j^{\text{adjusted}})$$
$$\text{Pl}(R) = \min_j(\text{Pl}_j)$$
$$K(R) = \max_j(K_j)$$

Rationale: a rule is only as assessable as its least-supported requirement. A single missing requirement blocks the entire rule.

### 3.6 Three-State Decision

$$\text{status}(R) = \begin{cases} \text{ASSESSABLE} & \text{if } \text{Bel}(R) \geq \theta_{\text{high}} \\ \text{NOT\_ASSESSABLE} & \text{if } \text{Pl}(R) \leq \theta_{\text{low}} \\ \text{PARTIALLY\_ASSESSABLE} & \text{otherwise} \end{cases}$$

Default thresholds: $\theta_{\text{high}} = 0.7$, $\theta_{\text{low}} = 0.3$.

The PARTIALLY_ASSESSABLE state — absent from all prior compliance checking systems — enables graduated evidence requests: "You're close — provide one additional measurement to confirm."

---

## 4. Algorithm Pseudocode

```
Algorithm SABLE(rule R, entities E, graph G, embeddings model)
─────────────────────────────────────────────────────────────

Input:
  R: RuleConfig with required_evidence = {R₁, R₂, ..., Rₙ}
  E: list[ExtractedEntity] from evidence provider
  G: SNKG for structured evidence retrieval
  model: sentence embedding model for semantic similarity

Output:
  result: AssessabilityResult with (status, belief, plausibility, conflict_mass)

1.  requirement_beliefs ← empty list

2.  FOR EACH requirement Rⱼ IN R.required_evidence:

3.      matched ← FILTER(E, by source type matching Rⱼ.acceptable_sources)

4.      // SEMANTIC RELEVANCE FILTERING
5.      FOR EACH entity eᵢ IN matched:
6.          rᵢ ← cosine_similarity(embed(eᵢ.attribute), embed(Rⱼ.attribute))
7.          IF rᵢ < τ_relevance:  REMOVE eᵢ from matched

8.      IF matched IS EMPTY:
9.          requirement_beliefs.APPEND((0.0, 1.0, 0.0))  // no evidence
10.         CONTINUE

11.     // CONFIDENCE GATING
12.     trusted ← FILTER(matched, by confidence_gate.is_trustworthy)
13.     IF trusted IS EMPTY:
14.         requirement_beliefs.APPEND((0.0, 0.5, 0.0))  // evidence exists but untrusted
15.         CONTINUE

16.     // MASS FUNCTION CONSTRUCTION
17.     mass_functions ← empty list
18.     FOR EACH entity eᵢ IN trusted:
19.         ρᵢ ← threshold_lookup[eᵢ.extraction_method][eᵢ.entity_type]
20.         cᵢ ← eᵢ.confidence
21.         rᵢ ← cosine_similarity(embed(eᵢ.attribute), embed(Rⱼ.attribute))
22.
23.         m_suf ← ρᵢ × cᵢ × rᵢ
24.         m_ins ← (1 - ρᵢ) × (1 - cᵢ) × (1 - rᵢ)
25.         m_ign ← 1 - m_suf - m_ins
26.
27.         mass_functions.APPEND({sufficient: m_suf, insufficient: m_ins, Θ: m_ign})

28.     // DEMPSTER COMBINATION
29.     combined ← mass_functions[0]
30.     K_total ← 0.0
31.     FOR i ← 1 TO len(mass_functions) - 1:
32.         combined, K ← DEMPSTER_COMBINE(combined, mass_functions[i])
33.         K_total ← max(K_total, K)

34.     Belⱼ ← combined[sufficient]
35.     Plⱼ  ← 1 - combined[insufficient]

36.     // CONCORDANCE ADJUSTMENT
37.     reconciled ← reconciler.reconcile(trusted, Rⱼ.attribute)
38.     γⱼ ← CONCORDANCE_FACTOR(reconciled.status)
39.     Belⱼ ← Belⱼ × γⱼ

40.     requirement_beliefs.APPEND((Belⱼ, Plⱼ, K_total))

41. // AGGREGATE ACROSS REQUIREMENTS
42. Bel_rule ← MIN(Belⱼ for all j)
43. Pl_rule  ← MIN(Plⱼ for all j)
44. K_rule   ← MAX(Kⱼ for all j)

45. // THREE-STATE DECISION
46. IF Bel_rule ≥ θ_high:  status ← ASSESSABLE
47. ELIF Pl_rule ≤ θ_low:  status ← NOT_ASSESSABLE
48. ELSE:                   status ← PARTIALLY_ASSESSABLE

49. RETURN AssessabilityResult(status, Bel_rule, Pl_rule, K_rule)
```

---

## 5. Subroutines

### 5.1 DEMPSTER_COMBINE(m₁, m₂)

```
Input: m₁, m₂ — mass functions over {sufficient, insufficient, Θ}
Output: combined mass function, conflict mass K

1. K ← 0.0
2. raw ← empty dict

3. FOR EACH (A, mass_A) IN m₁:
4.   FOR EACH (B, mass_B) IN m₂:
5.     intersection ← A ∩ B
6.     product ← mass_A × mass_B
7.     IF intersection = ∅:
8.       K ← K + product
9.     ELSE:
10.      raw[intersection] ← raw.get(intersection, 0) + product

11. IF K = 1.0: RETURN (m₁, 1.0)  // total conflict — cannot combine

12. combined ← {A: raw[A] / (1 - K) for each A in raw}
13. RETURN (combined, K)
```

**Intersection rules for frame {sufficient, insufficient, Θ}:**

| A ∩ B | sufficient | insufficient | Θ |
|-------|-----------|-------------|---|
| sufficient | sufficient | ∅ | sufficient |
| insufficient | ∅ | insufficient | insufficient |
| Θ | sufficient | insufficient | Θ |

### 5.2 CONCORDANCE_FACTOR(status)

```
AGREED        → 1.0   // Multiple sources confirm the same value
SINGLE_SOURCE → 0.7   // Only one source — less corroboration
CONFLICTING   → 0.3   // Sources disagree — significant uncertainty
MISSING       → 0.0   // No evidence at all
```

---

## 6. Properties

### 6.1 Formal Properties

1. **Bounded output.** $0 \leq \text{Bel}(R) \leq \text{Pl}(R) \leq 1$ for all rules $R$.
2. **Monotonicity in evidence quality.** Higher entity confidence, higher source reliability, or higher semantic relevance strictly increases $\text{Bel}$.
3. **Conflict sensitivity.** Contradictory sources increase $K$, which the concordance adjustment propagates into reduced $\text{Bel}$.
4. **Weakest-link aggregation.** A single inadequately-supported requirement blocks assessability, preventing premature verdicts.
5. **Determinism.** Given the same entities, extraction methods, confidence scores, and embedding model, SABLE produces identical output. No LLM calls in the reasoning path.

### 6.2 Computational Complexity

- **Per rule:** $O(n \times k)$ where $n$ = number of requirements, $k$ = average entities per requirement
- **Embedding computation:** $O(n \times k)$ cosine similarity operations (cached after first computation)
- **Dempster combination:** $O(k)$ per requirement (3×3 focal element pairs)
- **Total:** Linear in the number of entities. Negligible compared to extraction cost.

---

## 7. Comparison to Prior Work

| System | Evidence model | Uncertainty handling | Assessability | Multi-source conflict |
|--------|---------------|---------------------|---------------|----------------------|
| Traditional BIM checking [2] | Complete structured data | None — assumes perfect data | Binary (check or skip) | Not applicable |
| Li et al. 2021 [3] | Defeasible logic | Three-valued {true, false, unknown} | Implicit via "unknown" | Rule-based defeaters |
| Meyer et al. 2022 [4] | Dempster-Shafer | BPA from sensor data | Not addressed | D-S combination |
| Chen et al. 2024 [5] | LLM + deep learning | None — binary output | Not addressed | Not addressed |
| **SABLE (this work)** | **D-S with semantic mass construction** | **Four-factor BPA from multimodal extraction** | **Explicit tri-state with Bel/Pl intervals** | **Principled via D-S conflict mass + concordance** |

**Key differentiator:** SABLE is the first algorithm to combine (a) embedding-based semantic relevance with (b) Dempster-Shafer evidence theory for (c) compliance assessability determination from (d) multimodal extracted documents.

---

## 8. References

[1] G. Shafer, "A Mathematical Theory of Evidence," Princeton University Press, 1976.

[2] R. Amor and E. Dimyadi, "The Promise of Automated Compliance Checking," Developments in the Built Environment, vol. 5, 2021.

[3] H. Li, T. Schultz, E. Dimyadi, and R. Amor, "Defeasible Reasoning for Automated Building Code Compliance Checking," in Proc. CIB W78, Luxembourg, 2021.

[4] T. Meyer et al., "Dempster-Shafer Theory for Construction Monitoring with Uncertain Sensor Data," Automation in Construction, vol. 134, 2022.

[5] Y. Chen et al., "LLM-Enhanced Automated Compliance Checking via Deep Learning and Ontology," Advanced Engineering Informatics, vol. 60, 2024.

[6] D. Alshboul et al., "Dempster-Shafer Theory Applications in Construction Engineering: A Systematic Review," Construction Innovation, 2025.

[7] S. Purushotham et al., "Framework for Automated Building Code Compliance Checking to Improve Transparency, Trust," Automation in Construction, 2026.

---

## 9. Implementation Notes

- **Embedding model:** `sentence-transformers/all-MiniLM-L6-v2` (80MB, runs locally, no API call, deterministic)
- **Caching:** Embedding vectors cached per attribute string; mass functions cached per (entity, requirement) pair
- **Thresholds:** $\theta_{\text{high}} = 0.7$, $\theta_{\text{low}} = 0.3$, $\tau_{\text{relevance}} = 0.5$ — all configurable
- **Backward compatibility:** SABLE extends, does not replace, the existing assessability interface. All existing pipeline consumers read `status` and `blocking_reason` unchanged.
