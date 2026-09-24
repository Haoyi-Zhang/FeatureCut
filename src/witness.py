"""Directly validate a rejection witness; no producer or cover implementation.

The caller must first admit the input shape. This is not an authentication layer.
"""
from __future__ import annotations


def check_witness(model: dict, selected: list[str], witness: dict) -> bool:
    if type(witness) is not dict or type(selected) is not list:
        return False
    if any(type(p) is not str for p in selected) or len(set(selected)) != len(selected):
        return False
    allowed = {f'e:{i}' for i in range(len(model['events']))}
    budgets = model['query']['budgets']
    allowed.update(f's:{s}' for s, src in enumerate(model['sources'])
                   if src['seal'] is not None and set(src['writes']) & budgets.keys())
    if not set(selected) <= allowed:
        return False
    es, cut = model['events'], set(model['cut'])
    if witness.get('kind') == 'cut_edge':
        p, v = witness.get('parent'), witness.get('child')
        return (type(p) is int and type(v) is int and 0 <= v < len(es)
                and v in cut and p not in cut and p in es[v]['parents'])
    clocks = witness.get('times')
    if type(clocks) is not list or len(clocks) != len(es):
        return False
    q = model['query']['upper']; ds = model['query']['budgets']; ps = set(selected)
    for i, (e, t) in enumerate(zip(es, clocks)):
        if type(t) is not int or not 0 <= t <= min(q, e['upper']):
            return False
        if f'e:{i}' in ps and t < e['lower']:
            return False
        if any(clocks[p] > t for p in e['parents']):
            return False
    if witness.get('kind') == 'known':
        v = witness.get('event')
        return (type(v) is int and 0 <= v < len(es) and v not in cut
                and es[v]['feature'] in ds and clocks[v] <= q - ds[es[v]['feature']])
    if witness.get('kind') != 'suffix':
        return False
    s, f, t = witness.get('source'), witness.get('feature'), witness.get('time')
    if type(s) is not int or not 0 <= s < len(model['sources']):
        return False
    source = model['sources'][s]
    if type(t) is not int or type(f) is not str or f not in source['writes'] or f not in ds:
        return False
    if not 0 <= t <= q - ds[f]:
        return False
    if f's:{s}' in ps and not t > source['seal']:
        return False
    return all(clocks[i] <= t for i, e in enumerate(es) if e['source'] == s)
