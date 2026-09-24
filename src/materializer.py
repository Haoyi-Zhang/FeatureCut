"""Content-bound deterministic feature replay for causal-cut certificates.

The manifest file is the trusted application object: it contains the admitted
history model, an epoch identifier, event payloads, and a small deterministic
feature program.  A packet carries only its manifest digest, selected timing
facts, and the claimed output.  Acceptance requires an out-of-band expected
manifest digest.  SHA-256 is used for content addressing, not as a signature or
as a source-authentication mechanism.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from causalcut import Context, ModelError, prepare, verify
from resources import begin


class MaterializationError(ValueError):
    """Raised for malformed manifests, programs, or packets."""


OPERATORS = {"count", "sum", "max", "latest"}
HEX = set("0123456789abcdef")


def _exact_dict(value: Any, fields: set[str], name: str) -> dict:
    if type(value) is not dict or set(value) != fields:
        raise MaterializationError(f"{name}: fields must be {sorted(fields)}")
    return value


def _nonempty_string(value: Any, name: str, maximum: int = 256) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise MaterializationError(f"{name}: expected nonempty string of at most {maximum} characters")
    return value


def _integer(value: Any, name: str) -> int:
    if type(value) is not int:
        raise MaterializationError(f"{name}: expected integer")
    return value


def canonical_bytes(value: Any) -> bytes:
    """Canonical UTF-8 JSON representation used by the packet format."""
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as error:
        raise MaterializationError(f"value is not canonical JSON: {error}") from error


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


@dataclass(frozen=True)
class PreparedManifest:
    manifest: dict
    context: Context
    payload_by_event: dict[int, tuple[str, int]]
    outputs: tuple[tuple[str, str, str], ...]
    digest: str


def prepare_manifest(manifest: dict) -> PreparedManifest:
    """Validate a manifest and its deterministic replay program."""
    _exact_dict(manifest, {"schema", "epoch", "model", "payloads", "program"}, "manifest")
    if _integer(manifest["schema"], "manifest.schema") != 1:
        raise MaterializationError("manifest.schema: unsupported schema")
    _nonempty_string(manifest["epoch"], "manifest.epoch", 128)
    try:
        context = prepare(manifest["model"])
    except ModelError as error:
        raise MaterializationError(f"manifest.model: {error}") from error

    payloads = manifest["payloads"]
    if type(payloads) is not list:
        raise MaterializationError("manifest.payloads: expected list")
    feature_events = [event["id"] for event in manifest["model"]["events"] if event["feature"] is not None]
    if len(payloads) != len(feature_events):
        raise MaterializationError("manifest.payloads: exactly one payload is required for every feature event")
    payload_by_event: dict[int, tuple[str, int]] = {}
    for expected, row in zip(feature_events, payloads):
        _exact_dict(row, {"event", "entity", "value"}, "payload")
        event = _integer(row["event"], "payload.event")
        if event != expected:
            raise MaterializationError("manifest.payloads: rows must follow feature-event order exactly")
        entity = _nonempty_string(row["entity"], "payload.entity", 128)
        value = _integer(row["value"], "payload.value")
        payload_by_event[event] = (entity, value)

    program = _exact_dict(manifest["program"], {"outputs"}, "manifest.program")
    raw_outputs = program["outputs"]
    if type(raw_outputs) is not list or not raw_outputs:
        raise MaterializationError("manifest.program.outputs: nonempty list required")
    outputs: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for item in raw_outputs:
        _exact_dict(item, {"name", "feature", "operator"}, "program output")
        name = _nonempty_string(item["name"], "output.name", 128)
        feature = _nonempty_string(item["feature"], "output.feature", 128)
        operator = _nonempty_string(item["operator"], "output.operator", 32)
        if name in seen:
            raise MaterializationError("manifest.program.outputs: duplicate output name")
        if feature not in manifest["model"]["query"]["budgets"]:
            raise MaterializationError("manifest.program.outputs: output feature is not queried")
        if operator not in OPERATORS:
            raise MaterializationError("manifest.program.outputs: unsupported operator")
        seen.add(name)
        outputs.append((name, feature, operator))
    if [name for name, _, _ in outputs] != sorted(name for name, _, _ in outputs):
        raise MaterializationError("manifest.program.outputs: outputs must be sorted by name")

    return PreparedManifest(
        manifest=manifest,
        context=context,
        payload_by_event=payload_by_event,
        outputs=tuple(outputs),
        digest=digest_json(manifest),
    )


def replay(prepared: PreparedManifest) -> dict:
    """Evaluate the declared group-by-entity features over the exact cut."""
    model = prepared.manifest["model"]
    cut = set(model["cut"])
    by_feature: dict[str, list[tuple[int, str, int]]] = {
        feature: [] for _, feature, _ in prepared.outputs
    }
    for event in model["events"]:
        event_id = event["id"]
        feature = event["feature"]
        if event_id in cut and feature in by_feature:
            entity, value = prepared.payload_by_event[event_id]
            by_feature[feature].append((event_id, entity, value))

    materialized: list[dict] = []
    for name, feature, operator in prepared.outputs:
        groups: dict[str, list[tuple[int, int]]] = {}
        for event_id, entity, value in by_feature[feature]:
            groups.setdefault(entity, []).append((event_id, value))
        values: list[dict] = []
        for entity in sorted(groups):
            rows = groups[entity]
            if operator == "count":
                result = len(rows)
            elif operator == "sum":
                result = sum(value for _, value in rows)
            elif operator == "max":
                result = max(value for _, value in rows)
            elif operator == "latest":
                result = max(rows)[1]  # event IDs are unique and topological.
            else:  # pragma: no cover - prepare_manifest rejects this.
                raise AssertionError(operator)
            values.append({"entity": entity, "value": result})
        materialized.append({"name": name, "values": values})
    return {"features": materialized}


def make_packet(manifest: dict, facts: list[str]) -> dict:
    """Create an accepted packet; refuse to label uncertified output."""
    prepared = prepare_manifest(manifest)
    try:
        decision = verify(prepared.context, facts)
    except ModelError as error:
        raise MaterializationError(f"facts: {error}") from error
    if not decision["accepted"]:
        raise MaterializationError("facts do not certify the manifest cut")
    output = replay(prepared)
    return {
        "schema": 1,
        "manifest_sha256": prepared.digest,
        "facts": facts.copy(),
        "output": output,
        "output_sha256": digest_json(output),
    }


def _valid_digest(value: Any) -> bool:
    return type(value) is str and len(value) == 64 and all(character in HEX for character in value)


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict:
    """Reject ambiguous JSON objects at the file boundary."""
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise MaterializationError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def check_packet(manifest: dict, packet: dict, expected_manifest_sha256: str) -> dict:
    """Fail-closed packet verification against a trusted expected digest.

    Malformed objects are returned as rejections rather than being partially
    interpreted.  The reason string is diagnostic and is not part of the proof.
    """
    try:
        if not _valid_digest(expected_manifest_sha256):
            raise MaterializationError("expected manifest digest is malformed")
        prepared = prepare_manifest(manifest)
        _exact_dict(
            packet,
            {"schema", "manifest_sha256", "facts", "output", "output_sha256"},
            "packet",
        )
        if _integer(packet["schema"], "packet.schema") != 1:
            raise MaterializationError("packet.schema: unsupported schema")
        if not _valid_digest(packet["manifest_sha256"]):
            raise MaterializationError("packet.manifest_sha256: malformed digest")
        if not _valid_digest(packet["output_sha256"]):
            raise MaterializationError("packet.output_sha256: malformed digest")
        if prepared.digest != expected_manifest_sha256:
            return {"accepted": False, "reason": "untrusted_manifest"}
        if packet["manifest_sha256"] != prepared.digest:
            return {"accepted": False, "reason": "manifest_mismatch"}
        facts = packet["facts"]
        try:
            decision = verify(prepared.context, facts)
        except ModelError as error:
            return {"accepted": False, "reason": f"invalid_facts:{error}"}
        if not decision["accepted"]:
            return {"accepted": False, "reason": "timing_rejected"}
        expected_output = replay(prepared)
        if digest_json(packet["output"]) != packet["output_sha256"]:
            return {"accepted": False, "reason": "output_digest_mismatch"}
        if packet["output_sha256"] != digest_json(expected_output):
            return {"accepted": False, "reason": "replay_digest_mismatch"}
        if packet["output"] != expected_output:
            return {"accepted": False, "reason": "replay_value_mismatch"}
        return {
            "accepted": True,
            "reason": "accepted",
            "fact_count": len(facts),
            "manifest_sha256": prepared.digest,
            "output_sha256": packet["output_sha256"],
        }
    except (MaterializationError, ModelError, TypeError, ValueError) as error:
        return {"accepted": False, "reason": f"malformed:{error}"}


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(), object_pairs_hook=_no_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise MaterializationError(f"cannot read {path}: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("make", help="create a fail-closed materialization packet")
    make.add_argument("manifest", type=Path)
    make.add_argument("certificate", type=Path, help='JSON object with one "facts" field')
    make.add_argument("output", type=Path)
    check = sub.add_parser("check", help="verify a packet against an expected manifest digest")
    check.add_argument("manifest", type=Path)
    check.add_argument("packet", type=Path)
    check.add_argument("--expected", required=True)
    args = parser.parse_args()
    begin()
    try:
        if args.command == "make":
            manifest = _load(args.manifest)
            certificate = _load(args.certificate)
            _exact_dict(certificate, {"facts"}, "certificate")
            packet = make_packet(manifest, certificate["facts"])
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(packet, sort_keys=True, separators=(",", ":")) + "\n")
            print(json.dumps({"written": str(args.output), "manifest_sha256": packet["manifest_sha256"]}))
            return 0
        result = check_packet(_load(args.manifest), _load(args.packet), args.expected)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["accepted"] else 1
    except MaterializationError as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
