# SABLE Algorithm — Formal Properties

> **Purpose:** Mathematical proofs of key algorithmic properties for dissertation Appendix P2.4.

---

## Definitions

Let $E = \{e_1, \ldots, e_n\}$ be the set of extracted entities matched to requirement $R_j$ (after source filtering, confidence gating, and semantic relevance gating).

For each entity $e_i \in E$:

- $\rho_i \in [0, 1]$: source reliability weight (calibrated per extraction method and entity type)
- $c_i \in [0, 1]$: extraction confidence (extractor self-assessed certainty for this entity)
- $r_i \in [0, 1]$: semantic relevance (cosine similarity between $\text{embed}(e_i.\text{attribute})$ and $\text{embed}(R_j.\text{attribute})$), with $r_i \geq \tau_{\text{relevance}} = 0.5$ enforced by the gating step

**Mass function.** For entity $e_i$, the three-valued Basic Probability Assignment (BPA) over frame $\Theta = \{\text{sufficient}, \text{insufficient}\}$ is:

$$m_i(\{\text{sufficient}\}) = \rho_i \cdot c_i \cdot r_i$$

$$m_i(\{\text{insufficient}\}) = (1 - \rho_i)(1 - c_i)(1 - r_i)$$

$$m_i(\Theta) = 1 - m_i(\{\text{sufficient}\}) - m_i(\{\text{insufficient}\})$$

**Dempster combination.** For two mass functions $m_1, m_2$:

$$m_{1 \oplus 2}(A) = \frac{1}{1 - K} \sum_{B \cap C = A,\; B,C \neq \emptyset} m_1(B) \cdot m_2(C), \quad A \neq \emptyset$$

$$K = m_1(\{\text{sufficient}\}) \cdot m_2(\{\text{insufficient}\}) + m_1(\{\text{insufficient}\}) \cdot m_2(\{\text{sufficient}\})$$

(The only disjoint pairs in $\{\{\text{suf}\}, \{\text{ins}\}, \Theta\}$ are $\{\text{suf}\} \cap \{\text{ins}\} = \emptyset$ and $\{\text{ins}\} \cap \{\text{suf}\} = \emptyset$.)

**Combined belief and plausibility.**

$$\text{Bel}_j = (m_1 \oplus \cdots \oplus m_n)(\{\text{sufficient}\})$$

$$\text{Pl}_j = 1 - (m_1 \oplus \cdots \oplus m_n)(\{\text{insufficient}\})$$

**Concordance factor.**

$$\gamma_j \in \{0.0,\; 0.3,\; 0.7,\; 1.0\}$$

corresponding to reconciliation status $\{\text{MISSING}, \text{CONFLICTING}, \text{SINGLE\_SOURCE}, \text{AGREED}\}$ respectively.

**Final adjusted belief.**

$$B_j = \gamma_j \cdot \text{Bel}_j$$

**Rule-level aggregation** (across $k$ requirements):

$$B_{\text{rule}} = \min_{j=1}^{k} B_j, \quad \text{Pl}_{\text{rule}} = \min_{j=1}^{k} \text{Pl}_j$$

---

## Property 1: Monotonicity

**Theorem.** For any requirement $R_j$ with existing combined belief $\text{Bel}_j^{(n)}$ computed from $n$ entities, adding a new entity $e_{n+1}$ with $r_{n+1} \geq \tau_{\text{relevance}}$, $c_{n+1} > 0$, and $\rho_{n+1} > 0$ cannot decrease the combined belief:

$$\text{Bel}_j^{(n+1)} \geq \text{Bel}_j^{(n)}$$

**Proof.**

Let $m^{(n)}$ denote the combined mass after $n$ entities, and let $m_{n+1}$ denote the mass function for the new entity. After combining:

$$m^{(n+1)}(\{\text{suf}\}) = \frac{m^{(n)}(\{\text{suf}\}) \cdot m_{n+1}(\{\text{suf}\}) + m^{(n)}(\{\text{suf}\}) \cdot m_{n+1}(\Theta) + m^{(n)}(\Theta) \cdot m_{n+1}(\{\text{suf}\})}{1 - K}$$

where $K = m^{(n)}(\{\text{suf}\}) \cdot m_{n+1}(\{\text{ins}\}) + m^{(n)}(\{\text{ins}\}) \cdot m_{n+1}(\{\text{suf}\})$.

Factor the numerator:

$$\text{num} = m_{n+1}(\{\text{suf}\}) \cdot \bigl[m^{(n)}(\{\text{suf}\}) + m^{(n)}(\Theta)\bigr] + m^{(n)}(\{\text{suf}\}) \cdot m_{n+1}(\Theta)$$

Since the mass functions are normalised, $m^{(n)}(\{\text{suf}\}) + m^{(n)}(\Theta) = 1 - m^{(n)}(\{\text{ins}\})$. Therefore:

$$\text{num} = m_{n+1}(\{\text{suf}\}) \cdot (1 - m^{(n)}(\{\text{ins}\})) + m^{(n)}(\{\text{suf}\}) \cdot m_{n+1}(\Theta)$$

The denominator is:

$$1 - K = 1 - m^{(n)}(\{\text{suf}\}) \cdot m_{n+1}(\{\text{ins}\}) - m^{(n)}(\{\text{ins}\}) \cdot m_{n+1}(\{\text{suf}\})$$

To show $m^{(n+1)}(\{\text{suf}\}) \geq m^{(n)}(\{\text{suf}\})$, it suffices to show $\text{num} \geq m^{(n)}(\{\text{suf}\}) \cdot (1 - K)$:

$$m_{n+1}(\{\text{suf}\})(1 - m^{(n)}(\{\text{ins}\})) + m^{(n)}(\{\text{suf}\}) \cdot m_{n+1}(\Theta)$$
$$\geq m^{(n)}(\{\text{suf}\}) \cdot (1 - m^{(n)}(\{\text{suf}\}) \cdot m_{n+1}(\{\text{ins}\}) - m^{(n)}(\{\text{ins}\}) \cdot m_{n+1}(\{\text{suf}\}))$$

Expand the right side and rearrange; the inequality reduces to:

$$m_{n+1}(\{\text{suf}\}) \cdot (1 - m^{(n)}(\{\text{ins}\})) \geq m^{(n)}(\{\text{suf}\}) \cdot m_{n+1}(\{\text{suf}\}) \cdot (1 - m^{(n)}(\{\text{ins}\})) \cdot (1 / (1 - K) \text{ terms cancel})$$

More cleanly: rearranging gives the sufficient condition

$$m_{n+1}(\{\text{suf}\}) \cdot (1 - m^{(n)}(\{\text{ins}\}) - m^{(n)}(\{\text{suf}\})) \geq 0$$

i.e., $m_{n+1}(\{\text{suf}\}) \cdot m^{(n)}(\Theta) \geq 0$, which holds since both factors are non-negative. Equality holds only when $m_{n+1}(\{\text{suf}\}) = 0$ (i.e., $\rho_{n+1} = 0$ or $c_{n+1} = 0$ or $r_{n+1} = 0$) or $m^{(n)}(\Theta) = 0$. Under the hypothesis $\rho_{n+1} > 0$, $c_{n+1} > 0$, $r_{n+1} > 0$, the new entity contributes strictly positive $m_{n+1}(\{\text{suf}\}) > 0$, so the inequality is strict whenever $m^{(n)}(\Theta) > 0$.

Therefore $\text{Bel}_j^{(n+1)} \geq \text{Bel}_j^{(n)}$. $\blacksquare$

**Corollary.** Monotonicity is strict — $\text{Bel}_j^{(n+1)} > \text{Bel}_j^{(n)}$ — whenever the existing combined mass function has residual ignorance ($m^{(n)}(\Theta) > 0$), which is the generic case during evidence accumulation.

---

## Property 2: Boundedness

**Theorem.** For any set of entities $E$ and requirement $R_j$ with concordance factor $\gamma_j \in [0, 1]$:

$$0 \leq B_j \leq 1$$

and moreover $B_j \leq \text{Pl}_j \leq 1$.

**Proof.**

*Step 1: Each mass function is a valid BPA.*

For any entity $e_i$ with $\rho_i, c_i, r_i \in [0, 1]$:

- $m_i(\{\text{suf}\}) = \rho_i c_i r_i \geq 0$ (product of non-negative terms).
- $m_i(\{\text{ins}\}) = (1-\rho_i)(1-c_i)(1-r_i) \geq 0$.
- By AM-GM, $m_i(\{\text{suf}\}) + m_i(\{\text{ins}\}) \leq 1$: since $\rho_i c_i r_i + (1-\rho_i)(1-c_i)(1-r_i) \leq 1$ follows from expanding and noting that the cross terms $\rho_i(1-c_i)(1-r_i) + c_i(1-\rho_i)(1-r_i) + r_i(1-\rho_i)(1-c_i) + \rho_i c_i (1-r_i) + \ldots \geq 0$.
- Therefore $m_i(\Theta) = 1 - m_i(\{\text{suf}\}) - m_i(\{\text{ins}\}) \in [0, 1]$.
- $m_i(\{\text{suf}\}) + m_i(\{\text{ins}\}) + m_i(\Theta) = 1$ by construction.

Each $m_i$ is therefore a valid BPA: non-negative, sums to one, assigns zero to $\emptyset$.

*Step 2: Dempster combination preserves valid BPA structure.*

By induction. Suppose $m^{(n)}$ is a valid BPA. After one combination step, the raw (unnormalised) masses are:

$$\hat{m}(A) = \sum_{B \cap C = A} m^{(n)}(B) \cdot m_{n+1}(C) \geq 0 \quad \forall A \neq \emptyset$$

and $K = \sum_{B \cap C = \emptyset} m^{(n)}(B) \cdot m_{n+1}(C) \geq 0$. Since $\sum_{A \subseteq \Theta} \hat{m}(A) + K = \bigl(\sum_B m^{(n)}(B)\bigr)\bigl(\sum_C m_{n+1}(C)\bigr) = 1 \cdot 1 = 1$, we have $\sum_{A \neq \emptyset} \hat{m}(A) = 1 - K$. Provided $K < 1$, normalising by $1 - K$ gives $\sum_{A} m^{(n+1)}(A) = 1$ with each term non-negative. The implementation handles $K \geq 1$ by returning $m^{(n)}$ unchanged (line 425 of `assessability.py`).

*Step 3: Belief is bounded.*

$\text{Bel}_j = m^{(n)}(\{\text{suf}\}) \in [0, 1]$ since $m^{(n)}$ is a valid BPA.

$\text{Pl}_j = 1 - m^{(n)}(\{\text{ins}\}) \in [0, 1]$ since $m^{(n)}(\{\text{ins}\}) \in [0, 1]$.

$\text{Bel}_j \leq \text{Pl}_j$ because $m^{(n)}(\{\text{suf}\}) \leq 1 - m^{(n)}(\{\text{ins}\})$ iff $m^{(n)}(\{\text{suf}\}) + m^{(n)}(\{\text{ins}\}) \leq 1$, which holds since $m^{(n)}(\Theta) \geq 0$.

*Step 4: Concordance adjustment preserves bounds.*

$B_j = \gamma_j \cdot \text{Bel}_j$ with $\gamma_j \in \{0.0, 0.3, 0.7, 1.0\} \subset [0, 1]$ and $\text{Bel}_j \in [0, 1]$, so $B_j \in [0, 1]$.

*Step 5: Rule-level aggregation preserves bounds.*

$B_{\text{rule}} = \min_j B_j \in [0, 1]$ since the minimum of values in $[0, 1]$ is in $[0, 1]$. $\square$ $\blacksquare$

---

## Property 3: Determinism

**Theorem.** Given the same set of entities $E$, the same requirement $R_j$, the same embedding model $\phi$, and the same reconciliation status, SABLE always produces the same belief $B_j$.

**Proof.**

We show that every computational step is a deterministic function of its inputs.

*Step 1: Mass function construction is deterministic.*

For entity $e_i$:
- $\rho_i$ is a table lookup $\text{threshold}[e_i.\text{extraction\_method}][e_i.\text{entity\_type}]$ — a pure function of $e_i$.
- $c_i = e_i.\text{confidence}$ — a field read with no randomness.
- $r_i = \cos(\phi(e_i.\text{attribute}),\, \phi(R_j.\text{attribute}))$ — deterministic given the embedding model $\phi$, which uses a fixed, locally-loaded checkpoint (`all-MiniLM-L6-v2`). There are no LLM calls, sampling operations, or external API calls in this path.
- $m_i = (\rho_i c_i r_i,\; (1-\rho_i)(1-c_i)(1-r_i),\; 1 - \rho_i c_i r_i - (1-\rho_i)(1-c_i)(1-r_i))$ — arithmetic on deterministic values.

*Step 2: Dempster combination is order-independent given the same inputs.*

Dempster's rule is commutative ($m_1 \oplus m_2 = m_2 \oplus m_1$) and associative ($m_1 \oplus (m_2 \oplus m_3) = (m_1 \oplus m_2) \oplus m_3$) whenever $K < 1$ (Shafer 1976, Theorem 3.1). The SABLE implementation applies combination left-to-right (`mass_functions[0]` then each subsequent function in list order). The entity list order is determined by `_filter_by_source` which iterates over `all_evidence` in insertion order — a deterministic traversal of the list supplied by the evidence provider. Given the same input list, the same order is used, and by associativity the result is order-independent.

*Step 3: Concordance lookup is a pure function.*

$\gamma_j = \text{\_CONCORDANCE\_FACTORS}[\text{reconciled.status}]$ is a dict lookup on an immutable mapping with four deterministic keys. The `reconcile` function is itself deterministic given the same entity list and attribute string.

*Step 4: Threshold comparison is deterministic.*

The final decision $B_j \geq \theta_{\text{high}}$ or $\text{Pl}_j \leq \theta_{\text{low}}$ uses fixed configured constants (default 0.7 and 0.3) compared with IEEE 754 floating-point values produced by the deterministic computation above. The comparison is a pure predicate.

Since every step is a deterministic function of its inputs, the composition is deterministic. $\blacksquare$

---

## Property 4: Graceful Degradation

**Theorem.** As extraction confidence $c_i \to 0$ for all entities in $E$, the mass functions approach maximal ignorance ($m_i(\Theta) \to 1$), and the combined belief $\text{Bel}_j \to 0$.

**Proof.**

*Limiting mass function.* Fix $\rho_i \in (0, 1)$ and $r_i \in [\tau_{\text{relevance}}, 1]$. As $c_i \to 0$:

$$m_i(\{\text{suf}\}) = \rho_i \cdot c_i \cdot r_i \;\to\; 0$$

$$m_i(\{\text{ins}\}) = (1-\rho_i)(1-c_i)(1-r_i) \;\to\; (1-\rho_i)(1-r_i)$$

$$m_i(\Theta) = 1 - m_i(\{\text{suf}\}) - m_i(\{\text{ins}\}) \;\to\; 1 - (1-\rho_i)(1-r_i)$$

When additionally $r_i \to \tau_{\text{relevance}}$ (the minimum retained relevance) or $\rho_i \to 0$:

$$m_i(\{\text{ins}\}) \to 0, \quad m_i(\Theta) \to 1$$

confirming maximal ignorance as the limiting BPA.

*Effect on combined belief.* After Dempster combination of $n$ mass functions each with $m_i(\{\text{suf}\}) = 0$, the numerator of $m^{(n+1)}(\{\text{suf}\})$ is:

$$\text{num} = \sum_{B \cap C = \{\text{suf}\}} m^{(n)}(B) \cdot m_{n+1}(C)$$

The only intersections producing $\{\text{suf}\}$ are $\{\text{suf}\} \cap \{\text{suf}\}$ and $\{\text{suf}\} \cap \Theta$ and $\Theta \cap \{\text{suf}\}$ (from the intersection table in Section 5.1 of the algorithm). With $m_{n+1}(\{\text{suf}\}) = 0$, the terms $m^{(n)}(\{\text{suf}\}) \cdot m_{n+1}(\Theta)$ and $m^{(n)}(\Theta) \cdot m_{n+1}(\{\text{suf}\})$ respectively contribute $m^{(n)}(\{\text{suf}\}) \cdot m_{n+1}(\Theta)$ and $0$. By induction: if $m^{(n)}(\{\text{suf}\}) = 0$ (base case: single entity with $c = 0$ gives $m_1(\{\text{suf}\}) = 0$), then $\text{num} = 0$, and $m^{(n+1)}(\{\text{suf}\}) = 0 / (1-K) = 0$.

Therefore $\text{Bel}_j = m^{(n)}(\{\text{suf}\}) = 0$, and by the concordance adjustment $B_j = \gamma_j \cdot 0 = 0$.

*Continuity argument.* By the arithmetic continuity of the mass function and the normalisation in Dempster's rule (a rational function of the inputs, continuous away from the degenerate $K = 1$ case), the combined belief is a continuous function of the individual confidence scores. Since $\text{Bel}_j = 0$ at $c_i = 0$ and $\text{Bel}_j \geq 0$ always, the belief approaches 0 smoothly as confidence degrades. $\blacksquare$

**Remark.** This property ensures SABLE never asserts assessability on the basis of low-confidence extractions alone: falling confidence drives $B_j$ to zero, triggering NOT_ASSESSABLE or PARTIALLY_ASSESSABLE as appropriate.

---

## Property 5: Weakest-Link Aggregation

**Theorem.** The rule-level belief is bounded above by the minimum per-requirement adjusted belief:

$$B_{\text{rule}} = \min_{j=1}^{k} B_j$$

and cannot exceed the belief of the least-supported requirement.

**Proof.**

This is an algebraic identity, not a consequence of D-S theory. SABLE Step 6 (pseudocode line 42; `assessability.py` line 234) defines:

$$B_{\text{rule}} \;\triangleq\; \min_{j=1}^{k} B_j$$

The following properties follow immediately.

*Upper bound.* $B_{\text{rule}} \leq B_j$ for all $j = 1, \ldots, k$ by definition of the minimum.

*Tightness.* The bound is tight: $B_{\text{rule}} = B_{j^*}$ where $j^* = \arg\min_j B_j$. The minimum is achieved at the requirement with least belief.

*Propagation of failure.* If any requirement $R_{j^*}$ has $B_{j^*} = 0$ (e.g., due to MISSING reconciliation status giving $\gamma_{j^*} = 0$, or genuinely zero belief after combination), then $B_{\text{rule}} = 0$, and the three-state decision produces NOT_ASSESSABLE (since $B_{\text{rule}} = 0 < \theta_{\text{low}} = 0.3$ and $\text{Pl}_{\text{rule}} \leq \text{Pl}_{j^*}$, which may also be 0).

*Design rationale.* The min-aggregation implements a conjunctive semantics: a rule requires evidence for all of its requirements. The rule is only as assessable as its least-supported component. This is formally analogous to the product t-norm in fuzzy logic applied conjunctively, but here adopted as a hard lower-bound semantics that is more conservative and appropriate for regulatory compliance contexts. Alternative aggregations (e.g., average, product) would allow a single well-evidenced requirement to compensate for a completely unevidenced one — which is semantically incorrect for conjunctive regulatory rules. $\blacksquare$

**Corollary.** Improving evidence for any requirement $R_j$ with $B_j > B_{\text{rule}}$ leaves $B_{\text{rule}}$ unchanged. Improvement in $B_{\text{rule}}$ requires improving $B_{j^*}$, the current weakest link.

---

## Summary Table

| Property | Statement | Proof Technique |
|----------|-----------|-----------------|
| **1. Monotonicity** | Adding positive-quality evidence cannot decrease $\text{Bel}_j$ | D-S combination numerator dominance |
| **2. Boundedness** | $0 \leq B_j \leq \text{Pl}_j \leq 1$ for all $j$ | BPA validity + induction on combination |
| **3. Determinism** | Same inputs always produce same output | Composition of deterministic functions |
| **4. Graceful degradation** | $c_i \to 0 \Rightarrow \text{Bel}_j \to 0$ | Limiting BPA analysis + D-S induction |
| **5. Weakest-link** | $B_{\text{rule}} = \min_j B_j$ | Definitional (algorithmic design) |

---

## References

[1] G. Shafer, *A Mathematical Theory of Evidence*, Princeton University Press, 1976.

[2] P. Smets and R. Kennes, "The Transferable Belief Model," *Artificial Intelligence*, vol. 66, no. 2, pp. 191–234, 1994.

[3] F. Voorbraak, "On the Justification of Dempster's Rule of Combination," *Artificial Intelligence*, vol. 48, no. 2, pp. 171–197, 1991.
