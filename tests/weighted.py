"""Bounded oracle for the additive-cost chain extension."""
from __future__ import annotations
import argparse
import itertools as it
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from causalcut import prepare, weighted_chain_optimum, chain_optimum
from checker import check
from resources import begin, finish
from finite import event,powerset

def run(n):
    d=dict(suite='weighted_chains',length=n,instances=0,subset_checks=0,feasible=0,
           unit_agreements=0,disagreements=0,cost_patterns=4)
    for lows in it.product(range(4),repeat=n):
      es=[event(i,[] if i==0 else [i-1],lows[i],3,0,i,f'f{i%2}') for i in range(n)]
      for b0,b1 in it.product((2,3),repeat=2):
       for k in range(n+1):
        for seal in (None,0,1,2):
         model=dict(events=es,sources=[dict(id=0,writes=['f0','f1'],seal=seal)],cut=list(range(k)),
                    query=dict(upper=3,budgets={'f0':b0,'f1':b1}))
         ctx=prepare(model);ps=list(ctx.facts)
         good=[]
         for facts in powerset(ps):
            d['subset_checks']+=1
            if check(model,facts):good.append(facts)
         for pattern in range(4):
            costs={p:(1 if pattern==0 else (i+1 if pattern==1 else len(ps)-i if pattern==2 else (3*i+1)%5))
                   for i,p in enumerate(ps)}
            sol=weighted_chain_optimum(ctx,costs);d['instances']+=1
            best=min((sum(costs[p] for p in facts) for facts in good),default=None)
            value=None if sol is None else sum(costs[p] for p in sol)
            assert value==best,(model,costs,sol,best)
            if sol is not None:assert check(model,sol);d['feasible']+=1
            if pattern==0:
                unit=chain_optimum(ctx)
                assert (None if unit is None else len(unit))==value
                d['unit_agreements']+=1
    return d

def main():
    p=argparse.ArgumentParser();p.add_argument('--length',type=int,choices=[3,4],required=True)
    a=p.parse_args();start=begin();d=run(a.length);d.update(finish(start))
    out=Path(__file__).resolve().parents[1]/f'results/weighted-{a.length}.json'
    out.write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d))
if __name__=='__main__':main()
