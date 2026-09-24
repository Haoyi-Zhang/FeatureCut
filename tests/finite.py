"""Bounded exhaustive suites. All choices are explicit, no randomness."""
from __future__ import annotations
import argparse
import itertools as it
import json
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from causalcut import (prepare, verify, greedy, exact, dual_bound, check_dual,
                      counterexample, minimum_cut, chain_optimum, ModelError)
from checker import check
from witness import check_witness
from resources import begin, finish
from oracle import robust


def event(i, parents, lower, upper=2, source=None, seq=0, feature=None):
    return dict(id=i, source=i if source is None else source, seq=seq,
                feature=f'f{i}' if feature is None else feature,
                parents=parents, lower=lower, upper=upper)


def dag_parents(n, mask):
    ps = [[] for _ in range(n)]; j=0
    for u in range(n):
        for v in range(u+1,n):
            if mask & (1 << j): ps[v].append(u)
            j+=1
    return ps


def powerset(xs):
    for k in range(len(xs)+1):
        for part in it.combinations(xs,k): yield list(part)


def full4(shard):
    n=4; d={'suite':'full4','shard':shard,'shards':8,
           'dag_masks':list(range(shard*8,(shard+1)*8)),
           'interval_tuples_per_dag':1296,'cut_subsets':16,'budget_patterns':2,
           'admitted_decisions':0,'infeasible_catalogs':0,'rejection_witnesses':0,
           'cut_only_false_acceptances':0,'disagreements':0}
    intervals=list(it.combinations_with_replacement(range(3),2))
    for mask in d['dag_masks']:
        ps=dag_parents(n,mask)
        for ranges in it.product(intervals,repeat=n):
            es=[event(i,ps[i],lo,hi) for i,(lo,hi) in enumerate(ranges)]
            sources=[dict(id=i,writes=[f'f{i}'],seal=0 if i%2 else None) for i in range(n)]
            model=dict(events=es,sources=sources,cut=[],query=dict(upper=2,budgets={f'f{i}':2 for i in range(n)}))
            try: prepare(model)
            except ModelError:
                d['infeasible_catalogs']+=1;continue
            for cm in range(16):
                model['cut']=[i for i in range(n) if cm&(1<<i)]
                for bp in range(2):
                    model['query']['budgets']={f'f{i}':2 if bp==0 or i%2==0 else 1 for i in range(n)}
                    ctx=prepare(model); facts=list(ctx.facts)
                    a=verify(ctx,facts)['accepted']; b=robust(model,facts); c=check(model,facts)
                    d['admitted_decisions']+=1
                    if not a==b==c:
                        raise AssertionError(('decision disagreement',model,a,b,c))
                    if ctx.causal and not a: d['cut_only_false_acceptances']+=1
                    if not a:
                        w=counterexample(ctx,facts)
                        if not check_witness(model,facts,w): raise AssertionError(('witness',model,w))
                        d['rejection_witnesses']+=1
    return d


def subsets3():
    d={'suite':'subsets3','dag_edge_sets':8,'lower_tuples':27,'cut_subsets':8,
       'budget_patterns':2,'seal_patterns':3,'certificate_decisions':0,
       'minimum_cut_comparisons':0,'rejection_witnesses':0,'disagreements':0}
    for mask in range(8):
      ps=dag_parents(3,mask)
      for lows in it.product(range(3),repeat=3):
       for seals in ([None]*3,[0]*3,[1,None,1]):
        for bp in range(2):
         model=dict(events=[event(i,ps[i],lows[i]) for i in range(3)],
                    sources=[dict(id=i,writes=[f'f{i}'],seal=seals[i]) for i in range(3)],cut=[],
                    query=dict(upper=2,budgets={f'f{i}':2 if bp==0 or i%2==0 else 1 for i in range(3)}))
         ctx0=prepare(model)
         for facts in powerset(list(ctx0.facts)):
          good=[]
          predicted=minimum_cut(ctx0,facts)
          for cm in range(8):
           model['cut']=[i for i in range(3) if cm&(1<<i)]
           ctx=prepare(model); a=verify(ctx,facts)['accepted']; b=robust(model,facts); c=check(model,facts)
           d['certificate_decisions']+=1
           if not a==b==c: raise AssertionError(('subset',model,facts,a,b,c))
           if a: good.append(set(model['cut']))
           else:
            w=counterexample(ctx,facts)
            if not check_witness(model,facts,w): raise AssertionError(('witness',model,facts,w))
            d['rejection_witnesses']+=1
          if predicted is None:
           if good: raise AssertionError('infeasible minimum cut has valid ideal')
          else:
           p=set(predicted)
           if p not in good or any(not p<=g for g in good): raise AssertionError(('least cut',model,facts,p,good))
          d['minimum_cut_comparisons']+=1
    return d


def cover_case(incidence, m=3, a=3):
    es=[dict(id=0,source=0,seq=0,feature=None,parents=[],lower=0,upper=2)]
    sources=[dict(id=0,writes=[],seal=None)]
    for j in range(a):
        k=len(es);es.append(dict(id=k,source=k,seq=0,feature=None,parents=[0],lower=1,upper=2))
        sources.append(dict(id=k,writes=[],seal=None))
    for i in range(m):
        k=len(es);es.append(event(k,[j+1 for j in range(a) if incidence[j]&(1<<i)],0,feature=f'f{i}'))
        sources.append(dict(id=k,writes=[f'f{i}'],seal=None))
    return dict(events=es,sources=sources,cut=[0],query=dict(upper=2,budgets={f'f{i}':2 for i in range(m)}))


def covers():
    d={'suite':'covers','incidence_matrices':512,'elements':3,'sets':3,
       'feasible':0,'infeasible':0,'greedy_suboptimal':0,'dual_tight':0,
       'certificate_subset_checks':0,'disagreements':0}
    for incidence in it.product(range(8),repeat=3):
        model=cover_case(incidence);ctx=prepare(model)
        opt=None
        for inds in powerset(list(range(3))):
            union=0
            for j in inds: union|=incidence[j]
            truth=union==7
            facts=[f'e:{j+1}' for j in inds]
            if verify(ctx,facts)['accepted']!=truth or check(model,facts)!=truth:
                raise AssertionError(('reduction',incidence,inds))
            d['certificate_subset_checks']+=1
            if truth and opt is None:opt=len(inds)
        g=greedy(ctx);x=exact(ctx)
        if opt is None:
            if g is not None or x is not None:raise AssertionError('false feasible')
            d['infeasible']+=1;continue
        d['feasible']+=1
        if x is None or len(x)!=opt or g is None or not check(model,g):raise AssertionError('optimizer')
        if len(g)>opt:d['greedy_suboptimal']+=1
        if len(g)>sum(1/i for i in range(1,7))*opt+1e-12:raise AssertionError('approximation')
        lb=check_dual(ctx,dual_bound(ctx))
        if lb>opt:raise AssertionError('invalid dual bound')
        if math.ceil(lb)==opt:d['dual_tight']+=1
    return d


def chains():
    d={'suite':'chains','length':4,'lower_tuples':256,'budget_patterns':4,
       'cut_prefixes':5,'seal_values':[None,0,1,2],'instances':0,
       'certificate_subset_checks':0,'feasible':0,'disagreements':0}
    for lows in it.product(range(4),repeat=4):
      es=[event(i,[] if i==0 else [i-1],lows[i],3,0,i,f'f{i%2}') for i in range(4)]
      for b0,b1 in it.product((2,3),repeat=2):
       for k in range(5):
        for seal in d['seal_values']:
         model=dict(events=es,sources=[dict(id=0,writes=['f0','f1'],seal=seal)],cut=list(range(k)),
                    query=dict(upper=3,budgets={'f0':b0,'f1':b1}))
         ctx=prepare(model); sol=chain_optimum(ctx);best=None
         for facts in powerset(list(ctx.facts)):
            d['certificate_subset_checks']+=1
            if check(model,facts):best=facts;break
         d['instances']+=1
         if (sol is None)!=(best is None) or (sol is not None and len(sol)!=len(best)):
            raise AssertionError(('chain optimum',model,sol,best))
         if sol is not None:
            if not robust(model,sol):raise AssertionError(('chain oracle',model,sol))
            d['feasible']+=1
    return d


def main():
    parser=argparse.ArgumentParser();parser.add_argument('suite',choices=['full4','subsets3','covers','chains'])
    parser.add_argument('--shard',type=int,choices=range(8),default=0);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();start=begin()
    d=full4(args.shard) if args.suite=='full4' else globals()[args.suite]()
    d.update(finish(start));args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,sort_keys=True))
if __name__=='__main__':main()
