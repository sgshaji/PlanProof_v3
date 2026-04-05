# SABLE: Semantically-Augmented Belief Logic for Evidence

> A novel algorithm for evidence sufficiency assessment in multimodal regulatory compliance checking.
>
> SABLE acts as a **"Zero-Trust" gateway** for automated compliance — replacing the "Black Box" of LLM extraction with a **"Glass Box" of evidence logic**.

---

## 1. The Pre-Evaluation Paradox

In regulatory technology, the most dangerous state is not a "Fail." It is a **"Pass" based on hallucinated or misread evidence.** When an LLM confidently extracts a building height of 7.5m from a blurry scan — and the actual dimension was 11.5m — a traditional compliance system will issue a PASS verdict. The building gets built. The violation is discovered years later, or never.

This is the **Pre-Evaluation Paradox**: the system cannot know whether a rule evaluation is trustworthy until it knows whether the *evidence feeding that evaluation* is trustworthy. Every prior automated compliance system — from BIM-based checking to LLM-based extraction — skips this question entirely. They assume the data is correct and proceed to evaluate.

SABLE shifts the focus from *"Is the building compliant?"* to *"Is the evidence sufficient to even ask that question?"*

### Why existing approaches fail

Automated compliance checking in the built environment has traditionally assumed structured, complete data — typically from BIM systems where every dimension, material, and spatial relationship is machine-readable. These systems work when data is perfect.

Planning applications submitted to UK local authorities are not perfect. They arrive as bundles of unstructured documents: multi-page PDF application forms, scanned architectural drawings, handwritten annotations, and third-party certificates. Extracting structured data introduces uncertainty at every step:

- The OCR may misread "8.5m" as "85m" or miss it entirely
- The LLM may hallucinate an attribute that doesn't exist in the document
- Two documents in the same submission may state different values for the same measurement
- A critical measurement may simply be absent from all documents

Traditional systems have no mechanism to handle this. They either evaluate rules on whatever data is available (risking **false verdicts** — what we call "compliance washing," where high confidence in trivial attributes masks high uncertainty in critical ones) or refuse to evaluate entirely (producing blanket NOT_ASSESSABLE results that provide no value to planning officers).

**SABLE solves this by answering a question no prior system asks: "Is there sufficient trustworthy evidence to evaluate this rule — before attempting evaluation?"**

---

## 2. Mathematical Foundations

### 2.1 Dempster-Shafer Evidence Theory

SABLE is grounded in the Dempster-Shafer (D-S) theory of evidence [1], which generalises Bayesian probability to handle **epistemic uncertainty** — situations where evidence is incomplete or ambiguous.

Unlike Bayesian approaches that require a complete probability distribution over all hypotheses, D-S theory allows mass to be assigned to **subsets** of hypotheses, explicitly representing ignorance. This is critical for planning compliance: when an extraction pipeline returns a building height with moderate confidence, we don't know whether the evidence is sufficient or insufficient — we have genuine ignorance that should be modelled, not forced into a binary choice.

**Frame of discernment.** For each evidence requirement, we define:

$$\Theta = \{\text{sufficient}, \text{insufficient}\}$$

**Basic Probability Assignment (BPA).** A mass function $m: 2^\Theta \rightarrow [0, 1]$ assigns belief mass to subsets of $\Theta$:

- $m(\{\text{sufficient}\})$ — direct evidence that the requirement is met
- $m(\{\text{insufficient}\})$ — direct evidence that the requirement is not met
- $m(\Theta)$ — **ignorance** — evidence exists but is inconclusive

With constraints: $m(\emptyset) = 0$ and $\sum_{A \subseteq \Theta} m(A) = 1$.

**Belief and Plausibility.** From a mass function:

$$\text{Bel}(A) = \sum_{B \subseteq A} m(B) \quad \text{(lower bound of support)}$$

$$\text{Pl}(A) = \sum_{B \cap A \neq \emptyset} m(B) \quad \text{(upper bound of support)}$$

The interval $[\text{Bel}(\text{sufficient}), \text{Pl}(\text{sufficient})]$ represents the range of possible evidence sufficiency. The gap $\text{Pl} - \text{Bel}$ quantifies **residual uncertainty** — how much the system doesn't know.

### 2.2 Dempster's Rule of Combination

When multiple entities provide evidence for the same requirement, their mass functions are combined:

$$m_{1,2}(A) = \frac{1}{1-K} \sum_{B \cap C = A} m_1(B) \cdot m_2(C)$$

where the **conflict mass** $K$ measures source disagreement:

$$K = \sum_{B \cap C = \emptyset} m_1(B) \cdot m_2(C)$$

The only disjoint pairs in our frame are $\{\text{sufficient}\} \cap \{\text{insufficient}\} = \emptyset$ and vice versa, giving:

$$K = m_1(\{\text{suf}\}) \cdot m_2(\{\text{ins}\}) + m_1(\{\text{ins}\}) \cdot m_2(\{\text{suf}\})$$

High $K$ is a principled signal for conflicting evidence — a reason to flag NOT_ASSESSABLE rather than produce an unreliable verdict.

**Intersection table for frame $\{\text{sufficient}, \text{insufficient}, \Theta\}$:**

| $A \cap B$ | sufficient | insufficient | $\Theta$ |
|------------|-----------|-------------|----------|
| sufficient | sufficient | $\emptyset$ | sufficient |
| insufficient | $\emptyset$ | insufficient | insufficient |
| $\Theta$ | sufficient | insufficient | $\Theta$ |

---

## 3. The SABLE Algorithm

### 3.1 Novel Contribution: Four-Factor Mass Function Construction

SABLE's primary contribution is the **mass function construction layer** — a novel procedure that decomposes extraction uncertainty into four interpretable, orthogonal dimensions:

| Dimension | Symbol | Source | What it captures |
|-----------|--------|--------|-----------------|
| **Source reliability** | $\rho_i$ | Per-method/per-type calibrated thresholds | How reliable is the extraction method? |
| **Extraction confidence** | $c_i$ | Extractor self-assessed certainty | How confident is the extractor about this specific extraction? |
| **Semantic relevance** | $r_i$ | Embedding cosine similarity | Does this entity actually relate to the required attribute? |
| **Cross-source concordance** | $\gamma_j$ | Pairwise reconciliation status | Do multiple sources agree on this attribute? |

**To our knowledge, no prior work combines embedding-based semantic relevance scoring with Dempster-Shafer evidence theory for regulatory compliance assessability determination.**

### 3.2 Mass Function Construction

For each entity $e_i$ matched to requirement $R_j$, with $\rho_i, c_i, r_i \in [0, 1]$:

$$m_i(\{\text{sufficient}\}) = \rho_i \cdot c_i \cdot r_i$$

$$m_i(\{\text{insufficient}\}) = (1 - \rho_i)(1 - c_i)(1 - r_i)$$

$$m_i(\Theta) = 1 - m_i(\{\text{sufficient}\}) - m_i(\{\text{insufficient}\})$$

**Intuition:** An entity contributes strong "sufficient" evidence only when the extraction method is reliable ($\rho_i$ high), the extractor is confident ($c_i$ high), AND the extracted attribute is semantically relevant to the requirement ($r_i$ high). If any dimension is weak, mass shifts to ignorance ($m_i(\Theta)$), not to "insufficient" — reflecting genuine uncertainty rather than negative evidence.

The "insufficient" mass is only large when ALL three dimensions are low — the method is unreliable, the extractor is uncertain, and the attribute is semantically unrelated. This is the appropriate signal for negative evidence.

### 3.3 Algorithmic Steps

**Step 1 — Source filtering.** For each requirement $R_j$, filter entities by `acceptable_sources` (e.g., "FORM", "DRAWING").

**Step 2 — Semantic relevance gating.** Compute $r_i = \cos(\text{embed}(e_i.\text{attribute}), \text{embed}(R_j.\text{attribute}))$. Discard entities with $r_i < \tau_{\text{relevance}}$ (default 0.5). The embedding model is a fixed, locally-loaded checkpoint (`all-MiniLM-L6-v2`) — deterministic, no LLM call, no circular dependency.

**Step 3 — Confidence gating.** Filter by per-method confidence thresholds. Entities below the threshold are removed.

**Step 4 — Mass function construction.** For each surviving entity, compute the three-valued BPA as above.

**Step 5 — Dempster combination.** Combine mass functions from multiple entities providing evidence for the same requirement:

$$m_j = m_1 \oplus m_2 \oplus \cdots \oplus m_k$$

**Step 6 — Concordance adjustment.** Adjust combined belief by cross-source agreement:

$$B_j = \gamma_j \cdot \text{Bel}_j$$

where $\gamma_j$ is determined by reconciliation status:

| Status | $\gamma_j$ | Meaning |
|--------|-----------|---------|
| AGREED | 1.0 | Multiple sources confirm the same value |
| SINGLE_SOURCE | 0.7 | Only one source — less corroboration |
| CONFLICTING | 0.3 | Sources disagree — significant uncertainty |
| MISSING | 0.0 | No evidence at all |

**Step 7 — Weakest-link aggregation.** Across all requirements:

$$B_{\text{rule}} = \min_{j=1}^{k} B_j, \quad \text{Pl}_{\text{rule}} = \min_{j=1}^{k} \text{Pl}_j, \quad K_{\text{rule}} = \max_{j=1}^{k} K_j$$

A rule is only as assessable as its least-supported requirement.

**Step 8 — Three-state decision.**

$$\text{status}(R) = \begin{cases} \text{ASSESSABLE} & \text{if } B_{\text{rule}} \geq \theta_{\text{high}} \\ \text{NOT\_ASSESSABLE} & \text{if } \text{Pl}_{\text{rule}} \leq \theta_{\text{low}} \\ \text{PARTIALLY\_ASSESSABLE} & \text{otherwise} \end{cases}$$

Default thresholds: $\theta_{\text{high}} = 0.7$, $\theta_{\text{low}} = 0.3$.

The **PARTIALLY_ASSESSABLE** state — absent from all prior compliance checking systems — enables graduated evidence requests: "You're close — provide one additional measurement to confirm."

---

## 4. Algorithm Pseudocode

```
Algorithm SABLE(rule R, entities E, graph G, embeddings model φ)
─────────────────────────────────────────────────────────────────

Input:
  R: RuleConfig with required_evidence = {R₁, R₂, ..., Rₙ}
  E: list[ExtractedEntity] from evidence provider
  G: SNKG for structured evidence retrieval
  φ: sentence embedding model for semantic similarity

Output:
  result: AssessabilityResult with (status, belief, plausibility, conflict_mass)

1.  requirement_beliefs ← empty list

2.  FOR EACH requirement Rⱼ IN R.required_evidence:

3.      matched ← FILTER(E, by source type matching Rⱼ.acceptable_sources)

4.      // SEMANTIC RELEVANCE GATING
5.      FOR EACH entity eᵢ IN matched:
6.          rᵢ ← cosine_similarity(φ(eᵢ.attribute), φ(Rⱼ.attribute))
7.          IF rᵢ < τ_relevance:  REMOVE eᵢ from matched

8.      IF matched IS EMPTY:
9.          requirement_beliefs.APPEND((0.0, 1.0, 0.0))  // no evidence
10.         CONTINUE

11.     // CONFIDENCE GATING
12.     trusted ← FILTER(matched, by confidence ≥ threshold[method][type])
13.     IF trusted IS EMPTY:
14.         requirement_beliefs.APPEND((0.0, 0.5, 0.0))  // untrusted evidence
15.         CONTINUE

16.     // MASS FUNCTION CONSTRUCTION (Novel four-factor BPA)
17.     mass_functions ← empty list
18.     FOR EACH entity eᵢ IN trusted:
19.         ρᵢ ← threshold_lookup[eᵢ.extraction_method][eᵢ.entity_type]
20.         cᵢ ← eᵢ.confidence
21.         rᵢ ← cosine_similarity(φ(eᵢ.attribute), φ(Rⱼ.attribute))
22.         m_suf ← ρᵢ × cᵢ × rᵢ
23.         m_ins ← (1 - ρᵢ) × (1 - cᵢ) × (1 - rᵢ)
24.         m_ign ← 1 - m_suf - m_ins
25.         mass_functions.APPEND({sufficient: m_suf, insufficient: m_ins, Θ: m_ign})

26.     // DEMPSTER COMBINATION
27.     combined ← mass_functions[0]
28.     K_total ← 0.0
29.     FOR i ← 1 TO len(mass_functions) - 1:
30.         combined, K ← DEMPSTER_COMBINE(combined, mass_functions[i])
31.         K_total ← max(K_total, K)

32.     Belⱼ ← combined[sufficient]
33.     Plⱼ  ← 1 - combined[insufficient]

34.     // CONCORDANCE ADJUSTMENT
35.     reconciled ← reconciler.reconcile(trusted, Rⱼ.attribute)
36.     γⱼ ← CONCORDANCE_FACTOR(reconciled.status)
37.     Bⱼ ← Belⱼ × γⱼ

38.     requirement_beliefs.APPEND((Bⱼ, Plⱼ, K_total))

39. // WEAKEST-LINK AGGREGATION
40. B_rule  ← MIN(Bⱼ for all j)
41. Pl_rule ← MIN(Plⱼ for all j)
42. K_rule  ← MAX(Kⱼ for all j)

43. // THREE-STATE DECISION
44. IF B_rule ≥ θ_high:   status ← ASSESSABLE
45. ELIF Pl_rule ≤ θ_low:  status ← NOT_ASSESSABLE
46. ELSE:                   status ← PARTIALLY_ASSESSABLE

47. RETURN AssessabilityResult(status, B_rule, Pl_rule, K_rule)
```

---

## 5. Formal Properties and Proofs

### 5.1 Definitions

Let $E = \{e_1, \ldots, e_n\}$ be the set of extracted entities matched to requirement $R_j$ (after source filtering, confidence gating, and semantic relevance gating). For each entity $e_i \in E$:

- $\rho_i \in [0, 1]$: source reliability weight
- $c_i \in [0, 1]$: extraction confidence
- $r_i \in [\tau_{\text{relevance}}, 1]$: semantic relevance (gated at $\tau = 0.5$)

Combined mass after $n$ entities: $m^{(n)} = m_1 \oplus m_2 \oplus \cdots \oplus m_n$

Combined belief: $\text{Bel}_j = m^{(n)}(\{\text{sufficient}\})$

Adjusted belief: $B_j = \gamma_j \cdot \text{Bel}_j$

Rule-level belief: $B_{\text{rule}} = \min_{j=1}^{k} B_j$

---

### Theorem 1 (Boundedness)

**Statement.** For any set of entities $E$ and requirement $R_j$ with concordance factor $\gamma_j \in [0, 1]$:

$$0 \leq B_j \leq \text{Pl}_j \leq 1$$

**Proof.**

*Step 1: Each mass function is a valid BPA.* For any entity $e_i$ with $\rho_i, c_i, r_i \in [0, 1]$:

- $m_i(\{\text{suf}\}) = \rho_i c_i r_i \geq 0$
- $m_i(\{\text{ins}\}) = (1-\rho_i)(1-c_i)(1-r_i) \geq 0$
- $m_i(\{\text{suf}\}) + m_i(\{\text{ins}\}) \leq 1$ since expanding gives all cross-terms non-negative
- $m_i(\Theta) = 1 - m_i(\{\text{suf}\}) - m_i(\{\text{ins}\}) \in [0, 1]$
- Sum: $m_i(\{\text{suf}\}) + m_i(\{\text{ins}\}) + m_i(\Theta) = 1$

Each $m_i$ is a valid BPA.

*Step 2: Dempster combination preserves validity.* By induction. If $m^{(n)}$ is valid, unnormalised masses after combination are $\hat{m}(A) = \sum_{B \cap C = A} m^{(n)}(B) \cdot m_{n+1}(C) \geq 0$. Since $\sum_A \hat{m}(A) + K = 1$ and $K \geq 0$, normalising by $1-K$ (when $K < 1$) gives a valid BPA. The implementation returns $m^{(n)}$ unchanged when $K \geq 1$.

*Step 3: Belief ordering.* $\text{Bel}_j = m^{(n)}(\{\text{suf}\}) \in [0,1]$. $\text{Pl}_j = 1 - m^{(n)}(\{\text{ins}\}) \in [0,1]$. $\text{Bel}_j \leq \text{Pl}_j$ because $m^{(n)}(\Theta) \geq 0$.

*Step 4: Concordance preserves bounds.* $B_j = \gamma_j \cdot \text{Bel}_j$ with $\gamma_j \in [0,1]$, so $B_j \in [0,1]$.

*Step 5: Aggregation preserves bounds.* $B_{\text{rule}} = \min_j B_j \in [0,1]$. $\blacksquare$

---

### Theorem 2 (Monotonicity)

**Statement.** Adding a new entity $e_{n+1}$ with $r_{n+1} \geq \tau_{\text{relevance}}$, $c_{n+1} > 0$, and $\rho_{n+1} > 0$ cannot decrease the combined belief:

$$\text{Bel}_j^{(n+1)} \geq \text{Bel}_j^{(n)}$$

**Proof.**

After combining $m^{(n)}$ with $m_{n+1}$:

$$m^{(n+1)}(\{\text{suf}\}) = \frac{m_{n+1}(\{\text{suf}\}) \cdot (1 - m^{(n)}(\{\text{ins}\})) + m^{(n)}(\{\text{suf}\}) \cdot m_{n+1}(\Theta)}{1 - K}$$

To show $m^{(n+1)}(\{\text{suf}\}) \geq m^{(n)}(\{\text{suf}\})$, it suffices to show the numerator $\geq m^{(n)}(\{\text{suf}\}) \cdot (1-K)$. Rearranging, the sufficient condition is:

$$m_{n+1}(\{\text{suf}\}) \cdot m^{(n)}(\Theta) \geq 0$$

This holds since both factors are non-negative. The inequality is strict whenever $m_{n+1}(\{\text{suf}\}) > 0$ (guaranteed by $\rho_{n+1}, c_{n+1}, r_{n+1} > 0$) and $m^{(n)}(\Theta) > 0$ (the generic case during evidence accumulation). $\blacksquare$

**Corollary.** More positive evidence always helps. The system never becomes *less* confident in assessability when presented with additional trustworthy, relevant evidence.

---

### Theorem 3 (Determinism)

**Statement.** Given identical inputs $(E, R_j, \phi, \gamma_j)$, SABLE always produces the same output $(B_j, \text{Pl}_j, K_j)$.

**Proof.**

Every computational step is a deterministic function:

1. **Mass construction:** $\rho_i$ is a table lookup; $c_i$ is a field read; $r_i = \cos(\phi(e_i.\text{attr}), \phi(R_j.\text{attr}))$ uses a fixed embedding model — no LLM calls, no sampling, no external API.
2. **Dempster combination:** Commutative and associative (Shafer 1976, Theorem 3.1). The implementation applies left-to-right over a deterministically-ordered list.
3. **Concordance:** A pure dict lookup on an immutable mapping.
4. **Threshold comparison:** IEEE 754 arithmetic on deterministic values.

The composition of deterministic functions is deterministic. $\blacksquare$

**Significance.** Determinism is essential for regulatory compliance: the same application must always receive the same assessment, regardless of when or how many times it is processed. SABLE achieves this without sacrificing the expressiveness of D-S theory.

---

### Theorem 4 (Graceful Degradation)

**Statement.** As extraction confidence $c_i \to 0$ for all entities, the combined belief $\text{Bel}_j \to 0$.

**Proof.**

As $c_i \to 0$: $m_i(\{\text{suf}\}) = \rho_i \cdot c_i \cdot r_i \to 0$. For mass functions with $m_i(\{\text{suf}\}) = 0$, Dempster combination cannot produce positive $m^{(n)}(\{\text{suf}\})$ (by induction on the intersection table: the only terms producing $\{\text{suf}\}$ involve at least one factor of $m(\{\text{suf}\})$). Therefore $\text{Bel}_j \to 0$, and $B_j = \gamma_j \cdot 0 = 0$.

By arithmetic continuity of the mass function and Dempster normalisation (a rational function, continuous away from $K=1$), the degradation is smooth. $\blacksquare$

**Significance.** SABLE never asserts assessability on unreliable evidence. As extraction quality degrades, the system gracefully transitions from ASSESSABLE through PARTIALLY_ASSESSABLE to NOT_ASSESSABLE — giving planning officers a principled signal that more evidence is needed.

---

### Theorem 5 (Weakest-Link Aggregation)

**Statement.** $B_{\text{rule}} = \min_{j=1}^{k} B_j$ and cannot exceed the belief of the least-supported requirement.

**Proof.** This is definitional (algorithmic design choice). The min-aggregation implements **conjunctive semantics**: a rule requires evidence for ALL requirements. A single missing requirement blocks the entire rule.

*Design rationale.* Alternative aggregations (average, product) would allow a well-evidenced requirement to compensate for a missing one — semantically incorrect for regulatory compliance where every requirement is mandatory. The weakest-link approach is analogous to the conjunctive t-norm in fuzzy logic, applied as a hard lower-bound. $\blacksquare$

**Corollary.** Improving evidence for any requirement with $B_j > B_{\text{rule}}$ has no effect. The only way to improve $B_{\text{rule}}$ is to strengthen the weakest link.

---

## 6. Computational Complexity

| Operation | Complexity | Notes |
|-----------|-----------|-------|
| Per-entity mass construction | $O(1)$ | Three multiplications + embedding lookup (cached) |
| Semantic relevance | $O(d)$ | Cosine similarity on $d$-dimensional embeddings |
| Dempster combination per requirement | $O(k)$ | $k$ entities, $3 \times 3$ focal element pairs each |
| Per rule (total) | $O(n \times k)$ | $n$ requirements, $k$ average entities each |
| Embedding cache | $O(|V|)$ | $|V|$ = unique attribute vocabulary size |

Total: **linear in the number of entities**. Negligible compared to extraction cost (LLM/VLM API calls).

---

## 7. Comparison to Prior Work

| System | Evidence model | Uncertainty | Assessability | Multi-source conflict |
|--------|---------------|------------|---------------|----------------------|
| Traditional BIM [2] | Complete structured data | None | Binary | N/A |
| Li et al. 2021 [3] | Defeasible logic | Three-valued | Implicit via "unknown" | Rule-based defeaters |
| Meyer et al. 2022 [4] | Dempster-Shafer | BPA from sensors | Not addressed | D-S combination |
| Chen et al. 2024 [5] | LLM + deep learning | None — binary | Not addressed | Not addressed |
| **SABLE** | **D-S with four-factor semantic BPA** | **Continuous Bel/Pl intervals** | **Explicit tri-state** | **D-S conflict mass + concordance** |

**Key differentiator:** SABLE is the first algorithm to combine (a) embedding-based semantic relevance with (b) Dempster-Shafer evidence theory for (c) compliance assessability determination from (d) multimodal extracted documents.

---

## 8. Properties Summary

| Property | Statement | Proof technique | Significance |
|----------|-----------|-----------------|--------------|
| **Boundedness** | $0 \leq B_j \leq \text{Pl}_j \leq 1$ | BPA validity + induction | Outputs always interpretable |
| **Monotonicity** | More evidence $\Rightarrow$ higher belief | D-S numerator dominance | System improves with data |
| **Determinism** | Same inputs → same output | Composition of pure functions | Regulatory reproducibility |
| **Graceful degradation** | Low confidence → NOT_ASSESSABLE | Limiting BPA analysis | Never evaluates on bad data |
| **Weakest-link** | $B_{\text{rule}} = \min_j B_j$ | Definitional (conjunctive) | One gap blocks the rule |

---

## 9. References

[1] G. Shafer, *A Mathematical Theory of Evidence*, Princeton University Press, 1976.

[2] R. Amor and E. Dimyadi, "The Promise of Automated Compliance Checking," *Developments in the Built Environment*, vol. 5, 2021.

[3] H. Li, T. Schultz, E. Dimyadi, and R. Amor, "Defeasible Reasoning for Automated Building Code Compliance Checking," Proc. CIB W78, Luxembourg, 2021.

[4] T. Meyer et al., "Dempster-Shafer Theory for Construction Monitoring with Uncertain Sensor Data," *Automation in Construction*, vol. 134, 2022.

[5] Y. Chen et al., "LLM-Enhanced Automated Compliance Checking via Deep Learning and Ontology," *Advanced Engineering Informatics*, vol. 60, 2024.

[6] D. Alshboul et al., "Dempster-Shafer Theory Applications in Construction Engineering: A Systematic Review," *Construction Innovation*, 2025.

[7] S. Purushotham et al., "Framework for Automated Building Code Compliance Checking to Improve Transparency, Trust," *Automation in Construction*, 2026.

[8] P. Smets and R. Kennes, "The Transferable Belief Model," *Artificial Intelligence*, vol. 66, no. 2, pp. 191–234, 1994.

[9] F. Voorbraak, "On the Justification of Dempster's Rule of Combination," *Artificial Intelligence*, vol. 48, no. 2, pp. 171–197, 1991.

---

## 10. Known Challenges and Open Questions

### 10.1 The Calibration Problem

The source reliability weight ($\rho_i$) is the most sensitive parameter. If $\rho_i$ for scanned drawings is set too high, the system will be overconfident on noisy extractions. If too low, everything becomes PARTIALLY_ASSESSABLE. Current weights are hardcoded per extraction method — empirical calibration from extraction accuracy on real data is needed. A reliability diagram (predicted confidence vs actual accuracy) would validate or correct these weights.

### 10.2 Semantic Overlap

Cosine similarity ($r_i$) can conflate semantically close but physically different measurements. In architectural documents, "Floor Height" and "Ceiling Height" are close in embedding space but represent different measurements. A domain-aware synonym/exclusion table augmenting the embedding similarity — or an ontology-aware check — would reduce false positive matches without abandoning the embedding approach.

### 10.3 Explainability for Planning Officers

While SABLE tracks per-requirement belief, plausibility, conflict mass, and blocking reason internally, a planning officer needs natural language: "Certificate type is missing from the application form" rather than "R_j.attribute=certificate_type, status=MISSING_EVIDENCE." Generating human-readable assessment explanations from SABLE's structured output is a presentation-layer concern, but critical for adoption.

---

## 11. Future Scope: Automated Requests for Further Information (RFIs)

The PARTIALLY_ASSESSABLE state directly maps to an operational capability that does not exist in any current planning validation system: **automated generation of Requests for Further Information**.

When SABLE determines a rule is PARTIALLY_ASSESSABLE, it already knows:

1. **Which requirement** is the weakest link ($j^* = \arg\min_j B_j$)
2. **Why it's weak** — MISSING (no evidence), LOW_CONFIDENCE (evidence exists but untrustworthy), or CONFLICTING (sources disagree)
3. **What would fix it** — the requirement's `acceptable_sources` specifies which document type to request

This enables RFIs such as:

> *"Your application for 65 Sir Harrys Road (PP-14532213) cannot be fully validated. The following information is needed:*
> - *Building height measurement: No dimension annotation was found on the submitted elevation drawings. Please provide an annotated elevation showing the proposed ridge height.*
> - *Site boundary area: The stated site area on the application form (450m²) conflicts with the Land Registry parcel area (320m²). Please clarify the discrepancy."*

This is exactly how planning officers currently write RFIs — but manually, after reading every document. SABLE automates the triage:

| SABLE Status | Action | Human involvement |
|-------------|--------|-------------------|
| ASSESSABLE | Proceed to rule evaluation | None at this stage |
| PARTIALLY_ASSESSABLE | Generate targeted RFI specifying evidence gaps | Officer reviews and sends |
| NOT_ASSESSABLE | Generate comprehensive RFI listing all missing requirements | Officer reviews and sends |

The path from research prototype to operational deployment is: ASSESSABLE applications go straight to automated rule evaluation, NOT_ASSESSABLE applications receive automated RFIs, and PARTIALLY_ASSESSABLE applications are flagged for officer review with a specific evidence gap report. This transforms SABLE from a validation algorithm into a **workflow automation system** that reduces planning officer workload on the ~60% of applications that are straightforward, while focusing human attention on the ~40% that genuinely need expert judgment.
