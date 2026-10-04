# Causal-cut certificates bounded

A standalone, standard-library Python artifact for timing certificates over
causal input histories with open source-log prefixes. It is not a production
feature store, a cryptographic verifier, or a transaction-isolation checker.

## Result and trust boundary

Given a trusted DAG, complete fixed source/routing inventory, contiguous source
prefixes, upper time bounds, and selected true lower/seal assertions, the checker
certifies the absence of omitted updates older than each declared budget.
Event assertions are closed (`t >= L`); source seals are strict (`t > W`) and
apply to the unknown suffix. Only selected assertions are used as premises.
The optimization objective counts selected assertions, not a universal wire
encoding. A separate reference materializer content-binds the admitted model,
cut, event payloads, and deterministic feature program, and measures packets
with either the selected facts or the full catalog. Its SHA-256 digest is a
content address; an expected digest must be trusted out of band and is not a
signature. General mathematical proofs are in `proofs/model-and-proofs.md`;
finite checks are not machine-checked proofs. The forward and backward code
paths share input admission and were not independently authored or reviewed.

## Requirements

Python 3.10 or later on Linux/POSIX with `resource` and, on Linux, CPU affinity.
No Python package installation, network access, GPU, model, private data or
external service is required. Scientific children pin one allowed CPU and cap
address space at 3 GiB and CPU time at 35 seconds. Run serially. The retained
largest observed resident set was below 190 MiB; the final fresh-copy run peaked
at 189,932 KiB; this is a measurement, not a universal requirement for arbitrary
input sizes. The CLI accepts at most 200,000
observed events; larger untrusted inputs are outside the resource claim. The
schematic data model uses arbitrary-precision integer endpoints in the code;
the main mathematical result permits real endpoints.

## Quick check

Run from this repository root:

```sh
python3 src/checker.py data/workloads/shared-128-11.json data/certificates/shared-128-11.json
python3 src/cli.py data/workloads/shared-128-11.json --method greedy --output /tmp/causal-cut-certificate.json
python3 src/checker.py data/workloads/shared-128-11.json /tmp/causal-cut-certificate.json
```

A successful checker prints `{"accepted": true}` and exits zero. Rejection is
exit one. Parsing/admission errors are exit two; a syntactically valid but
unknown or duplicated fact selection is rejected.

A content-bound packet can be checked independently:

```sh
python3 src/materializer.py check \
  data/materializations/shared-128.json \
  data/materialization-certificates/shared-128-minimal.json \
  --expected 14c1b6fe146f348955ef9cd4c5ac3840acad3822d0abc04a415ea4ed498fd427
```

The packet is accepted only if the expected digest matches the canonical
manifest, its selected facts certify the embedded cut, and local deterministic
replay exactly matches the packet output and digest.
The manifest digest does not identify one unique selected-fact list. Facts are
proof premises checked for membership, uniqueness, and sufficiency: the retained
minimal and full packets both accept, as do redundant additions and legal
reorderings. Removing a necessary fact, repeating an identifier, or naming an
unknown identifier rejects. The producer supports
`greedy`, `chain`, `exact`, and `full`. Exact search is bounded to 22 catalog
facts. A chain request on cross-source edges raises a model error rather than
silently dropping edges. For an uncertifiable cut the producer writes a negative
world and the least observed cut under all facts, if one exists. This is not a
claim that the actual history was stale.

## Reproduction

```sh
python3 reproduce.py --task boundaries
python3 reproduce.py --tasks audit metadata materialization
python3 reproduce.py --all
python3 report.py --check
```

`reproduce.py` copies this repository to its own temporary directory, runs named
tasks serially, and compares semantic result fields and all exact JSON inputs
and certificates with the retained records. It does not overwrite the original
measurements. Timing and peak-memory observations may vary. A failed comparison
or timeout is a nonzero exit, not silently excluded data. Use `--output PATH`
to retain the reproduction record, or `--list` to list the 74 scientific tasks.
Each child is bounded; `--all` spans multiple children and can take several
minutes. Retained per-process measurements sum to 224.53 CPU seconds, with a
separate conservative 40-second allowance for an interrupted orchestration
driver. The final fresh-copy run completed all 74 tasks, matched every semantic
result, compared 199 retained JSON files byte-for-byte, and recorded 324.35 child
CPU seconds, 428.26 wall seconds, and a 189,932 KiB child-RSS peak in
`results/reproduction.json`. Do not add repeated semantic case counts as new
coverage. All evidence was executed during this internal research rather than
left as an unrun scientific handoff.

`report.py --check` recomputes the summary, pooled workload table, and seed-11
plot data from raw results and verifies retained derived files. `report.py
--write` refreshes only these derived results. The artifact contains its own
copy of the quantitative table/plot data and has no dependence on `paper/`.

## Evidence domains

The development pilot has 22,464 decisions. The full four-event suite covers all
64 topologically numbered DAGs, six endpoint intervals per event, all 16 cuts,
and two budget patterns: 1,783,808 admitted decisions and 27,200 infeasible
catalogs. All selected-premise three-event cases comprise 359,424 decisions and
44,928 least-cut comparisons. The independent-chain unit-cost suite has 20,480
instances. Additive-cost tests have 16,384 length-three and 81,920 length-four
optimization instances. The cover suite enumerates 512 three-by-three incidence
systems; the separate six-element control correctly makes greedy suboptimal
(three selected facts versus two). The fixed-evidence envelope suite compares
50,400 budget queries. Ten semantic mutation controls are deliberately selected,
not a random mutation sample. A separately organized two-source audit covers
9,072 admitted models, 326,592 selected-premise subsets, and 36,288 weighted
optimization instances with zero decision or optimum disagreement. Its replay
oracle covers 45 manifests and all four reference operators; seven top-level or
nested duplicate-JSON-member controls are rejected before semantic interpretation.
See raw result JSON for exact counts and failures.

Six generated workload families, three scales and three seed labels yield 54
runs, each with an unfenced-source negative pair. Seeds affect only the overlap
and DAG families. Four families repeat identical structures at each scale, so
54 runs must not be described as 54 independent workloads. All 30 distinct
structural inputs and repeats are retained under neutral case names. Timings use
five serial repetitions per method. The plotted forward-check times exclude
admission and selection; the table separates selection. The original six-family workload study measures fact counts and CPU paths,
not application throughput or deployment latency. A separate materialization
suite binds concrete payloads and eight deterministic outputs in six cases. It
accepts both minimal- and full-fact packets with identical replay and rejects 13
digest, output, insufficient or ill-formed selected-fact, manifest, writer-inventory,
and schema controls.
At scale 8,192, cached-manifest packet savings are 80.0% for shared evidence and
44.7% for independent evidence; including the manifest reduces those cold
package savings to 5.9% and 2.8%. These bytes are for the declared JSON schema,
not a network or production throughput claim. Full-catalog, per-target, greedy,
and eligible chain methods receive the same admitted header; exact optimization
is not attempted on large general graphs.

## Files and interfaces

`src/causalcut.py` implements admission, forward checking, set-cover selection,
verified rational dual bounds, least-cut construction, negative worlds,
independent-chain unit/additive-cost optima, and per-feature budget envelopes.
`src/checker.py` searches backward by obligation threshold. `src/witness.py`
validates explicit rejection worlds. `src/materializer.py` validates canonical
manifests and packets and deterministically replays per-entity `count`, `sum`,
`max`, and latest-by-event-ID outputs. `tests/materialization.py` retains six
content-bound cases and 13 fail-closed controls. `tests/audit.py` independently
organizes the two-source decision/optimization domain, a replay specification,
and duplicate-member ingress controls. `tests/metadata.py` validates unique
ledger identifiers, the 36 cited reference records, and the documented 18 full
plus 17 targeted literature readings. `tests/oracle.py` directly enumerates small
integer timestamp worlds and one possible hidden update. The finite oracle shares
the stated model, not a production time source. `tests/` contains all bounded
suites; `data/` contains exact generated cases and certificates; `results/`
contains claim-critical raw and derived evidence. `reference_verification.csv`
records publication identifiers, primary records, read scope, and citation
status. The other ledgers map claims and external resources; upstream papers are
not redistributed.

For library calls, first call `prepare(model)`, retain its immutable-in-use
context, and then select or validate facts. Do not mutate the header between
producer and checker. `budget_envelope` returns tagged pairs, not an acceptance
flag: retain the context's causal-closure condition and compare each bound to
`(Q-budget, 0)`. `weighted_chain_optimum` needs a nonnegative integer cost for
every catalog fact; it minimizes additive cost, not fact count. The simple JSON
format stores a full lower-fact catalog for exact reproduction. Selection
minimality is relative to treating only chosen facts as premises, even though
the catalog is physically available in this benchmark file.

## Limitations and provenance

No general proof assistant, independent human verification, deployment,
authentication, clock-calibration protocol, or source-discovery protocol is
included. Feature computation is limited to the declared deterministic reference
operators; it does not establish ML usefulness, conflict-resolution semantics,
window semantics, or transaction/session guarantees. Selected-assertion
minimality is not universal encoding minimality. The algorithmic ingredients
(ideal closure, set cover and interval cover/stabbing) are standard; passing the
tests does not guarantee venue-level novelty or acceptance. The manuscript is
an internal research draft, not an independently reviewed submission.

This license
covers original artifact material only; see `LICENSE` and
`external_resources.csv`. No project instructions, prompts or review history
are required to reproduce the finite evidence.
