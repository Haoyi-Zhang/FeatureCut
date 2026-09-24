# Timing certificates for open-prefix causal histories

## Scope and cost convention

These are mathematical proofs, not mechanically verified general theorems. The executable oracle checks finite instances. The objects being minimized are **selected primitive timing assertions**, each with unit cost. The causal graph, source inventory, source-prefix identities, feature-routing epoch, read cut and event upper bounds form a trusted structural header. Their storage and validation costs are not included in the objective. Neither an information-theoretic encoding lower bound nor a cryptographic authentication guarantee is claimed.

A producer has a finite catalog of true primitive assertions. A certificate selects assertions from it. Entailment is evaluated using **only selected assertions**, not all unrevealed catalog facts. A countermodel to a subset can therefore violate an unselected fact; it shows that the subset does not certify the claim, not that the actual history was stale. Admission verifies that the whole supplied catalog has some feasible world and rejects inconsistent inputs rather than exploiting vacuous implication.

## 1. Model

There is a finite, fixed inventory of sources S. Each source has a fixed set R_s of feature names it can update during the epoch. The observed event set E contains a complete prefix of each source's append-only log and every predecessor of each observed event. It is finite and topologically ordered. Source order is included in its directed acyclic dependency graph G. Events have either one feature name in their source's routing set or no queried update (an auxiliary event). Unobserved events can occur only after the corresponding observed source prefix. They may add cross-source dependencies, but no such dependencies are required; an extension with one event depending only on its source tail is allowed.

The physical timestamp t_v of an observed event is a nonnegative real number, satisfies its upper bound U_v and is no later than Q. A causal edge u -> v requires t_u <= t_v. A catalog assertion at v says t_v >= L_v. Selected source assertion s says that every event after the observed prefix has timestamp **strictly greater** than W_s. There is no upper bound on future extensions. Source seals constrain the unknown suffix, not observed events. Their physical validity, authentication, inventory completeness and absence of prefix holes are assumptions, not outputs of this checker.

The timestamp uncertainties are independent except for the specified inequalities. In particular, shared unknown clock offsets or hidden synchronization constraints are not in this model. Q is the upper endpoint of the read-time uncertainty interval, and the world q=Q is allowed. Considering q=Q suffices: all freshness thresholds increase with q. Observed events must have occurred by the actual read time; the necessity constructions choose q=Q.

Let F be the nonempty queried feature set, with nonnegative budgets Delta_f. Define theta_f=Q-Delta_f. A fixed materialized input history C is acceptable exactly when it is an ideal of G and, in every selected-premise world and extension, every update of every f in F with t <= theta_f belongs to C. Freshness means absence of omitted old updates, **not age of the last update**. No feature-value function, conflict-resolution rule, prediction quality or transaction atomicity is inferred from this property.

## 2. Augmented obligations and tagged bounds

Append a virtual vertex z_s for each source with R_s intersect F nonempty. Its only predecessor is the source's observed tail, if any. It represents a possible next unseen event, not an assertion that such an event exists. Its threshold is theta_s=max{theta_f : f in R_s intersect F}. The obligation set O contains (v,theta_f) for each observed queried update v not in C, and (z_s,theta_s) for every relevant source.

Represent a lower assertion by (a,b), b in {0,1}: (a,0) means t>=a, and (a,1) means t>a. Order these pairs lexicographically. A selected event fact is (L_v,0); a selected seal at z_s is (W_s,1). The free base bound is (0,0). In topological order propagate

    B_P(v) = max({(0,0)} union selected bounds at v union {B_P(u):u->v}).

Thus B_P(v) is the largest selected bound among all reflexive ancestors of v. An obligation (v,theta) passes exactly when B_P(v)>(theta,0). Negative thresholds pass from nonnegativity alone. A seal W=theta passes, whereas an event lower endpoint L=theta does not.

## Theorem 1: exact robust certification

For an admitted catalog and a selected subset P, C is a robustly acceptable input history if and only if C is an ideal and every obligation passes the tagged-bound test.

**Sufficiency.** Induction in a topological order proves that every event time satisfies each propagated bound. For an observed omitted update, a passing bound makes its timestamp strictly later than its feature's threshold in every world. Every unseen update follows the observed tail of its source, and also satisfies that source's selected seal, when present. A bound at z_s therefore bounds the timestamp of every unseen event from s. The maximum routing threshold is at least the threshold of whichever queried feature an unseen event updates. No omitted known or unknown old update can exist. Closure gives the remaining causal requirement.

**Necessity.** A nonideal C already violates causality. Otherwise take a failed obligation (v,theta). Since the base bound failed, theta>=0. First suppose v is observed. Start with a feasible selected-premise assignment (whole-catalog feasibility guarantees one). Cap the times of every reflexive ancestor of v at theta. Every selected lower fact on this ancestor set is at most (theta,0), so the cap preserves it. Upper bounds and nonnegativity are preserved. Edges internal to the set preserve order under the same monotone cap; no edge can enter the ancestor set from outside it; outgoing edges only have their lower endpoint decreased. Thus this is a feasible world with t_v<=theta. Take an empty unknown suffix, which is permitted by every seal. The queried update v is omitted and old.

If v=z_s, cap all observed ancestors of the tail at theta in the same manner. If the selected seal exists, failure implies W_s<theta, because (theta,1) would pass. Choose f in R_s intersect F attaining theta_s. Append exactly one event of feature f at time theta, ordered after the observed tail and with no additional dependencies. It satisfies the seal, nonnegative time, and source order. It occurs by Q because every budget is nonnegative. It is an omitted old queried update. This extension is allowed by the prefix model. These constructions prove necessity.

This capping argument also works with strict lower assertions on observed vertices in a more general mathematical catalog, provided admission establishes feasibility. The delivered executable format uses closed event lower endpoints and strict source seals only. For integer inputs its counterexample generator can simply use propagated closed event lower endpoints and, for a suffix witness, timestamp theta.

## Corollary 2: least materialization for fixed premises

Compute bounds on the augmented header, independently of C. If any virtual source obligation fails, no subset of E can be certified fresh: adding observed events never accounts for the possible old hidden event. Otherwise let M_P contain every observed queried update v whose bound fails its feature threshold. The unique inclusion-minimal certified ideal is C_P=downward_closure(M_P).

**Proof.** Theorem 1 forces every certified C to include M_P; an ideal containing M_P contains its downward closure. This closure is itself an ideal. Every queried observed update it omits has a passing bound, and by hypothesis all source obligations pass. Apply Theorem 1. This is an ideal-closure consequence, not a claimed new lattice algorithm. It differs from choosing a minimal timing certificate for a fixed C.

## Theorem 3: exact set-cover representation

Remove negative-threshold obligations, which are free. For each primitive p at vertex a with bound b, form

    S_p = {(v,theta) in O : a is a reflexive ancestor of v and b>(theta,0)}.

For ideal C, P is a certificate if and only if the sets S_p for p in P cover O.

**Proof.** The propagated maximum exceeds an obligation's threshold if and only if some selected ancestor bound does. The free bound cannot pass a remaining nonnegative threshold. Combine this observation with Theorem 1. Infeasible covers correspond to uncertifiable cuts, not to unsound optimizer outputs.

The representation yields standard set-cover tools. Unit-cost greedy chooses a fact with maximum newly covered obligations and has the classical H_m approximation bound, m=|O|. The guarantee is inherited from set cover, not a new approximation theorem. Rational y_o>=0 with sum_{o in S_p} y_o<=1 for every p give sum_o y_o<=OPT by summing inequalities over any covering family. Consequently ceil(sum_o y_o) is a verified integer lower bound. The executable dual routine merely constructs feasible weights; it does not solve the dual LP optimally.

## Theorem 4: hardness despite a one-element cut frontier

For finitely binary-encoded rational endpoints, deciding whether an ideal cut has a certificate of at most k primitive facts is NP-complete. This complexity statement is not an oracle claim for arbitrary real-number inputs. Hardness holds with equal budgets, no seals, all numeric constants in {0,1,2}, an included-cut frontier of size one, and an observed graph of height at most three (four after adding suffix vertices).

**Proof.** Membership follows from Theorem 1 and polynomial-size fact IDs. Given a set-cover instance with elements i and candidate sets A_j, make one auxiliary genesis g, one auxiliary anchor a_j per candidate set, and one queried update x_i per element. All events have different sources, so every observed source prefix has length one. The sources of g and anchors route no queried feature. The source of x_i routes only f_i. Add g->a_j and a_j->x_i exactly when i belongs to A_j. Let C={g}, Q=2, Delta_f=2. Give g and x_i lower endpoint 0, anchors lower endpoint 1, and all upper endpoints 2. O contains x_i and its source's suffix vertex, both with threshold 0. The catalog is feasible: g at 0, anchors and targets at 1. Only anchor facts have positive coverage. An anchor covers x_i and its suffix exactly for i in A_j. Therefore a size-k timing certificate exists exactly when the original cover does. The transformation is polynomial. The frontier is {g}; all other restrictions hold. An uncovered set-system element simply gives an infeasible timing certificate instance, as required.

## Corollary 5: causal-frontier width does not bound primitive timing evidence

For any n, specialize Theorem 4 to n singleton sets. Every queried update and its suffix require the corresponding anchor fact; no other positive-bound ancestor exists. Hence exactly n facts are necessary although the included-cut frontier has width one. Replacing the n singleton anchors by one shared anchor gives an instance requiring one fact. This is a lower bound for the declared primitive-assertion language, not for arbitrary encodings, shared authenticated state, or cryptographic proofs.

## Theorem 6: exact independent-chain optimization

Suppose the graph contains no cross-source causal edges. With unit-cost facts, minimum certificate cardinality is solvable by interval stabbing on each source independently.

**Proof.** Index each source's observed events followed by its virtual vertex, if relevant. A later fact whose tagged bound is no stronger than an earlier fact is dominated: every descendant obligation it covers is also covered by the earlier fact. At the same position retain only the strongest fact. Drop all facts dominated by the free bound. The remaining record facts have strictly increasing positions and strictly increasing tagged bounds. For an obligation (v,theta), eligible facts have position at most pos(v), a prefix of the record sequence, and bound greater than (theta,0), a suffix. Their intersection is an index interval [l_v,r_v]. An empty interval proves infeasibility.

Sort these intervals by right endpoint. For the first unhit interval choose its right endpoint, and repeat. To prove optimality, take its right endpoint r and any optimal solution hitting that interval at j<=r. Replacing j by r preserves every not-yet-processed interval that j hit: such an interval has right endpoint at least r and left endpoint at most j. This exchange preserves cardinality. Induction proves the greedy hitting set optimal. Alternatively, the intervals that triggered choices are pairwise disjoint, a matching lower-bound packing. Sources have no common fact coverage, so optima add. Sorting yields O((|P|+|O|)log(|P|+|O|)) comparisons after the chain/header construction. The delivered straightforward source grouping additionally scans arrays by source; its implementation need not attain that ideal preprocessing bound.

This particular record-fact pruning does not extend to unequal fact costs: its dominance rule and right-endpoint exchange rely on unit cost. Theorem 7 uses a different reduction to handle unequal costs. No independent-chain reduction is applied to a graph containing cross-source edges.

## 3. Structural necessity and boundaries

A prefix hole can hide an old update before an apparently late source tail. An omitted source can hide an old update without affecting any visible event. In either case two physical histories can agree on the entire visible packet but disagree on freshness. A checker that has neither a trusted complete inventory/prefix header nor equivalent authenticated evidence cannot infer our guarantee from that packet alone. A source seal is useful only when bound to the exact epoch and prefix to which it applies.

Changing an event lower endpoint to its upper endpoint, replacing strict > by >= for known-event obligations, or deleting virtual obligations can all create false acceptance. Treating a source with several routed queried features using the *minimum* threshold is unsound; the maximum is required. Using the maximum threshold for *every* feature is sound but can reject valid heterogeneous-budget cuts.

Constant per-source clock offsets are a different model. For example, if two events share an unknown offset, capping only the earlier event may violate that equality. Our necessity proof relies on independence except for the stated order and bound inequalities. The result therefore cannot be transferred to correlated clock models by substituting HLC physical components for calibrated interval endpoints.

The source inventory, causal predecessor completeness, physical calibration, interpretation of a materialized input set, value computation, and conflict handling remain assumptions. The checker can reject when it cannot certify a cut; it supplies no liveness guarantee under partitions, no bound on when a certificate will become obtainable, and no deployed feature-store performance claim.

## Theorem 7: exact additive-cost independent-chain selection

For independent source chains, minimum total nonnegative additive primitive-fact cost is polynomial-time solvable. This includes zero-cost facts and unequal costs. It is a different argument from the unit-cost record-fact pruning in Theorem 6: an earlier stronger assertion may be more expensive, so that pruning is invalid for unequal costs.

**Proof.** Work on one source and discard negative-threshold obligations. If obligation (v,theta) precedes (w,phi) on the chain and theta>=phi, every fact covering v also covers w. Consequently remove every obligation whose threshold is no larger than an earlier obligation's threshold. The retained obligations o_1,...,o_r have strictly increasing positions and strictly increasing thresholds, and covering them is equivalent to covering all obligations.

For any fact p, its eligible retained obligations form an interval [l_p,h_p]: eligible positions are a suffix of the ordered obligations, while thresholds strictly below the tagged fact bound are a prefix. Empty intervals can be ignored. Crucially, facts are not discarded merely because an earlier fact is stronger.

Consider a directed acyclic graph of covered-prefix states 0,...,r. Each interval [l,h] and state j with l-1<=j<h gives an edge j->h with that fact's cost. A path from 0 to r chooses intervals that successively cover every obligation, and each chosen fact is used at most once because state indices strictly increase. Conversely, from any covering set, start at the first uncovered obligation j+1, choose a member interval containing it, and advance to that interval's right endpoint. Continuing constructs a path using a subset of the cover. Nonnegative costs make the path no more expensive. Minimum path cost therefore equals the minimum certificate cost.

Let D[0]=0 and initially D[j]=infinity for j>0. For intervals ending at h, compute

    D[h] = min over p with h_p=h of (cost(p) + min_{l_p-1<=j<h} D[j]).

Process endpoints increasingly. A range-minimum tree evaluates each inner minimum in logarithmic time; predecessors reconstruct a certificate. An absent finite D[r] means infeasibility. Different sources share no covering fact, so costs add. After grouping and sorting, time is O((P+O) log(P+O)) comparisons and O(P+O) storage, apart from graph admission. With B-bit nonnegative integer costs, additions/comparisons also pay their O(B+log P) bit cost. There is no claim that this standard interval-cover shortest-path algorithm is itself new.

The executable extension was piloted on every three-event lower tuple in {0,1,2,3}, two-feature budget pair in {2,3}^2, every prefix cut, four seals, and four explicit cost patterns (one includes zero costs): 16,384 optimization instances, 57,344 directly checked subsets, no optimum disagreement. This pilot preceded the length-four extension campaign. Mathematical proof, finite optimum enumeration and implementation measurements are separate evidence types.


## Corollary 8: exact budget envelope for fixed evidence

Fix the header, queried feature set F, cut C, and selected facts P, but permit the
nonnegative budgets to vary. For each f let J_f contain every observed omitted
update of f and every virtual source vertex whose routing includes f. Each J_f
is nonempty, because admission requires a complete nonempty source inventory
for f. Define K_f as the minimum tagged bound B_P(v) over v in J_f.

Then C certifies budgets Delta exactly when it is an ideal and
K_f > (Q-Delta_f,0) for every f. For K_f=(a,0), this is Delta_f > Q-a;
for K_f=(a,1), it is Delta_f >= Q-a. Intersect these conditions with Delta_f>=0.

**Proof.** Known omissions of f have the same threshold. The source condition
B_P(z_s) > (max_f theta_f,0) is equivalent to its conjunction over every f routed
by s. Regroup all these tests by feature and take the finite minimum. Apply
Theorem 1. A minimum is attained; a failed feature therefore identifies a
known or virtual failing obligation and inherits its counterworld construction.

The region is an upward product of open or closed rays for fixed P. This is a
corollary of the exact criterion, not a new independent optimization algorithm.
It does not say a fixed certificate remains valid after changing source
membership, epoch, prefixes or physical calibration. Unions over different
certificate selections, or joint optimization of cut and certificate cost, are
separate questions. The API returns the envelope even for a nonideal cut, so
callers must retain the independent closure test.


## Numeric boundary illustrations

The seven-event chain r,p,o1,q,o2,o3,o4 has lower endpoints 9,5,0,9,0,0,0,
all upper endpoints 10, empty cut and one source with no seal. The four query
thresholds are 3,4,7,8. Its useful fact covers are r:{1,2,3,4}, p:{1,2},
q:{2,3,4}; the virtual suffix duplicates the fourth obligation. Costs 5,2,2
yield weighted optimum {p,q} of cost four and unit optimum {r} of size one.
A feasible full-catalog assignment is time nine at every event.

For the excluded correlation model, an auxiliary included u and omitted f-update
v have trusted upper endpoints ten, unselected lower endpoints zero, and separate
sources; only v's source routes f and has no seal. At Q=10 and budget 8 the
independent model rejects empty evidence. Restricting times to u=o, v=o+5 with
real o in [0,5] forces v>=5>2 and also forces every hidden successor on v's source
to be later than the threshold. This is a mathematically fresh cut in the smaller
world set. It refutes transferring necessity to arbitrary correlated time models;
it does not refute Theorem 1 under its stated independence assumption. Six
integer points are included only as a numerical illustration, not as a proof of
the continuous restriction. Both illustrations are retained by tests/illustrations.py.

## Proposition 9: composition with deterministic feature replay

Let M be one admitted application manifest containing the structural timing
header, the fixed cut C, one value payload for every observed feature update,
and a deterministic feature program Phi.  Let replay(M) denote the exact value
obtained by evaluating Phi over the payloads whose event identifiers belong to
C.  A bound packet is accepted only when (i) its selected facts pass Theorem 1
against M, (ii) its manifest identifier names the same trusted M, and (iii) its
claimed value is byte-for-byte equal to a fresh deterministic replay.

Then every accepted packet has both of the following properties:

1. C is a causal ideal and, for every queried feature f, every known or possible
   unseen update with physical time at most Q-Delta_f belongs to C.
2. The claimed materialized value is exactly replay(M).

Consequently the accepted value is the declared deterministic transformation of
a causally closed input set with no omitted update older than its feature's
budget.  This does not imply that every included update changes the value (for
example, a maximum can ignore smaller inputs), that the transformation is useful
for a model, or that the packet has transaction/session semantics.

**Proof.** Item 1 is Theorem 1 because the packet checker invokes the same
selected-premise decision procedure on the manifest's header and cut.  Item 2
is the explicit replay-equality check.  The conjunction gives the conclusion.
No property of the transformation other than determinism and use of the same
manifest is needed.

The executable instantiation groups feature updates by entity and supports
count, integer sum, integer maximum, and latest-by-topological-event-ID.  These
operators are examples, not a restriction of the proposition.  Event ID is an
explicit deterministic order in this prototype; it is not presented as event
time or a conflict-resolution rule for a deployed store.

### Binding and cryptographic boundary

The implementation serializes the complete manifest canonically and uses its
SHA-256 digest as a content address.  Verification also receives an expected
digest through a separate trust channel.  This prevents accidental mixing of a
packet with a different manifest and makes changes to the cut, payloads,
program, source inventory, routing, prefixes, or timing catalog detectable under
that trust setup.  The proof above is conditional on the checker being given the
intended manifest.  It is not a proof of SHA-256 collision resistance, a digital
signature, source authentication, secure writer discovery, or tamper-resistant
clock attestation.  A deployment must authenticate the expected digest and the
assertions that the manifest contains.

The fail-closed service rule in the artifact is also deliberately narrow.  A
malformed packet, digest mismatch, timing failure, or replay mismatch yields no
certified output.  Rejection says only that this packet does not establish the
claim; it does not prove the underlying feature value is false or stale.
