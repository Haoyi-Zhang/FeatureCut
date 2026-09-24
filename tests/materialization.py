"""Deterministic feature replay, content binding, packet bytes, and tamper controls."""
from __future__ import annotations

import copy
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def no_duplicates(pairs):
    value={}
    for key,item in pairs:
        if key in value: raise ValueError(f'duplicate JSON key: {key}')
        value[key]=item
    return value

def strict_load(path):
    return json.loads(path.read_text(),object_pairs_hook=no_duplicates)
sys.path.insert(0, str(ROOT / "src"))

from causalcut import greedy, prepare, verify
from checker import check
from materializer import (
    canonical_bytes,
    check_packet,
    digest_json,
    make_packet,
    prepare_manifest,
    replay,
)
from resources import begin, finish

SIZES = (128, 1024, 8192)
PATTERNS = ("shared", "independent")
PROGRAM = {
    "outputs": [
        {"name": "f_count", "feature": "f", "operator": "count"},
        {"name": "f_latest", "feature": "f", "operator": "latest"},
        {"name": "f_max", "feature": "f", "operator": "max"},
        {"name": "f_sum", "feature": "f", "operator": "sum"},
        {"name": "g_count", "feature": "g", "operator": "count"},
        {"name": "g_latest", "feature": "g", "operator": "latest"},
        {"name": "g_max", "feature": "g", "operator": "max"},
        {"name": "g_sum", "feature": "g", "operator": "sum"},
    ]
}


def payload(event: int, source: int, ordinal: int) -> dict:
    return {
        "event": event,
        "entity": f"entity-{(source * 19 + ordinal * 7) % 64:02d}",
        "value": ((source + 3) * (ordinal + 11) * 17) % 211 - 105,
    }


def shared_manifest(n: int) -> dict:
    source_count = 8
    sources = [{"id": 0, "writes": [], "seal": None}]
    for source in range(1, source_count + 1):
        feature = "f" if source % 3 else "g"
        sources.append({"id": source, "writes": [feature], "seal": None})
    events: list[dict] = []
    payloads: list[dict] = []
    cut: list[int] = []
    seq = [0] * len(sources)

    def add(source: int, feature: str | None, parents: list[int], lower: int, value_ordinal: int = 0) -> int:
        event = len(events)
        events.append(
            {
                "id": event,
                "source": source,
                "seq": seq[source],
                "feature": feature,
                "parents": sorted(set(parents)),
                "lower": lower,
                "upper": 100,
            }
        )
        seq[source] += 1
        if feature is not None:
            payloads.append(payload(event, source, value_ordinal))
        return event

    root = add(0, None, [], 0)
    cut.append(root)
    tails: dict[int, int] = {}
    ordinals = [0] * len(sources)
    base, extra = divmod(n, source_count)
    for source in range(1, source_count + 1):
        length = base + (source <= extra)
        last = root
        for _ in range(length):
            current = add(source, sources[source]["writes"][0], [last], 0, ordinals[source])
            ordinals[source] += 1
            last = current
            cut.append(current)
        tails[source] = last
    anchor = add(0, None, [root, *tails.values()], 95)
    cut.append(anchor)
    for source in range(1, source_count + 1):
        add(
            source,
            sources[source]["writes"][0],
            [tails[source], anchor],
            0,
            ordinals[source],
        )
    model = {
        "events": events,
        "sources": sources,
        "cut": cut,
        "query": {"upper": 100, "budgets": {"f": 20, "g": 10}},
    }
    return {"schema": 1, "epoch": f"shared-{n}", "model": model, "payloads": payloads, "program": PROGRAM}


def independent_manifest(n: int) -> dict:
    sources: list[dict] = []
    events: list[dict] = []
    payloads: list[dict] = []
    cut: list[int] = []
    for source in range(n):
        feature = "f" if source % 3 else "g"
        sources.append({"id": source, "writes": [feature], "seal": None})
        included = len(events)
        events.append(
            {
                "id": included,
                "source": source,
                "seq": 0,
                "feature": feature,
                "parents": [],
                "lower": 0,
                "upper": 100,
            }
        )
        payloads.append(payload(included, source, 0))
        cut.append(included)
        omitted = len(events)
        events.append(
            {
                "id": omitted,
                "source": source,
                "seq": 1,
                "feature": feature,
                "parents": [included],
                "lower": 95,
                "upper": 100,
            }
        )
        payloads.append(payload(omitted, source, 1))
    model = {
        "events": events,
        "sources": sources,
        "cut": cut,
        "query": {"upper": 100, "budgets": {"f": 20, "g": 10}},
    }
    return {
        "schema": 1,
        "epoch": f"independent-{n}",
        "model": model,
        "payloads": payloads,
        "program": PROGRAM,
    }


def build(pattern: str, n: int) -> dict:
    return shared_manifest(n) if pattern == "shared" else independent_manifest(n)


def exact_file(path: Path, value: dict) -> None:
    text = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert strict_load(path) == value, f"retained file differs: {path}"
    else:
        path.write_text(text)


def rows_in_output(output: dict) -> int:
    return sum(len(feature["values"]) for feature in output["features"])


def tamper_controls(manifest: dict, packet: dict, facts: list[str], other_packet: dict) -> list[dict]:
    expected = digest_json(manifest)
    controls: list[tuple[str, dict, dict, str]] = []

    wrong_expected = "0" * 64 if expected != "0" * 64 else "1" * 64
    controls.append(("wrong_expected_digest", manifest, packet, wrong_expected))

    changed = copy.deepcopy(packet)
    changed["manifest_sha256"] = wrong_expected
    controls.append(("packet_manifest_digest", manifest, changed, expected))

    changed = copy.deepcopy(packet)
    changed["output"]["features"][0]["values"][0]["value"] += 1
    controls.append(("output_value_without_digest", manifest, changed, expected))

    changed = copy.deepcopy(packet)
    changed["output"]["features"][0]["values"][0]["value"] += 1
    changed["output_sha256"] = digest_json(changed["output"])
    controls.append(("output_value_with_digest", manifest, changed, expected))

    changed = copy.deepcopy(packet)
    changed["output_sha256"] = wrong_expected
    controls.append(("output_digest", manifest, changed, expected))

    changed = copy.deepcopy(packet)
    changed["facts"] = []
    controls.append(("missing_timing_fact", manifest, changed, expected))

    changed = copy.deepcopy(packet)
    changed["facts"] = facts + [facts[0]]
    controls.append(("duplicate_timing_fact", manifest, changed, expected))

    controls.append(("cross_manifest_packet", manifest, other_packet, expected))

    changed_manifest = copy.deepcopy(manifest)
    changed_manifest["payloads"][0]["value"] += 1
    controls.append(("payload_manifest_change", changed_manifest, packet, expected))

    changed_manifest = copy.deepcopy(manifest)
    changed_manifest["program"]["outputs"][0]["operator"] = "sum"
    controls.append(("program_manifest_change", changed_manifest, packet, expected))

    changed_manifest = copy.deepcopy(manifest)
    changed_manifest["model"]["cut"] = changed_manifest["model"]["cut"][:-1]
    controls.append(("cut_manifest_change", changed_manifest, packet, expected))

    # Rebind the packet to a new listed writer but preserve the old facts/output.
    # This isolates the timing rejection from the digest-mismatch controls.
    changed_manifest = copy.deepcopy(manifest)
    source = len(changed_manifest["model"]["sources"])
    changed_manifest["model"]["sources"].append({"id": source, "writes": ["f"], "seal": None})
    changed = copy.deepcopy(packet)
    changed["manifest_sha256"] = digest_json(changed_manifest)
    controls.append(("listed_unfenced_writer", changed_manifest, changed, changed["manifest_sha256"]))

    changed = copy.deepcopy(packet)
    changed["extra"] = 1
    controls.append(("unknown_packet_field", manifest, changed, expected))

    outcomes = []
    for name, candidate_manifest, candidate_packet, candidate_expected in controls:
        decision = check_packet(candidate_manifest, candidate_packet, candidate_expected)
        assert not decision["accepted"], (name, decision)
        outcomes.append({"name": name, "accepted": False, "reason": decision["reason"]})
    return outcomes


def run() -> dict:
    manifest_root = ROOT / "data" / "materializations"
    packet_root = ROOT / "data" / "materialization-certificates"
    cases = []
    retained: dict[tuple[str, int], tuple[dict, dict, list[str]]] = {}
    for pattern in PATTERNS:
        for n in SIZES:
            manifest = build(pattern, n)
            prepared = prepare_manifest(manifest)
            ctx = prepared.context
            full = list(ctx.facts)
            selected = greedy(ctx)
            assert selected is not None
            assert verify(ctx, selected)["accepted"] and check(manifest["model"], selected)
            assert verify(ctx, full)["accepted"] and check(manifest["model"], full)

            start_make = time.perf_counter()
            minimal_packet = make_packet(manifest, selected)
            make_seconds = time.perf_counter() - start_make
            full_packet = make_packet(manifest, full)
            start_check = time.perf_counter()
            decision = check_packet(manifest, minimal_packet, prepared.digest)
            check_seconds = time.perf_counter() - start_check
            assert decision["accepted"]
            assert check_packet(manifest, full_packet, prepared.digest)["accepted"]
            output = replay(prepared)
            assert minimal_packet["output"] == output == full_packet["output"]

            name = f"{pattern}-{n}"
            exact_file(manifest_root / f"{name}.json", manifest)
            exact_file(packet_root / f"{name}-minimal.json", minimal_packet)
            exact_file(packet_root / f"{name}-full.json", full_packet)
            exact_file(packet_root / f"{name}-facts.json", {"facts": selected})
            manifest_bytes = len(canonical_bytes(manifest))
            minimal_bytes = len(canonical_bytes(minimal_packet))
            full_bytes = len(canonical_bytes(full_packet))
            cases.append(
                {
                    "pattern": pattern,
                    "scale": n,
                    "events": len(manifest["model"]["events"]),
                    "sources": len(manifest["model"]["sources"]),
                    "cut_events": len(manifest["model"]["cut"]),
                    "output_rows": rows_in_output(output),
                    "catalog_facts": len(full),
                    "selected_facts": len(selected),
                    "manifest_bytes": manifest_bytes,
                    "minimal_packet_bytes": minimal_bytes,
                    "full_packet_bytes": full_bytes,
                    "warm_bytes_saved": full_bytes - minimal_bytes,
                    "warm_fraction_saved": (full_bytes - minimal_bytes) / full_bytes,
                    "cold_bytes_saved": full_bytes - minimal_bytes,
                    "cold_fraction_saved": (full_bytes - minimal_bytes) / (manifest_bytes + full_bytes),
                    "make_seconds": make_seconds,
                    "check_seconds": check_seconds,
                    "manifest_sha256": prepared.digest,
                    "output_sha256": minimal_packet["output_sha256"],
                    "forward_and_backward_agree": True,
                }
            )
            retained[(pattern, n)] = (manifest, minimal_packet, selected)

    manifest, packet, selected = retained[("shared", 128)]
    other_packet = retained[("independent", 128)][1]
    controls = tamper_controls(manifest, packet, selected, other_packet)
    return {
        "suite": "materialization",
        "schema": 1,
        "case_count": len(cases),
        "cases": cases,
        "control_count": len(controls),
        "controls": controls,
        "all_cases_accepted": True,
        "all_controls_rejected": True,
        "binding_boundary": "expected SHA-256 digest is an out-of-band trust anchor; no signature or source authentication",
    }


def main() -> None:
    start = begin()
    result = run()
    result.update(finish(start))
    out = ROOT / "results" / "materialization.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "suite": result["suite"],
                "cases": result["case_count"],
                "controls": result["control_count"],
                "cpu_seconds": result["cpu_seconds"],
                "peak_rss_kib": result["peak_rss_kib"],
            }
        )
    )


if __name__ == "__main__":
    main()
