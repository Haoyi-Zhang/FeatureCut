"""Derive tables and plot input from retained original measurements."""
from __future__ import annotations
import argparse,csv,io,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FAMILIES=['shared','independent','chains','heterogeneous','overlap','dag']


def no_duplicates(pairs):
    value={}
    for key,item in pairs:
        if key in value: raise ValueError(f'duplicate JSON key: {key}')
        value[key]=item
    return value

def load_json(path):
    return json.loads(path.read_text(),object_pairs_hook=no_duplicates)


def derive():
    files=list((ROOT/'results').glob('*.json'))+list((ROOT/'results/workloads').glob('*.json'))
    records=[load_json(p) for p in files if p.name not in {'summary.json','reproduction.json'}]
    full=[j for j in records if j.get('suite')=='full4'];wls=[j for j in records if j.get('suite')=='workload']
    materialization=next((j for j in records if j.get('suite')=='materialization'),None)
    audit=next((j for j in records if j.get('suite')=='independent_audit'),None)
    metadata=next((j for j in records if j.get('suite')=='metadata_audit'),None)
    summary={'full4':{k:sum(j.get(k,0) for j in full) for k in ['admitted_decisions','infeasible_catalogs','rejection_witnesses','cut_only_false_acceptances','disagreements']},
             'workload_runs':len(wls),'workload_rejected_pairs':sum(j['unfenced_pair_rejected'] for j in wls),
             'materialization_cases':0 if materialization is None else materialization['case_count'],
             'materialization_controls':0 if materialization is None else materialization['control_count'],
             'materialization_all_controls_rejected':False if materialization is None else materialization['all_controls_rejected'],
             'audit_multi_source_models':0 if audit is None else audit['multi_source_optimization']['models'],
             'audit_certificate_subset_checks':0 if audit is None else audit['multi_source_optimization']['certificate_subset_checks'],
             'audit_weighted_instances':0 if audit is None else audit['multi_source_optimization']['weighted_instances'],
             'audit_replay_cases':0 if audit is None else audit['replay']['cases'],
             'audit_duplicate_key_controls':0 if audit is None else audit['ingress']['control_count'],
             'audit_all_duplicate_key_controls_rejected':False if audit is None else audit['ingress']['all_rejected_before_interpretation'],
             'audit_disagreements':0 if audit is None else (audit['multi_source_optimization']['unit_disagreements']+audit['multi_source_optimization']['weighted_disagreements']+audit['multi_source_optimization']['decision_disagreements']+audit['replay']['disagreements']),
             'reference_rows':0 if metadata is None else metadata['reference_rows'],
             'all_references_cited_and_recorded':False if metadata is None else metadata['all_references_cited_and_recorded'],
             'literature_rows':0 if metadata is None else metadata['literature_rows'],
             'full_paper_calibration_rows':0 if metadata is None else metadata['full_paper_calibration_rows'],
             'targeted_close_work_rows':0 if metadata is None else metadata['targeted_close_work_rows'],
             'claim_ledger_rows':0 if metadata is None else metadata['claim_ledger_rows'],
             'external_resource_rows':0 if metadata is None else metadata['external_resource_rows'],
             'completed_process_cpu_seconds':sum(j.get('cpu_seconds',0) for j in records),
             'unmeasured_interrupted_driver_cpu_upper_bound_seconds':40,
             'max_recorded_peak_rss_kib':max(j.get('peak_rss_kib',0) for j in records),
             'max_recorded_process_wall_seconds':max(j.get('wall_seconds',0) for j in records),
             'source':'original per-process JSON plus completion-round materialization, independent-audit, and metadata-audit processes; reproduction record is separate'}
    out={'results/summary.json':json.dumps(summary,indent=2)+'\n'}
    buf=io.StringIO(newline='')
    fields=['family','scale','seed','events','edges','sources','targets','header_json_bytes','fact_catalog','method','fact_count','selection_ms','forward_ms','backward_ms','admission_ms']
    w=csv.DictWriter(buf,fieldnames=fields);w.writeheader()
    for j in sorted(wls,key=lambda x:(x['family'],x['scale'],x['seed'])):
      for method,res in j['methods'].items():
        row={k:j[k] for k in fields[:9]}
        row.update(method=method,fact_count=res['fact_count'],admission_ms=1000*j['admission']['median_seconds'])
        row.update({k+'_ms':1000*res[k]['median_seconds'] if k in res else '' for k in ['selection','forward','backward']})
        w.writerow(row)
    out['results/workload-summary.csv']=buf.getvalue()
    plot='n shared independent chains heterogeneous overlap dag\n'
    for n in [128,1024,8192]:
        values=[1000*next(j for j in wls if j['family']==family and j['scale']==n and j['seed']==11)['methods']['greedy']['forward']['median_seconds'] for family in FAMILIES]
        plot+=str(n)+' '+' '.join(f'{v:.8f}' for v in values)+'\n'
    out['results/scaling.dat']=plot
    table=[]
    for family in FAMILIES:
        rows=[j for j in wls if j['family']==family and j['scale']==8192]
        count=lambda method:','.join(map(str,sorted({j['methods'][method]['fact_count'] for j in rows})))
        med=lambda method,k:1000*statistics.median(t for j in rows for t in j['methods'][method][k]['seconds'])
        table.append(f"{family.capitalize()} & {rows[0]['events']:,} & {count('all_facts')} & {count('per_target')} & {count('greedy')} & {med('greedy','selection'):.2f} & {med('greedy','forward'):.2f} "+chr(92)*2)
    out['results/large-table.tex']='\n'.join(table)+'\n'
    if materialization is not None:
        mbuf=io.StringIO(newline='')
        mfields=['pattern','scale','events','sources','cut_events','output_rows','catalog_facts','selected_facts','manifest_bytes','minimal_packet_bytes','full_packet_bytes','warm_bytes_saved','warm_fraction_saved','cold_fraction_saved','manifest_sha256','output_sha256']
        mw=csv.DictWriter(mbuf,fieldnames=mfields);mw.writeheader()
        for row in sorted(materialization['cases'],key=lambda x:(x['pattern'],x['scale'])):
            mw.writerow({key:row[key] for key in mfields})
        out['results/materialization-summary.csv']=mbuf.getvalue()
        largest=[row for row in materialization['cases'] if row['scale']==8192]
        lines=[]
        for row in sorted(largest,key=lambda x:x['pattern'],reverse=True):
            lines.append(
                f"{row['pattern'].capitalize()} & {row['events']:,} & "
                f"{row['selected_facts']:,}/{row['catalog_facts']:,} & "
                f"{row['minimal_packet_bytes']/1024:.1f}/{row['full_packet_bytes']/1024:.1f} & "
                f"{100*row['warm_fraction_saved']:.1f}\\% & {100*row['cold_fraction_saved']:.1f}\\% "+chr(92)*2
            )
        out['results/materialization-table.tex']='\n'.join(lines)+'\n'
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--write',action='store_true');g.add_argument('--check',action='store_true');a=p.parse_args()
    for name,text in derive().items():
        path=ROOT/name
        if a.write:path.write_text(text)
        else:
            if not path.exists() or path.read_text().replace('\r\n','\n')!=text.replace('\r\n','\n'):
                raise SystemExit(f'derived result mismatch: {name}')
    print('Derived summaries, tables and plot data agree with raw records.' if a.check else 'Derived results written.')
