"""Fixed, self-contained synthetic graph families and serial measurements.

These are theorem/method probes, not production feature-store traces. Exact input
JSON is retained so consumers need not rely on a PRNG compatibility assumption.
"""
from __future__ import annotations
import argparse
import copy
import gc
import json
import random
import statistics
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from causalcut import prepare,verify,greedy,per_target,chain_optimum,counterexample
from checker import check
from witness import check_witness
from resources import begin,finish
FAMILIES=['shared','independent','chains','heterogeneous','overlap','dag']
SIZES=[128,1024,8192]
SEEDS=[11,29,47]

def no_duplicates(pairs):
    value={}
    for key,item in pairs:
        if key in value: raise ValueError(f'duplicate JSON key: {key}')
        value[key]=item
    return value

def strict_load(path):
    return json.loads(path.read_text(),object_pairs_hook=no_duplicates)

def build(family:str,n:int,seed:int) -> dict:
    rng=random.Random(seed);es=[];sources=[];cut=[]
    budgets={'f':4};q=4
    def source(writes):
        s=len(sources);sources.append(dict(id=s,writes=writes,seal=None));return s
    def add(s,f,parents,lower,seq=0):
        v=len(es);es.append(dict(id=v,source=s,seq=seq,feature=f,parents=sorted(set(parents)),lower=lower,upper=q));return v
    if family in ('shared','independent','overlap'):
        g=add(source([]),None,[],0);cut=[g]
        a=1 if family=='shared' else n if family=='independent' else max(4,n//8)
        anchors=[add(source([]),None,[g],1) for _ in range(a)]
        for i in range(n):
            ps=anchors if family=='shared' else [anchors[i]] if family=='independent' else rng.sample(anchors,min(4,a))
            add(source(['f']),'f',ps,2 if family=='shared' else 0)
    elif family in ('chains','heterogeneous'):
        budgets={'f':4,'g':2 if family=='heterogeneous' else 4}
        for s in range(8):
            src=source(['f','g']);last=None;vertices=[];length=n//8+(s<n%8)
            for j in range(length):
                low=1+min(2,(3*j)//length)
                v=add(src,'f' if j%2==0 else 'g',[] if last is None else [last],low,j)
                vertices.append(v);last=v
            if family=='heterogeneous':
                bad=[v for v in vertices if es[v]['feature']=='g' and es[v]['lower']<=2]
                if bad:cut.extend(v for v in vertices if v<=max(bad))
    elif family=='dag':
        for i in range(n):
            ps=[] if i<8 else rng.sample(range(i),min(3,i))
            add(source(['f']),'f',ps,1 if not ps else rng.randrange(4))
    else:raise ValueError('unknown family')
    return dict(events=es,sources=sources,cut=cut,query=dict(upper=q,budgets=budgets))

def negative(model:dict)->dict:
    x=copy.deepcopy(model);s=len(x['sources'])
    x['sources'].append(dict(id=s,writes=[min(x['query']['budgets'])],seal=None))
    return x

def timed(fn,repetitions=5):
    values=[];answer=None
    for _ in range(repetitions):
        gc.collect();t=time.perf_counter();answer=fn();values.append(time.perf_counter()-t)
    return answer,dict(seconds=values,median_seconds=statistics.median(values),
                       min_seconds=min(values),max_seconds=max(values))

def run(family,n,seed,input_root=None):
    root=Path(__file__).resolve().parents[1];name=f'{family}-{n}-{seed}'
    folder=(root/'data/workloads') if input_root is None else input_root
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/(name+'.json');badpath=folder/(name+'-unfenced.json')
    if path.exists(): model=strict_load(path)
    else:
        model=build(family,n,seed);path.write_text(json.dumps(model,separators=(',',':'))+'\n')
    bad=negative(model)
    if badpath.exists():assert strict_load(badpath)==bad
    else:badpath.write_text(json.dumps(bad,separators=(',',':'))+'\n')
    ctx,admit=timed(lambda:prepare(model));full=list(ctx.facts)
    assert verify(ctx,full)['accepted'] and check(model,full)
    rows={};solutions={}
    for label,fn in [('all_facts',lambda:full.copy()),('per_target',lambda:per_target(ctx)),('greedy',lambda:greedy(ctx))]:
        sol,timing=timed(fn);assert sol is not None and verify(ctx,sol)['accepted'] and check(model,sol)
        ok,forward=timed(lambda:verify(ctx,sol));assert ok['accepted']
        ok,backward=timed(lambda:check(model,sol));assert ok
        rows[label]=dict(fact_count=len(sol),selection=timing,forward=forward,backward=backward)
        solutions[label]=sol
    if family in ('chains','heterogeneous'):
        sol,timing=timed(lambda:chain_optimum(ctx));assert sol is not None and check(model,sol)
        rows['chain_optimum']=dict(fact_count=len(sol),selection=timing)
        solutions['chain_optimum']=sol
    b=prepare(bad);bp=list(b.facts);w=counterexample(b,bp)
    assert not verify(b,bp)['accepted'] and not check(bad,bp) and check_witness(bad,bp,w)
    assert greedy(b) is None and per_target(b) is None
    certroot=root/'data/certificates';certroot.mkdir(parents=True,exist_ok=True)
    (certroot/(name+'.json')).write_text(json.dumps({'facts':solutions['greedy']},separators=(',',':'))+'\n')
    return dict(suite='workload',family=family,scale=n,seed=seed,repetitions=5,
                events=len(model['events']),edges=sum(len(e['parents']) for e in model['events']),
                sources=len(model['sources']),targets=len(ctx.targets),header_json_bytes=path.stat().st_size,
                known_cut_size=len(model['cut']),fact_catalog=len(full),admission=admit,methods=rows,
                unfenced_pair_rejected=True,unfenced_witness_validated=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('family',choices=FAMILIES);p.add_argument('scale',type=int,choices=SIZES)
    p.add_argument('seed',type=int,choices=SEEDS);p.add_argument('--input-root',type=Path)
    a=p.parse_args();start=begin();d=run(a.family,a.scale,a.seed,a.input_root);d.update(finish(start))
    root=Path(__file__).resolve().parents[1];out=root/'results/workloads';out.mkdir(parents=True,exist_ok=True)
    (out/f'{a.family}-{a.scale}-{a.seed}.json').write_text(json.dumps(d,indent=2)+'\n')
    print(json.dumps({k:v for k,v in d.items() if k not in ('methods','admission')}))
if __name__=='__main__':main()
