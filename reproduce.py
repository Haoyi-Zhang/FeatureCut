"""Serial bounded reproduction from a fresh private copy; preserves raw evidence."""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
FAMILIES=['shared','independent','chains','heterogeneous','overlap','dag']
TASKS={'pilot':(['tests/pilot.py'],'results/pilot.json')}
for s in range(8):
    TASKS[f'full4-{s}']=(['tests/finite.py','full4','--shard',str(s),'--out',f'results/full4-{s}.json'],f'results/full4-{s}.json')
for name in ['subsets3','covers','chains']:
    TASKS[name]=(['tests/finite.py',name,'--out',f'results/{name}.json'],f'results/{name}.json')
TASKS['mutations']=(['tests/mutations.py'],'results/mutations.json')
for n in [3,4]:
    TASKS[f'weighted-{n}']=(['tests/weighted.py','--length',str(n)],f'results/weighted-{n}.json')
TASKS['boundaries']=(['tests/boundaries.py'],'results/boundaries.json')
TASKS['illustrations']=(['tests/illustrations.py'],'results/illustrations.json')
TASKS['materialization']=(['tests/materialization.py'],'results/materialization.json')
TASKS['audit']=(['tests/audit.py'],'results/audit.json')
TASKS['metadata']=(['tests/metadata.py'],'results/metadata-audit.json')
for family in FAMILIES:
    for n in [128,1024,8192]:
        for seed in [11,29,47]:
            name=f'{family}-{n}-{seed}'
            TASKS[name]=(['tests/workloads.py',family,str(n),str(seed)],f'results/workloads/{name}.json')
MEASUREMENTS={'cpu_seconds','wall_seconds','peak_rss_kib','admission','selection','forward','backward','make_seconds','check_seconds'}

def no_duplicates(pairs):
    value={}
    for key,item in pairs:
        if key in value: raise ValueError(f'duplicate JSON key: {key}')
        value[key]=item
    return value

def load_json(path: Path):
    return json.loads(path.read_text(), object_pairs_hook=no_duplicates)

def semantic(value):
    if isinstance(value,dict):
        return {k:semantic(v) for k,v in value.items() if k not in MEASUREMENTS}
    if isinstance(value,list):return [semantic(v) for v in value]
    return value

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--all',action='store_true');g.add_argument('--task',choices=TASKS)
    g.add_argument('--tasks',nargs='+',choices=TASKS);g.add_argument('--list',action='store_true')
    ap.add_argument('--output',type=Path)
    args=ap.parse_args()
    if args.list:
        print('\n'.join(TASKS));return 0
    names=list(TASKS) if args.all else args.tasks or [args.task]
    if len(set(names))!=len(names):ap.error('duplicate task')
    if hasattr(os,'sched_setaffinity'):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    rows=[]; start=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='causal-cut-reproduction-') as tmp:
      work=Path(tmp)/'artifact'
      shutil.copytree(ROOT,work,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
      for name in names:
        cmd,path=TASKS[name]
        completed=subprocess.run([sys.executable,*cmd],cwd=work,capture_output=True,text=True,timeout=40)
        if completed.returncode:
            raise RuntimeError(f'{name}: exit {completed.returncode}\n{completed.stdout}\n{completed.stderr}')
        expected=load_json(ROOT/path);actual=load_json(work/path)
        if semantic(actual)!=semantic(expected):
            raise AssertionError(f'{name}: semantic result mismatch')
        rows.append(dict(task=name,semantic_equal=True,cpu_seconds=actual.get('cpu_seconds',0),
                         wall_seconds=actual.get('wall_seconds',0),peak_rss_kib=actual.get('peak_rss_kib',0)))
        print(f'{name}: semantic equality',flush=True)
      inputs=0
      for path in sorted((ROOT/'data').rglob('*.json')):
        relative=path.relative_to(ROOT);other=work/relative
        if not other.exists() or path.read_bytes()!=other.read_bytes():
            raise AssertionError(f'changed retained input/certificate bytes: {relative}')
        inputs+=1
      # Detect unexpected generated cases as well as changed/missing originals.
      if {p.relative_to(work/'data') for p in (work/'data').rglob('*.json')} != {p.relative_to(ROOT/'data') for p in (ROOT/'data').rglob('*.json')}:
        raise AssertionError('generated data file set changed')
    result=dict(tasks=rows,task_count=len(rows),all_requested_equal=True,
                exact_json_inputs_and_certificates_compared=inputs,
                byte_identical_json_files_compared=inputs,
                completed_child_cpu_seconds=sum(r['cpu_seconds'] for r in rows),
                peak_child_rss_kib=max(r['peak_rss_kib'] for r in rows),
                wall_seconds=time.perf_counter()-start,
                method='fresh temporary copy; serial children; semantic result comparison excludes timings; retained JSON data compared byte-for-byte')
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='tasks'}))
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError,AssertionError,subprocess.TimeoutExpired) as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
