"""Explicit suboptimal greedy control and exact fixed-evidence budget envelope."""
from __future__ import annotations
import itertools as it
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from causalcut import prepare, verify, exact, greedy, budget_envelope
from checker import check
from resources import begin, finish
from finite import event, dag_parents, powerset, cover_case
from oracle import robust

def run():
    root = Path(__file__).resolve().parents[1]
    case = cover_case([15,19,44], m=6, a=3)
    ctx = prepare(case); g = greedy(ctx); x = exact(ctx)
    assert g is not None and x is not None and len(g)==3 and len(x)==2
    assert check(case,g) and check(case,x)
    (root/'data/controls/greedy-suboptimal.json').write_text(json.dumps(case,indent=2)+'\n')
    d = dict(suite='boundaries', greedy_facts=len(g), exact_facts=len(x),
             envelope_queries=0, fixed_evidence_cases=0, disagreements=0)
    for mask in range(2):
      ps=dag_parents(2,mask)
      for lows in it.product(range(3), repeat=2):
       for seals in ([None,None],[0,0],[1,None]):
        model=dict(events=[event(i,ps[i],lows[i]) for i in range(2)],
                   sources=[dict(id=i,writes=[f'f{i}'],seal=seals[i]) for i in range(2)],
                   cut=[],query=dict(upper=2,budgets={'f0':2,'f1':2}))
        for cm in range(4):
         model['cut']=[i for i in range(2) if cm&(1<<i)]
         ctx=prepare(model)
         for facts in powerset(list(ctx.facts)):
          env=budget_envelope(ctx,facts); d['fixed_evidence_cases']+=1
          for b0,b1 in it.product(range(5),repeat=2):
           model['query']['budgets']={'f0':b0,'f1':b1}
           pred=ctx.causal and all(env[f]>(2-b,0) for f,b in model['query']['budgets'].items())
           fresh=prepare(model)
           assert pred==verify(fresh,facts)['accepted']==check(model,facts)==robust(model,facts)
           d['envelope_queries']+=1
    return d

if __name__=='__main__':
    start=begin(); d=run(); d.update(finish(start))
    p=Path(__file__).resolve().parents[1]/'results/boundaries.json'
    p.write_text(json.dumps(d,indent=2)+'\n'); print(json.dumps(d))
