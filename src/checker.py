"""Separately implemented backward certificate checker; does not import producer.

Independence means implementation separation only, not independent authorship or
review. The admitted structural header and fact catalog are trusted inputs.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path


def check(model: dict, selected: list[str]) -> bool:
    if type(selected) is not list or any(type(x) is not str for x in selected):
        return False
    if len(set(selected)) != len(selected):
        return False
    ev = model['events']; src = model['sources']; c = set(model['cut'])
    if any(x < 0 or x >= len(ev) for x in c):
        return False
    if any(p not in c for x in c for p in ev[x]['parents']):
        return False
    facts = set(selected)
    allowed = {f'e:{i}' for i in range(len(ev))} | {
        f's:{s}' for s in range(len(src)) if src[s]['seal'] is not None and
        set(src[s]['writes']) & model['query']['budgets'].keys()}
    if not facts <= allowed:
        return False
    q = model['query']['upper']; budgets = model['query']['budgets']
    tails = [None] * len(src)
    for i, e in enumerate(ev):
        tails[e['source']] = i

    memo: dict[tuple[int, int], bool] = {}

    def late(start: int | None, threshold: int) -> bool:
        if threshold < 0:
            return True
        if start is None:
            return False
        # Demand-driven Boolean reachability, keyed by the tested threshold.
        # This is not the producer's forward numeric-max propagation.
        stack = [(start, False)]
        while stack:
            v, expanded = stack.pop()
            key = (v, threshold)
            if key in memo:
                continue
            if f'e:{v}' in facts and ev[v]['lower'] > threshold:
                memo[key] = True
            elif expanded:
                memo[key] = any(memo[(u, threshold)] for u in ev[v]['parents'])
            else:
                stack.append((v, True))
                stack.extend((u, False) for u in ev[v]['parents']
                             if (u, threshold) not in memo)
        return memo[(start, threshold)]

    for i, e in enumerate(ev):
        if i not in c and e['feature'] in budgets:
            if not late(i, q - budgets[e['feature']]):
                return False
    for s, source in enumerate(src):
        affected = [q - budgets[f] for f in source['writes'] if f in budgets]
        if not affected:
            continue
        t = max(affected)
        if f's:{s}' in facts and source['seal'] >= t:
            continue
        if not late(tails[s], t):
            return False
    return True


def no_duplicates(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError('duplicate JSON key')
        d[k] = v
    return d


def main() -> int:
    if len(sys.argv) != 3:
        print('usage: python src/checker.py CASE.json CERTIFICATE.json', file=sys.stderr)
        return 2
    try:
        from resources import begin
        begin()
        # Schema admission is a separate trusted step; keep the checker algorithm
        # independent while requiring the documented context admission procedure.
        import causalcut
        model = json.loads(Path(sys.argv[1]).read_text(), object_pairs_hook=no_duplicates)
        cert = json.loads(Path(sys.argv[2]).read_text(), object_pairs_hook=no_duplicates)
        causalcut.prepare(model)
        causalcut.keys(cert, {'facts'}, 'certificate')
        selected = cert['facts']
        if type(selected) is not list or any(type(x) is not str for x in selected):
            raise ValueError('facts must be strings')
        ok = check(model, selected)
        print(json.dumps({'accepted': ok}))
        return 0 if ok else 1
    except (OSError, ValueError, KeyError, TypeError, IndexError) as e:
        print(json.dumps({'error': str(e)}))
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
