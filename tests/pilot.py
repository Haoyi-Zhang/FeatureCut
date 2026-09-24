import itertools, json, sys, time, resource
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from causalcut import prepare, verify, greedy, exact, ModelError
from checker import check
from oracle import robust


def run():
    start=time.process_time(); wall=time.perf_counter(); n=3; cases=0; certificates=0; controls=0; infeasible=0
    edgepairs=[(i,j) for j in range(n) for i in range(j)]
    intervals=[(0,0),(0,1),(0,2),(1,1),(1,2),(2,2)]
    for bits in range(1<<len(edgepairs)):
        ps=[[] for _ in range(n)]
        for k,(i,j) in enumerate(edgepairs):
            if bits>>k&1:ps[j].append(i)
        for ivs in itertools.product(intervals, repeat=n):
            # All 8 topological DAG edge sets, all 216 closed interval tuples,
            # 8 subsets, and two heterogeneous budget patterns.
            base={'events':[{'id':i,'source':i,'seq':0,'feature':f'f{i}', 'parents':ps[i],
                             'lower':ivs[i][0],'upper':ivs[i][1]} for i in range(n)],
                  'sources':[{'id':i,'writes':[f'f{i}'],'seal': 0 if i%2 else None} for i in range(n)],
                  'cut':[], 'query':{'upper':2,'budgets':{f'f{i}':2 for i in range(n)}}}
            try:prepare(base)
            except ModelError:infeasible+=1;continue
            for mask in range(1<<n):
                base['cut']=[i for i in range(n) if mask>>i&1]
                for pattern in [0,1]:
                    base['query']['budgets']={f'f{i}': (2 if pattern==0 else 1+i%2) for i in range(n)}
                    ctx=prepare(base); p=verify(ctx,list(ctx.facts))['accepted']; o=robust(base)
                    assert p==o, (base,p,o)
                    cases+=1
                    if ctx.causal and not o:controls+=1
                    # A deterministic subset of instances also exercises optimizer
                    # and the separately implemented backward verifier.
                    if cases%31==0:
                        a=greedy(ctx); b=exact(ctx)
                        assert (a is None)==(b is None)
                        if a is not None:
                            assert check(base,a) and robust(base,a)
                            assert len(a)>=len(b)
                            certificates+=1
    return {'suite':'pilot','dag_edge_sets':8,'interval_tuples_per_dag':216,'cut_subsets':8,
            'budget_patterns':2,'infeasible_catalogs':infeasible,'admitted_decisions':cases,
            'cut_only_false_acceptances':controls,'optimizer_certificates_checked':certificates,
            'disagreements':0,'cpu_seconds':time.process_time()-start,'wall_seconds':time.perf_counter()-wall,
            'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'workers':1}

if __name__=='__main__':
    from resources import begin
    begin()
    out=run(); print(json.dumps(out,indent=2))
    path=Path(__file__).resolve().parents[1]/'results/pilot.json';path.write_text(json.dumps(out,indent=2)+'\n')
