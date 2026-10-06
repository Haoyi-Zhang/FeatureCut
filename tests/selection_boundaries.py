"""Finite exact-search and integer-cost boundary regressions; no external inputs."""
from __future__ import annotations
import itertools
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from causalcut import exact, prepare, verify, weighted_chain_optimum, ModelError
from checker import check
from resources import begin, finish


def run():
    # Twenty-five zero-bound auxiliary facts have no positive coverage. The
    # useful ancestor, rather than total catalog size, controls the search limit.
    events = [dict(id=i, source=0, seq=i, feature=None,
                   parents=[] if i == 0 else [i-1], lower=0, upper=2)
              for i in range(25)]
    events.append(dict(id=25, source=0, seq=25, feature=None, parents=[24], lower=1, upper=2))
    events.append(dict(id=26, source=1, seq=0, feature='f', parents=[25], lower=0, upper=2))
    model = dict(events=events, sources=[dict(id=0, writes=[], seal=None),
                                        dict(id=1, writes=['f'], seal=None)],
                 cut=[], query=dict(upper=2, budgets={'f':2}))
    context = prepare(model)
    selected = exact(context)
    assert len(context.facts) == 27 and selected == ['e:25']
    assert verify(context, selected)['accepted'] and check(model, selected)

    # Twenty-three independently useful facts exceed the default positive-
    # coverage ceiling even though the structural instance is feasible.
    large = dict(events=[dict(id=i, source=i, seq=0, feature='f', parents=[], lower=1, upper=2)
                         for i in range(23)],
                 sources=[dict(id=i, writes=['f'], seal=None) for i in range(23)],
                 cut=[], query=dict(upper=2, budgets={'f':2}))
    context = prepare(large)
    assert verify(context, list(context.facts))['accepted']
    try:
        exact(context)
    except ModelError as error:
        assert 'ceiling' in str(error)
    else:
        raise AssertionError('positive-coverage fact ceiling was not enforced')

    # With a negative threshold nonnegativity discharges all obligations,
    # including an empty source prefix, without selecting a primitive.
    empty = dict(events=[], sources=[dict(id=0, writes=['f'], seal=None)],
                 cut=[], query=dict(upper=2, budgets={'f':3}))
    context = prepare(empty)
    assert exact(context) == [] and weighted_chain_optimum(context, {}) == []
    assert check(empty, [])

    # Exact integer arithmetic must distinguish adjacent 81-bit costs.
    chain = dict(events=[dict(id=i, source=0, seq=i, feature=None if i == 0 else 'f',
                             parents=[] if i == 0 else [i-1], lower=[2,1,0][i], upper=2)
                         for i in range(3)],
                 sources=[dict(id=0, writes=['f'], seal=None)], cut=[],
                 query=dict(upper=2, budgets={'f':2}))
    context = prepare(chain)
    cost_checks = 0
    for costs in ({'e:0':2**80+1, 'e:1':2**80, 'e:2':0},
                  {'e:0':0, 'e:1':0, 'e:2':0}):
        solution = weighted_chain_optimum(context, costs)
        good = [list(part) for n in range(4) for part in itertools.combinations(costs, n)
                if check(chain, list(part))]
        assert solution is not None and check(chain, solution)
        assert sum(costs[p] for p in solution) == min(sum(costs[p] for p in part) for part in good)
        if costs['e:0']:
            assert solution == ['e:1']
        cost_checks += 1
    return dict(suite='selection_boundaries', catalog_facts_in_small_search=27,
                positive_coverage_ceiling_rejections=1, free_empty_prefix_checks=1,
                integer_cost_optimum_checks=cost_checks, disagreements=0)


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('assertions must be enabled')
    start = begin(); result = run(); result.update(finish(start))
    print(json.dumps(result, sort_keys=True))
