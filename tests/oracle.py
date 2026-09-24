"""Explicit finite timestamp / one-hidden-update oracle, no producer imports."""
import itertools


def robust(model, selected=None):
    ev, sources = model['events'], model['sources']
    q = model['query']['upper']; budgets = model['query']['budgets']
    cut = set(model['cut'])
    if any(p not in cut for i in cut for p in ev[i]['parents']):
        return False
    chosen = None if selected is None else set(selected)
    intervals = [range((e['lower'] if chosen is None or f'e:{i}' in chosen else 0),
                       min(e['upper'], q) + 1) for i, e in enumerate(ev)]
    any_world = False
    for ts in itertools.product(*intervals):
        if any(ts[p] > ts[i] for i, e in enumerate(ev) for p in e['parents']):
            continue
        any_world = True
        for i, e in enumerate(ev):
            if i not in cut and e['feature'] in budgets and ts[i] <= q - budgets[e['feature']]:
                return False
        for s, source in enumerate(sources):
            tail = [i for i, e in enumerate(ev) if e['source'] == s]
            for f in source['writes']:
                if f not in budgets:
                    continue
                for hidden_time in range(q + 1):
                    if tail and ts[tail[-1]] > hidden_time:
                        continue
                    seal = source['seal'] if chosen is None or f's:{s}' in chosen else None
                    if seal is not None and hidden_time <= seal:
                        continue
                    if hidden_time <= q - budgets[f]:
                        return False
    if not any_world:
        raise ValueError('infeasible oracle input')
    return True
