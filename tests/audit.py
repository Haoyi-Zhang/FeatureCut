"""Independent audit of multi-source optimization, replay, and JSON ingress."""
from __future__ import annotations
import itertools as it
import json
import subprocess
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from causalcut import chain_optimum, prepare, verify, weighted_chain_optimum
from checker import check
from materializer import digest_json, make_packet, prepare_manifest, replay
from resources import begin, finish

def powerset(values):
    for size in range(len(values)+1):
        for subset in it.combinations(values,size): yield list(subset)

def event(identifier, source, sequence, lower, feature, parents):
    return {"id":identifier,"source":source,"seq":sequence,"feature":feature,"parents":parents,"lower":lower,"upper":3}

def multi_source_optimization():
    cuts=[(0,0),(1,0),(0,1),(1,1),(2,1),(1,2),(2,2)]
    seals=[(None,None),(0,None),(None,1),(2,2)]
    result={"models":0,"certificate_subset_checks":0,"weighted_instances":0,"feasible_models":0,"unit_disagreements":0,"weighted_disagreements":0,"decision_disagreements":0,"cut_prefix_patterns":len(cuts),"seal_patterns":len(seals),"cost_patterns":4}
    for lowers in it.product(range(3),repeat=4):
      events=[event(0,0,0,lowers[0],"f",[]),event(1,0,1,lowers[1],"f",[0]),event(2,1,0,lowers[2],"g",[]),event(3,1,1,lowers[3],"g",[2])]
      for f_budget,g_budget in it.product((2,3),repeat=2):
       for prefix0,prefix1 in cuts:
        cut=list(range(prefix0))+list(range(2,2+prefix1))
        for seal0,seal1 in seals:
         model={"events":events,"sources":[{"id":0,"writes":["f"],"seal":seal0},{"id":1,"writes":["g"],"seal":seal1}],"cut":cut,"query":{"upper":3,"budgets":{"f":f_budget,"g":g_budget}}}
         context=prepare(model); facts=list(context.facts); good=[]
         for selected in powerset(facts):
          forward=verify(context,selected)["accepted"]; backward=check(model,selected); result["certificate_subset_checks"]+=1
          if forward!=backward: result["decision_disagreements"]+=1; raise AssertionError((model,selected))
          if forward: good.append(selected)
         unit=chain_optimum(context); best_cardinality=min((len(x) for x in good),default=None); unit_value=None if unit is None else len(unit)
         if unit_value!=best_cardinality or (unit is not None and not check(model,unit)): result["unit_disagreements"]+=1; raise AssertionError((model,unit,best_cardinality))
         if good: result["feasible_models"]+=1
         for pattern in range(4):
          costs={fact:(1 if pattern==0 else index+1 if pattern==1 else len(facts)-index if pattern==2 else (3*index+1)%5) for index,fact in enumerate(facts)}
          optimum=weighted_chain_optimum(context,costs); best_cost=min((sum(costs[f] for f in x) for x in good),default=None); optimum_cost=None if optimum is None else sum(costs[f] for f in optimum); result["weighted_instances"]+=1
          if optimum_cost!=best_cost or (optimum is not None and not check(model,optimum)): result["weighted_disagreements"]+=1; raise AssertionError((model,costs,optimum,best_cost))
         result["models"]+=1
    return result

def small_manifest(shift,prefix0,prefix1):
    events=[event(0,0,0,0,"f",[]),event(1,0,1,1,"f",[0]),event(2,1,0,0,"g",[]),event(3,1,1,1,"g",[2])]
    for row in events: row["upper"]=5
    cut=list(range(prefix0))+list(range(2,2+prefix1))
    payloads=[{"event":0,"entity":"a","value":-3+shift},{"event":1,"entity":"a" if shift%2 else "b","value":7-shift},{"event":2,"entity":"b","value":2*shift-4},{"event":3,"entity":"b" if shift%2 else "a","value":5+shift}]
    outputs=[{"name":f"{feature}_{operator}","feature":feature,"operator":operator} for feature in ("f","g") for operator in ("count","latest","max","sum")]
    return {"schema":1,"epoch":f"audit-{shift}-{prefix0}-{prefix1}","model":{"events":events,"sources":[{"id":0,"writes":["f"],"seal":5},{"id":1,"writes":["g"],"seal":5}],"cut":cut,"query":{"upper":5,"budgets":{"f":5,"g":5}}},"payloads":payloads,"program":{"outputs":sorted(outputs,key=lambda row:row["name"])}}

def replay_oracle(manifest):
    cut=set(manifest["model"]["cut"]); payloads={row["event"]:(row["entity"],row["value"]) for row in manifest["payloads"]}; rows=[]
    for output in manifest["program"]["outputs"]:
      grouped={}
      for event_row in manifest["model"]["events"]:
       if event_row["id"] in cut and event_row["feature"]==output["feature"]:
        entity,value=payloads[event_row["id"]];grouped.setdefault(entity,[]).append((event_row["id"],value))
      values=[]
      for entity in sorted(grouped):
       observations=grouped[entity]; op=output["operator"]
       if op=="count": value=len(observations)
       elif op=="sum": value=sum(item for _,item in observations)
       elif op=="max": value=max(item for _,item in observations)
       elif op=="latest": value=max(observations)[1]
       else: raise AssertionError(op)
       values.append({"entity":entity,"value":value})
      rows.append({"name":output["name"],"values":values})
    return {"features":rows}

def replay_audit():
    cases=0
    for shift in range(5):
      for prefix0,prefix1 in it.product(range(3),repeat=2):
       manifest=small_manifest(shift,prefix0,prefix1); actual=replay(prepare_manifest(manifest)); expected=replay_oracle(manifest)
       if actual!=expected: raise AssertionError((manifest,actual,expected))
       cases+=1
    return {"cases":cases,"operators":4,"features":2,"disagreements":0}

def ingress_audit():
    manifest=small_manifest(0,2,2);packet=make_packet(manifest,["s:0","s:1"]);expected=digest_json(manifest);controls=[]
    with tempfile.TemporaryDirectory(prefix="causal-cut-ingress-") as temporary:
      root=Path(temporary); paths={k:root/f"{k}.json" for k in ("manifest","certificate","packet","output")}
      paths["manifest"].write_text(json.dumps(manifest,separators=(",",":")));paths["certificate"].write_text('{"facts":["s:0","s:1"]}');paths["packet"].write_text(json.dumps(packet,separators=(",",":")))
      dm=root/'duplicate-manifest.json';dm.write_text(paths['manifest'].read_text().replace('{"schema":1','{"schema":1,"schema":1',1));controls.append(("materializer_duplicate_manifest",["src/materializer.py","make",str(dm),str(paths['certificate']),str(paths['output'])]))
      dnm=root/'duplicate-nested-manifest.json';dnm.write_text(paths['manifest'].read_text().replace('{"event":0,"entity"','{"event":0,"event":0,"entity"',1));controls.append(("materializer_duplicate_nested_manifest",["src/materializer.py","make",str(dnm),str(paths['certificate']),str(paths['output'])]))
      dc=root/'duplicate-certificate.json';dc.write_text('{"facts":["s:0","s:1"],"facts":["s:0","s:1"]}');controls.append(("materializer_duplicate_certificate",["src/materializer.py","make",str(paths['manifest']),str(dc),str(paths['output'])]))
      dp=root/'duplicate-packet.json';dp.write_text(paths['packet'].read_text().replace('{"schema":1','{"schema":1,"schema":1',1));controls.append(("materializer_duplicate_packet",["src/materializer.py","check",str(paths['manifest']),str(dp),"--expected",expected]))
      model=manifest['model'];mp=root/'model.json';mp.write_text(json.dumps(model,separators=(",",":")));cc=root/'checker-certificate.json';cc.write_text('{"facts":["s:0","s:1"]}')
      dmodel=root/'duplicate-model.json';dmodel.write_text(mp.read_text()[:-1]+',"query":'+json.dumps(model['query'],separators=(",",":"))+'}')
      controls.append(("checker_duplicate_model",["src/checker.py",str(dmodel),str(cc)]));controls.append(("producer_duplicate_model",["src/cli.py",str(dmodel),"--method","greedy","--output",str(paths['output'])]))
      dcc=root/'duplicate-checker-certificate.json';dcc.write_text('{"facts":["s:0","s:1"],"facts":["s:0","s:1"]}');controls.append(("checker_duplicate_certificate",["src/checker.py",str(mp),str(dcc)]))
      outcomes=[]
      for name,args in controls:
       completed=subprocess.run([sys.executable,*args],cwd=ROOT,capture_output=True,text=True,timeout=10)
       if completed.returncode!=2: raise AssertionError((name,completed.returncode,completed.stdout,completed.stderr))
       outcomes.append({"name":name,"return_code":completed.returncode})
    return {"controls":outcomes,"control_count":len(outcomes),"all_rejected_before_interpretation":True}

def main():
    start=begin();result={"suite":"independent_audit","multi_source_optimization":multi_source_optimization(),"replay":replay_audit(),"ingress":ingress_audit()};result.update(finish(start));(ROOT/'results/audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({"suite":result['suite'],"models":result['multi_source_optimization']['models'],"weighted_instances":result['multi_source_optimization']['weighted_instances'],"replay_cases":result['replay']['cases'],"ingress_controls":result['ingress']['control_count'],"cpu_seconds":result['cpu_seconds']}))
if __name__=='__main__':main()
