"""Produce or explain a timing certificate from an admitted JSON catalog."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from causalcut import prepare, greedy, chain_optimum, exact, verify, counterexample, minimum_cut, ModelError
from checker import no_duplicates, check
from resources import begin

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case',type=Path)
    parser.add_argument('--method',choices=['greedy','chain','exact','full'],default='greedy')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); begin()
    try:
        model=json.loads(args.case.read_text(),object_pairs_hook=no_duplicates)
        ctx=prepare(model)
        facts=(list(ctx.facts) if args.method=='full' else
               {'greedy':greedy,'chain':chain_optimum,'exact':exact}[args.method](ctx))
        if facts is None or not verify(ctx,facts)['accepted']:
            evidence={'accepted':False,'witness':counterexample(ctx,list(ctx.facts)),
                      'minimum_cut_with_full_facts':minimum_cut(ctx,list(ctx.facts))}
            args.output.write_text(json.dumps(evidence,indent=2)+'\n')
            print('No certificate for this cut under the chosen method.');return 1
        if not check(model,facts): raise AssertionError('separate checker disagrees')
        args.output.write_text(json.dumps({'facts':facts},indent=2)+'\n')
        print(json.dumps({'accepted':True,'fact_count':len(facts)}));return 0
    except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:
        print(json.dumps({'error':str(exc)}));return 2
if __name__=='__main__': raise SystemExit(main())
