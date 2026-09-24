"""Causal-cut timing certificates. Python standard library only.

Certificates minimize selected primitive timing facts, not the structural header.
The header, routing and primitive assertions are trusted inputs; no signatures,
physical clock calibration or production feature-store behavior are implemented.
"""
from __future__ import annotations
import bisect
import heapq
import itertools
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

Bound = tuple[int, int]  # (endpoint, 0=closed / 1=open)

class ModelError(ValueError):
    pass


def integer(x: Any, name: str, low: int = 0) -> int:
    if type(x) is not int or x < low:
        raise ModelError(f'{name}: expected integer >= {low}')
    return x


def keys(obj: Any, allowed: set[str], name: str) -> None:
    if type(obj) is not dict or set(obj) != allowed:
        raise ModelError(f'{name}: fields must be {sorted(allowed)}')


@dataclass
class Context:
    model: dict
    parents: list[list[int]]
    facts: dict[str, tuple[int, Bound]]
    targets: list[tuple[int, int]]
    tails: list[int | None]
    causal: bool


def prepare(model: dict) -> Context:
    """Admit the entire trusted catalog once; reject inconsistent intervals."""
    keys(model, {'events', 'sources', 'cut', 'query'}, 'model')
    keys(model['query'], {'upper', 'budgets'}, 'query')
    q = integer(model['query']['upper'], 'query.upper')
    budgets = model['query']['budgets']
    if type(budgets) is not dict or not budgets:
        raise ModelError('nonempty budgets required')
    for f, d in budgets.items():
        if type(f) is not str or not f:
            raise ModelError('feature must be nonempty string')
        integer(d, 'budget')
    events, sources, cut = model['events'], model['sources'], model['cut']
    if type(events) is not list or len(events) > 200000:
        raise ModelError('event list too large or malformed')
    if type(sources) is not list or not sources:
        raise ModelError('nonempty source inventory required')
    for i, s in enumerate(sources):
        keys(s, {'id', 'writes', 'seal'}, 'source')
        if integer(s['id'], 'source.id') != i:
            raise ModelError('source IDs must equal list indices')
        w = s['writes']
        if type(w) is not list or any(type(x) is not str or not x for x in w) or len(set(w)) != len(w):
            raise ModelError('invalid routing inventory')
        if s['seal'] is not None:
            integer(s['seal'], 'seal', -1)
    routed = {f for source in sources for f in source['writes']}
    if not set(budgets) <= routed:
        raise ModelError('queried feature lacks a source')
    n = len(events)
    if type(cut) is not list or any(type(x) is not int or not 0 <= x < n for x in cut) or len(set(cut)) != len(cut):
        raise ModelError('invalid cut IDs')
    c = set(cut)
    tails: list[int | None] = [None] * len(sources)
    seqs = [0] * len(sources)
    parents: list[list[int]] = []
    facts: dict[str, tuple[int, Bound]] = {}
    earliest: list[int] = []
    for i, e in enumerate(events):
        keys(e, {'id', 'source', 'seq', 'feature', 'parents', 'lower', 'upper'}, 'event')
        if integer(e['id'], 'event.id') != i:
            raise ModelError('event IDs must equal topological list indices')
        s = integer(e['source'], 'event.source')
        if s >= len(sources):
            raise ModelError('unknown source')
        if integer(e['seq'], 'event.seq') != seqs[s]:
            raise ModelError('source prefix has a gap or duplicate')
        seqs[s] += 1
        f = e['feature']
        if f is not None and (type(f) is not str or f not in sources[s]['writes']):
            raise ModelError('event outside declared routing')
        p = e['parents']
        if type(p) is not list or any(type(x) is not int or not 0 <= x < i for x in p) or len(set(p)) != len(p):
            raise ModelError('invalid predecessor list or non-DAG order')
        if tails[s] is not None and tails[s] not in p:
            raise ModelError('source-order predecessor missing')
        lo, hi = integer(e['lower'], 'lower'), integer(e['upper'], 'upper')
        t = max([lo] + [earliest[x] for x in p])
        if t > min(hi, q):
            raise ModelError('catalog has no admissible clock assignment')
        earliest.append(t)
        parents.append(p.copy())
        facts[f'e:{i}'] = (i, (lo, 0))
        tails[s] = i
    causal = all(all(p in c for p in parents[v]) for v in c)
    targets = [(i, q - budgets[e['feature']]) for i, e in enumerate(events)
               if i not in c and e['feature'] in budgets]
    for s, source in enumerate(sources):
        fs = set(source['writes']) & budgets.keys()
        if not fs:
            continue
        z = len(parents)
        parents.append([] if tails[s] is None else [tails[s]])
        if source['seal'] is not None:
            facts[f's:{s}'] = (z, (source['seal'], 1))
        targets.append((z, max(q - budgets[f] for f in fs)))
    return Context(model, parents, facts, targets, tails, causal)


def verify(ctx: Context, selected: list[str]) -> dict:
    if type(selected) is not list or any(type(x) is not str for x in selected) or len(set(selected)) != len(selected):
        raise ModelError('certificate facts must be unique strings')
    if any(p not in ctx.facts for p in selected):
        raise ModelError('unknown fact identifier')
    low: list[Bound] = [(0, 0)] * len(ctx.parents)
    for p in selected:
        v, b = ctx.facts[p]
        low[v] = max(low[v], b)
    for v, ps in enumerate(ctx.parents):
        for p in ps:
            low[v] = max(low[v], low[p])
    failed = [(v, t) for v, t in ctx.targets if low[v] <= (t, 0)]
    return {'accepted': ctx.causal and not failed, 'causal': ctx.causal,
            'uncovered': failed, 'fact_count': len(selected)}


def cover_sets(ctx: Context) -> tuple[list[tuple[int, int]], dict[str, int]]:
    """Target bitsets. Integer bit operations are not counted as unit-cost math."""
    targets = [(v, t) for v, t in ctx.targets if t >= 0]
    reachable = [0] * len(ctx.parents)
    for i, (v, _) in enumerate(targets):
        reachable[v] |= 1 << i
    for v in reversed(range(len(ctx.parents))):
        for p in ctx.parents[v]:
            reachable[p] |= reachable[v]
    thresholds = sorted(set(t for _, t in targets))
    by_t = {t: 0 for t in thresholds}
    for i, (_, t) in enumerate(targets):
        by_t[t] |= 1 << i
    pref = [0]
    for t in thresholds:
        pref.append(pref[-1] | by_t[t])
    masks = {}
    for p, (v, b) in ctx.facts.items():
        k = bisect.bisect_right(thresholds, b[0]) if b[1] else bisect.bisect_left(thresholds, b[0])
        mask = reachable[v] & pref[k]
        if mask:
            masks[p] = mask
    return targets, masks


def greedy(ctx: Context) -> list[str] | None:
    targets, masks = cover_sets(ctx)
    uncovered = (1 << len(targets)) - 1
    if not ctx.causal:
        return None
    heap = [(-m.bit_count(), p) for p, m in masks.items()]
    heapq.heapify(heap)
    chosen: list[str] = []
    while uncovered:
        if not heap:
            return None
        old, p = heapq.heappop(heap)
        gain = (masks[p] & uncovered).bit_count()
        if gain == 0:
            continue
        if heap and (-gain, p) > heap[0]:
            heapq.heappush(heap, (-gain, p))
            continue
        chosen.append(p)
        uncovered &= ~masks[p]
    return chosen


def exact(ctx: Context, max_facts: int = 22) -> list[str] | None:
    targets, masks = cover_sets(ctx)
    if not ctx.causal:
        return None
    if len(masks) > max_facts:
        raise ModelError('exact oracle fact ceiling exceeded')
    goal = (1 << len(targets)) - 1
    ps = sorted(masks)
    for k in range(len(ps) + 1):
        for comb in itertools.combinations(ps, k):
            total = 0
            for p in comb:
                total |= masks[p]
            if total == goal:
                return list(comb)
    return None


def per_target(ctx: Context) -> list[str] | None:
    """Sound baseline: choose each target's strongest ancestor assertion.

    A dynamic program avoids an artificially slow quadratic baseline. Bounds
    break ties by latest vertex and fact ID, exactly as a direct ancestor scan.
    """
    if not ctx.causal:
        return None
    best: list[str | None] = [None] * len(ctx.parents)
    def rank(p: str) -> tuple[Bound, int, str]:
        v, b = ctx.facts[p]
        return b, v, p
    for p, (v, _) in ctx.facts.items():
        if best[v] is None or rank(p) > rank(best[v]):
            best[v] = p
    for v, parents in enumerate(ctx.parents):
        for u in parents:
            p = best[u]
            if p is not None and (best[v] is None or rank(p) > rank(best[v])):
                best[v] = p
    chosen: set[str] = set()
    for v, t in ctx.targets:
        if t < 0:
            continue
        p = best[v]
        if p is None or ctx.facts[p][1] <= (t, 0):
            return None
        chosen.add(p)
    return sorted(chosen)


def chain_optimum(ctx: Context) -> list[str] | None:
    """Exact unit-cost algorithm for independent source chains (no cross edges)."""
    if not ctx.causal:
        return None
    model = ctx.model
    events, sources = model['events'], model['sources']
    for e in events:
        if any(events[p]['source'] != e['source'] for p in e['parents']):
            raise ModelError('chain algorithm requires no cross-source edges')
    node_source = [e['source'] for e in events]
    budgets = model['query']['budgets']
    for s, source in enumerate(sources):
        if set(source['writes']) & budgets.keys():
            node_source.append(s)
    selected = []
    for s in range(len(sources)):
        vertices = [v for v, a in enumerate(node_source) if a == s]
        pos = {v: i for i, v in enumerate(vertices)}
        candidates = sorted((pos[v], b, p) for p, (v, b) in ctx.facts.items() if node_source[v] == s)
        # Same position: keep strongest fact; earlier equal/stronger fact dominates.
        grouped: dict[int, tuple[Bound, str]] = {}
        for i, b, p in candidates:
            if i not in grouped or (b, p) > grouped[i]:
                grouped[i] = (b, p)
        record = []
        best: Bound = (0, 0)
        for i in sorted(grouped):
            b, p = grouped[i]
            if b > best:
                record.append((i, b, p)); best = b
        bounds = [b for _, b, _ in record]
        positions = [i for i, _, _ in record]
        intervals = []
        for v, t in ctx.targets:
            if node_source[v] != s or t < 0:
                continue
            left = bisect.bisect_right(bounds, (t, 0))
            right = bisect.bisect_right(positions, pos[v]) - 1
            if left > right:
                return None
            intervals.append((right, left))
        last = -1
        for right, left in sorted(intervals):
            if not left <= last <= right:
                last = right
                selected.append(record[right][2])
    return selected


def dual_bound(ctx: Context) -> list[list[int]]:
    """Construct a rational feasible cover dual; this is not an LP solver."""
    targets, masks = cover_sets(ctx)
    m = len(targets)
    if not m:
        return []
    maximum = max((x.bit_count() for x in masks.values()), default=0)
    if not maximum:
        return []
    y = [Fraction(1, maximum) for _ in range(m)]
    incident: list[list[str]] = [[] for _ in range(m)]
    used = {}
    for p, mask in masks.items():
        used[p] = Fraction(mask.bit_count(), maximum)
        while mask:
            bit = mask & -mask; i = bit.bit_length() - 1
            incident[i].append(p); mask -= bit
    for i in range(m):
        if not incident[i]:
            return []
        delta = min(1 - used[p] for p in incident[i])
        y[i] += delta
        for p in incident[i]:
            used[p] += delta
    return [[x.numerator, x.denominator] for x in y]


def check_dual(ctx: Context, weights: list[list[int]]) -> Fraction:
    targets, masks = cover_sets(ctx)
    if len(weights) != len(targets):
        raise ModelError('dual length mismatch')
    y = []
    for pair in weights:
        if type(pair) is not list or len(pair) != 2:
            raise ModelError('invalid rational')
        a, b = integer(pair[0], 'numerator'), integer(pair[1], 'denominator', 1)
        y.append(Fraction(a, b))
    for mask in masks.values():
        total = Fraction(0)
        while mask:
            bit = mask & -mask; total += y[bit.bit_length() - 1]; mask -= bit
        if total > 1:
            raise ModelError('dual capacity violation')
    return sum(y, Fraction(0))


def propagated(ctx: Context, selected: list[str]) -> list[Bound]:
    """Compute premise closure, validating IDs as in the decision procedure."""
    if type(selected) is not list or any(type(p) is not str for p in selected):
        raise ModelError('certificate facts must be strings in a list')
    if len(set(selected)) != len(selected) or any(p not in ctx.facts for p in selected):
        raise ModelError('duplicate or unknown fact')
    low: list[Bound] = [(0, 0)] * len(ctx.parents)
    for p in selected:
        v, b = ctx.facts[p]
        low[v] = max(low[v], b)
    for v, ps in enumerate(ctx.parents):
        for p in ps:
            low[v] = max(low[v], low[p])
    return low


def minimum_cut(ctx: Context, selected: list[str]) -> list[int] | None:
    """Unique least robust cut for fixed premises, or None for an unsafe suffix.

    This changes the candidate cut, not the structural header or timing facts.
    The operation is distinct from optimizing premises for a fixed cut.
    """
    low = propagated(ctx, selected)
    model = ctx.model
    n = len(model['events'])
    if any(v >= n and low[v] <= (t, 0) for v, t in ctx.targets):
        return None
    q = model['query']['upper']; budgets = model['query']['budgets']
    needed = set()
    for i, e in enumerate(model['events']):
        if e['feature'] in budgets and low[i] <= (q - budgets[e['feature']], 0):
            needed.add(i)
    for v in reversed(range(n)):
        if v in needed:
            needed.update(ctx.parents[v])
    return sorted(needed)


def counterexample(ctx: Context, selected: list[str]) -> dict | None:
    """An explicit integer world or causal-cut edge witnessing non-certification.

    A world can violate omitted catalog facts: only selected facts are premises.
    It proves non-entailment, not a claim that this was the actual history.
    """
    low = propagated(ctx, selected)
    c = set(ctx.model['cut'])
    for v in sorted(c):
        for p in ctx.parents[v]:
            if p not in c:
                return {'kind': 'cut_edge', 'parent': p, 'child': v}
    failed = next(((v, t) for v, t in ctx.targets if low[v] <= (t, 0)), None)
    if failed is None:
        return None
    v, threshold = failed
    model = ctx.model; n = len(model['events'])
    # All real-event primitive lower endpoints in the executable model are closed.
    clocks = [low[i][0] for i in range(n)]
    if v < n:
        return {'kind': 'known', 'times': clocks, 'event': v}
    z = n
    budgets = model['query']['budgets']
    for s, source in enumerate(model['sources']):
        fs = set(source['writes']) & budgets.keys()
        if not fs:
            continue
        if z == v:
            f = min(fs, key=lambda f: (budgets[f], f))
            return {'kind': 'suffix', 'times': clocks, 'source': s,
                    'feature': f, 'time': threshold}
        z += 1
    raise AssertionError('unknown obligation vertex')


def weighted_chain_optimum(ctx: Context, costs: dict[str, int]) -> list[str] | None:
    """Exact nonnegative additive-cost optimization on independent chains.

    Prune dominated obligations, NOT dominated facts (which may be cheaper).
    Each remaining fact covers an interval of record obligations. A range-min
    shortest-path recurrence computes a minimum-cost cover of that sequence.
    """
    if type(costs) is not dict or set(costs) != set(ctx.facts):
        raise ModelError('one cost is required for every catalog fact')
    for value in costs.values():
        integer(value, 'cost')
    if not ctx.causal:
        return None
    events = ctx.model['events']; sources = ctx.model['sources']
    for e in events:
        if any(events[p]['source'] != e['source'] for p in e['parents']):
            raise ModelError('weighted chain algorithm requires no cross-source edges')
    node_source = [e['source'] for e in events]
    budgets = ctx.model['query']['budgets']
    for s, source in enumerate(sources):
        if set(source['writes']) & budgets.keys():
            node_source.append(s)
    grouped_targets: list[list[tuple[int, int]]] = [[] for _ in sources]
    grouped_facts: list[list[tuple[str, int, Bound]]] = [[] for _ in sources]
    for v, t in ctx.targets:
        if t >= 0:
            grouped_targets[node_source[v]].append((v, t))
    for p, (v, b) in ctx.facts.items():
        grouped_facts[node_source[v]].append((p, v, b))
    selected: list[str] = []
    for s in range(len(sources)):
        records = []
        highest = -1
        # A later obligation with an equal/lower threshold is implied by an
        # earlier harder obligation on the same source chain.
        for v, t in sorted(grouped_targets[s]):
            if t > highest:
                records.append((v, t)); highest = t
        if not records:
            continue
        vertices = [v for v, _ in records]
        thresholds = [t for _, t in records]
        intervals: dict[int, list[tuple[int, str]]] = {}
        for p, v, b in grouped_facts[s]:
            left = bisect.bisect_left(vertices, v)
            right = (bisect.bisect_right(thresholds, b[0]) if b[1]
                     else bisect.bisect_left(thresholds, b[0])) - 1
            if left <= right:
                intervals.setdefault(right + 1, []).append((left, p))
        m = len(records); size = 1
        while size < m + 1: size *= 2
        infinity = sum(costs[p] for p, _, _ in grouped_facts[s]) + 1
        tree = [(infinity, -1)] * (2 * size)
        def put(i: int, value: int) -> None:
            j = i + size; tree[j] = (value, i)
            while j > 1:
                j //= 2; tree[j] = min(tree[2*j], tree[2*j+1])
        def range_min(left: int, right: int) -> tuple[int, int]:
            # Half-open covered-prefix indices [left,right).
            left += size; right += size; answer = (infinity, -1)
            while left < right:
                if left & 1: answer = min(answer, tree[left]); left += 1
                if right & 1: right -= 1; answer = min(answer, tree[right])
                left //= 2; right //= 2
            return answer
        put(0, 0)
        pred: dict[int, tuple[int, str]] = {}
        for end in sorted(intervals):
            best = (infinity, -1, '')
            for left, p in intervals[end]:
                value, previous = range_min(left, end)
                if previous >= 0:
                    best = min(best, (value + costs[p], previous, p))
            if best[1] >= 0:
                put(end, best[0]); pred[end] = (best[1], best[2])
        if m not in pred:
            return None
        j = m
        while j:
            previous, p = pred[j]; selected.append(p); j = previous
    return selected


def budget_envelope(ctx: Context, selected: list[str]) -> dict[str, Bound]:
    """Exact per-feature lower envelope for fixed header, cut and selected facts.

    A new nonnegative budget d passes for feature f iff envelope[f] > (Q-d,0).
    This does not renew a routing epoch or a physically expired assertion.
    Nonideal cuts never certify, regardless of the returned envelope.
    """
    verify(ctx, selected)  # Validate IDs and uniqueness; failure to certify is allowed.
    bounds = propagated(ctx, selected)
    model = ctx.model
    fs = model['query']['budgets']
    buckets: dict[str, list[Bound]] = {f: [] for f in fs}
    cut = set(model['cut'])
    for v, event in enumerate(model['events']):
        if v not in cut and event['feature'] in buckets:
            buckets[event['feature']].append(bounds[v])
    z = len(model['events'])
    for source in model['sources']:
        relevant = set(source['writes']) & fs.keys()
        if relevant:
            for feature in relevant:
                buckets[feature].append(bounds[z])
            z += 1
    assert z == len(ctx.parents)
    # Admission requires every queried feature to have at least one source.
    return {feature: min(values) for feature, values in buckets.items()}
