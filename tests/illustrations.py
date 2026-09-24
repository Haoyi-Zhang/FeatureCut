"""Retained numeric illustrations; general arguments remain mathematical."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from causalcut import prepare,verify,weighted_chain_optimum,chain_optimum
from checker import check
from resources import begin,finish

def run():
    root=Path(__file__).resolve().parents[1]
    features=[None,None,'f1',None,'f2','f3','f4']
    lows=[9,5,0,9,0,0,0]
    case=dict(events=[dict(id=i,source=0,seq=i,feature=f,parents=[] if i==0 else [i-1],lower=lows[i],upper=10) for i,f in enumerate(features)],
              sources=[dict(id=0,writes=['f1','f2','f3','f4'],seal=None)],cut=[],
              query=dict(upper=10,budgets=dict(f1=7,f2=6,f3=3,f4=2)))
    ctx=prepare(case);costs={p:100 for p in ctx.facts};costs.update({'e:0':5,'e:1':2,'e:3':2})
    weighted=weighted_chain_optimum(ctx,costs);unit=chain_optimum(ctx)
    assert weighted is not None and set(weighted)=={'e:1','e:3'} and unit==['e:0']
    assert check(case,weighted) and check(case,unit)
    (root/'data/controls/weighted-chain-example.json').write_text(json.dumps(case,indent=2)+'\n')
    correlated=dict(events=[dict(id=0,source=0,seq=0,feature=None,parents=[],lower=0,upper=10),
                            dict(id=1,source=1,seq=0,feature='f',parents=[],lower=0,upper=10)],
                    sources=[dict(id=0,writes=[],seal=None),dict(id=1,writes=['f'],seal=None)],
                    cut=[0],query=dict(upper=10,budgets={'f':8}))
    assert not verify(prepare(correlated),[])['accepted'] and not check(correlated,[])
    samples=[(offset,offset+5) for offset in range(6)]
    assert all(0<=u<=10 and 2<v<=10 for u,v in samples)
    (root/'data/controls/correlated-header.json').write_text(json.dumps(correlated,indent=2)+'\n')
    return dict(suite='illustrations',weighted_cost=sum(costs[p] for p in weighted),unit_fact_count=len(unit),
                weighted_selection=weighted,unit_selection=unit,correlation_integer_samples=samples,
                correlation_model_rejected=True,disagreements=0,
                boundary='shared-offset restriction is outside executable admission; six points do not prove its real interval')

if __name__=='__main__':
    start=begin();d=run();d.update(finish(start));p=Path(__file__).resolve().parents[1]/'results/illustrations.json'
    p.write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d))
