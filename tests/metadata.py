"""Audit evidence-ledger and bibliography metadata without network access."""
from __future__ import annotations
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from resources import begin, finish

EXPECTED_HEADERS = {
    "claim_evidence_ledger.csv": ["claim_id","claim","main_location","proof_or_checker","source_or_test","experiment","figure_or_table","raw_result","maturity","fresh_recheck","boundary"],
    "external_resources.csv": ["name","scholarly_or_official_url","immutable_scientific_identifier","license","access_date","resource_type","acquisition_method","integration_mode","supported_claim_or_passage","internals_modified","read_scope"],
    "literature_matrix.csv": ["id","paper","primary_url","read_scope","calibration_groups","main_sections","references","motivating_problem","general_principle","proof_or_performance_argument","practical_connection","evaluation_breadth","artifact_strength","narrative_sequence","figure_table_roles"],
    "reference_verification.csv": ["bib_key","cited_in_main","entry_type","title","authors","year","venue","pages","stable_identifier","primary_record","verification_scope","access_date","status"],
}

def load(name: str):
    path=ROOT/name
    with path.open(newline="",encoding="utf-8") as handle:
        reader=csv.DictReader(handle)
        if reader.fieldnames != EXPECTED_HEADERS[name]:
            raise AssertionError((name, reader.fieldnames))
        rows=list(reader)
    for number,row in enumerate(rows,2):
        if None in row or any(value is None for value in row.values()):
            raise AssertionError(f"malformed CSV row {name}:{number}")
    return rows

def unique(rows, field, name):
    values=[row[field].strip() for row in rows]
    if any(not value for value in values) or len(values)!=len(set(values)):
        raise AssertionError(f"missing or duplicate {name}")
    return values

def main():
    start=begin()
    claims=load("claim_evidence_ledger.csv")
    external=load("external_resources.csv")
    literature=load("literature_matrix.csv")
    references=load("reference_verification.csv")
    unique(claims,"claim_id","claim id")
    unique(external,"name","external-resource name")
    unique(literature,"id","literature id")
    unique(references,"bib_key","bibliography key")
    stable=unique(references,"stable_identifier","bibliography stable identifier")
    if len(references)!=36 or any(row["cited_in_main"]!="yes" for row in references):
        raise AssertionError("expected exactly 36 cited bibliography records")
    if any(not row["primary_record"].startswith("https://") for row in references):
        raise AssertionError("every bibliography row needs an HTTPS primary record")
    external_ids={row["immutable_scientific_identifier"] for row in external if row["immutable_scientific_identifier"]}
    if not set(stable) <= external_ids:
        raise AssertionError(f"unledgered bibliography identifiers: {sorted(set(stable)-external_ids)}")
    targeted=[row for row in literature if "targeted-close-work" in row["calibration_groups"].split(";")]
    full=[row for row in literature if row not in targeted]
    if (len(literature),len(full),len(targeted))!=(35,18,17):
        raise AssertionError((len(literature),len(full),len(targeted)))
    groups=Counter(group for row in full for group in row["calibration_groups"].split(";") if group)
    for group,minimum in {"TPDS":12,"adjacent":5,"influential":5}.items():
        if groups[group] < minimum:
            raise AssertionError((group,groups[group],minimum))
    if len(claims)!=21 or len(external)!=46:
        raise AssertionError((len(claims),len(external)))
    result={
        "suite":"metadata_audit",
        "reference_rows":len(references),
        "all_references_cited_and_recorded":True,
        "unique_reference_identifiers":len(stable),
        "literature_rows":len(literature),
        "full_paper_calibration_rows":len(full),
        "targeted_close_work_rows":len(targeted),
        "calibration_group_counts":dict(sorted(groups.items())),
        "claim_ledger_rows":len(claims),
        "external_resource_rows":len(external),
        "boundary":"Standalone audit checks retained metadata and declarations; final packaging separately cross-checks paper citation keys against BibTeX.",
    }
    result.update(finish(start))
    (ROOT/"results/metadata-audit.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k not in {"boundary","calibration_group_counts"}}))

if __name__=="__main__":
    main()
