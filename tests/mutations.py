"""Fixed semantic controls; not a sampled code-mutation score."""
from __future__ import annotations
import copy
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from causalcut import prepare, verify, counterexample, per_target, ModelError
from checker import check
from witness import check_witness
from oracle import robust
from resources import begin,finish

def make(es, sources, budgets, cut=(), q=2):
    return dict(events=[dict(id=i,source=s,seq=seq,feature=f,parents=ps,lower=l,upper=u)
                        for i,(s,seq,f,ps,l,u) in enumerate(es)],
                sources=[dict(id=i,writes=fs,seal=w) for i,(fs,w) in enumerate(sources)],
                cut=list(cut),query=dict(upper=q,budgets=budgets))

def fixtures():
    return [
      ('upper_as_lower',make([(0,0,'f',[],0,2)],[(['f'],1)],{'f':1}),None,False),
      ('closed_event_passes_equality',make([(0,0,'f',[],1,1)],[(['f'],1)],{'f':1}),None,False),
      ('omit_suffix',make([],[(['f'],None)],{'f':1}),None,False),
      ('minimum_routing_threshold',make([],[(['f','g'],0)],{'f':2,'g':1}),None,False),
      ('ignore_closure',make([(0,0,None,[],2,2),(1,0,'f',[0],2,2)],
                             [([],None),(['f'],None)],{'f':2},[1]),None,False),
      ('underestimate_query',make([(0,0,'f',[],1,1)],[(['f'],1)],{'f':1}),None,False),
      ('seal_is_closed',make([],[(['f'],1)],{'f':1}),None,True),
      ('no_ancestor_propagation',make([(0,0,None,[],2,2),(1,0,'f',[0],0,2)],
                                    [([],None),(['f'],None)],{'f':1}),None,True),
      ('global_strictest_threshold',make([(0,0,'f',[],1,1),(1,0,'g',[],2,2)],
                                        [(['f'],None),(['g'],None)],{'f':2,'g':1}),None,True),
      ('use_unselected_facts',make([(0,0,'f',[],2,2)],[(['f'],None)],{'f':1}),[],False)]

def mutant(model,selected,name):
    ctx=prepare(model); low=[(0,0)]*len(ctx.parents)
    if name=='use_unselected_facts':selected=list(ctx.facts)
    for p in selected:
        v,b=ctx.facts[p]
        if name=='upper_as_lower' and v<len(model['events']): b=(model['events'][v]['upper'],0)
        if name=='seal_is_closed' and p.startswith('s:'): b=(b[0],0)
        low[v]=max(low[v],b)
    if name!='no_ancestor_propagation':
        for v,ps in enumerate(ctx.parents):
            for u in ps:low[v]=max(low[v],low[u])
    if name!='ignore_closure' and not ctx.causal:return False
    n=len(model['events']);targets=list(ctx.targets)
    if name=='omit_suffix':targets=[(v,t) for v,t in targets if v<n]
    if name=='minimum_routing_threshold':
        z=n;ds=model['query']['budgets'];q=model['query']['upper'];tm={}
        for source in model['sources']:
            ts=[q-ds[f] for f in source['writes'] if f in ds]
            if ts:tm[z]=min(ts);z+=1
        targets=[(v,tm.get(v,t)) for v,t in targets]
    if name=='global_strictest_threshold':
        t=max(model['query']['upper']-d for d in model['query']['budgets'].values())
        targets=[(v,t) for v,_ in targets]
    if name=='underestimate_query':targets=[(v,t-1) for v,t in targets]
    return all(low[v]>=(t,0) if name=='closed_event_passes_equality' and v<n
               else low[v]>(t,0) for v,t in targets)

def main():
    start=begin();rows=[];root=Path(__file__).resolve().parents[1];out=root/'data/controls';out.mkdir(parents=True,exist_ok=True)
    for name,m,p,truth in fixtures():
        c=prepare(m);p=list(c.facts) if p is None else p
        assert verify(c,p)['accepted']==check(m,p)==robust(m,p)==truth
        changed=mutant(m,p,name);assert changed != truth,(name,changed,truth)
        w=counterexample(c,p)
        if not truth:assert check_witness(m,p,w)
        # Selected-premise parser and witness types must fail closed.
        if w is not None:
            assert not check_witness(m,['unknown'],w)
            assert not check_witness(m,p+p,w) if p else True
        (out/(name+'.json')).write_text(json.dumps({'case':m,'facts':p,'expected':truth},indent=2)+'\n')
        rows.append(dict(control=name,correct=truth,mutated=changed,witness=w))
    bad=[];m=fixtures()[0][1]
    for field,value in [('id',True),('seq',1),('lower',3),('parents',[0]),('feature','unrouted')]:
        x=copy.deepcopy(m);x['events'][0][field]=value;bad.append(x)
    x=copy.deepcopy(m);x['cut']=[True];bad.append(x)
    x=copy.deepcopy(m);x['query']['budgets']['f']=-1;bad.append(x)
    x=copy.deepcopy(m);x['sources'][0]['writes']=[];bad.append(x)
    for x in bad:
        try:prepare(x)
        except ModelError:pass
        else:raise AssertionError('malformed model admitted')
    c=prepare(m)
    for p in [['unknown'],['e:0','e:0'],[0],None]:
        try:verify(c,p)
        except ModelError:pass
        else:raise AssertionError('malformed certificate admitted')
    # Countermodel corruption, including previously unsafe unhashable feature.
    m=fixtures()[2][1];p=[];w=counterexample(prepare(m),p)
    for key,value in [('feature',[]),('time',-1),('source',True),('times',[0])]:
        x=copy.deepcopy(w);x[key]=value;assert not check_witness(m,p,x)
    # Direct ancestor scan checks the strongest-ancestor DP baseline.
    baseline_checks=0
    for _,m,_,_ in fixtures():
        c=prepare(m);chosen=set();valid=c.causal
        for v,t in c.targets:
            if t<0:continue
            anc=set();stack=[v]
            while stack:
                z=stack.pop()
                if z not in anc:anc.add(z);stack.extend(c.parents[z])
            eligible=[p for p,(z,b) in c.facts.items() if z in anc and b>(t,0)]
            if not eligible:valid=False;break
            chosen.add(max(eligible,key=lambda p:(c.facts[p][1],c.facts[p][0],p)))
        assert per_target(c)==(sorted(chosen) if valid else None);baseline_checks+=1
    d=dict(suite='mutations',semantic_controls=rows,killed=len(rows),schema_rejections=len(bad),
           malformed_certificates=4,corrupt_witnesses=4,baseline_comparisons=baseline_checks)
    d.update(finish(start));(root/'results/mutations.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:v for k,v in d.items() if k!='semantic_controls'}))
if __name__=='__main__':main()
