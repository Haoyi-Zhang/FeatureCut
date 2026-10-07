"""Finite replay regressions; native imports are the default CI path.

--pure-core explicitly evaluates unchanged pure declarations on a host without
POSIX resource. It does not import or test the native entry point, resource
limits, or campaign. No source body is rewritten and no resource shim is used.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import importlib.util
import itertools
import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = None


def load_materializer(root: Path, pure_core: bool = False):
    source = root / "src" / "materializer.py"
    sys.path.insert(0, str(root / "src"))
    name = "replay_regression_materializer"
    if not pure_core:
        spec = importlib.util.spec_from_file_location(name, source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    declarations = []
    resource_imports = 0
    main_functions = 0
    main_guards = 0
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "resources":
            if [(item.name, item.asname) for item in node.names] != [("begin", None)]:
                raise AssertionError("unexpected resource import: review required")
            resource_imports += 1
        elif isinstance(node, ast.FunctionDef) and node.name == "main":
            main_functions += 1
        elif isinstance(node, ast.If) and ast.unparse(node.test) == "__name__ == '__main__'":
            main_guards += 1
        elif isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef)):
            declarations.append(node)
        elif isinstance(node, ast.Assign) and all(
            isinstance(target, ast.Name) and target.id in {"OPERATORS", "HEX"}
            for target in node.targets
        ):
            declarations.append(node)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            declarations.append(node)
        else:
            raise AssertionError("unexpected top-level source: review required")
    if (resource_imports, main_functions, main_guards) != (1, 1, 1):
        raise AssertionError("native boundary changed: review required")
    module = types.ModuleType(name)
    module.__file__ = str(source)
    sys.modules[name] = module
    exec(compile(ast.Module(body=declarations, type_ignores=[]), str(source), "exec"), module.__dict__)
    return module


def fixture(shift=0, prefixes=(2, 2)):
    """Four events in two independent source chains; no historical code copy."""
    events = []
    payloads = []
    cut = []
    for source, feature in enumerate(("f", "g")):
        for ordinal in range(2):
            identifier = 2 * source + ordinal
            events.append({"id": identifier, "source": source, "seq": ordinal,
                           "feature": feature, "parents": [] if ordinal == 0 else [identifier - 1],
                           "lower": ordinal, "upper": 5})
            payloads.append({"event": identifier, "entity": ("a", "\u03b2", "z")[(identifier + shift) % 3],
                             "value": (identifier + 1) * (shift - 2)})
            if ordinal < prefixes[source]:
                cut.append(identifier)
    outputs = [{"name": feature + "_" + operator, "feature": feature, "operator": operator}
               for feature in ("f", "g") for operator in ("count", "sum", "max", "latest")]
    outputs.append({"name": "z_repeat_f_sum", "feature": "f", "operator": "sum"})
    return {"schema": 1, "epoch": "finite-replay", "model": {
        "events": events, "sources": [{"id": index, "writes": [feature], "seal": 5}
                                        for index, feature in enumerate(("f", "g"))],
        "cut": cut, "query": {"upper": 5, "budgets": {"f": 5, "g": 5}}},
        "payloads": payloads, "program": {"outputs": sorted(outputs, key=lambda row: row["name"])}}


def reference_replay(manifest):
    """Independent scalar reduction per entity, without a grouping cache."""
    events = {row["id"]: row for row in manifest["model"]["events"]}
    cut = set(manifest["model"]["cut"])
    entities = sorted({row["entity"] for row in manifest["payloads"]})
    features = []
    for output in manifest["program"]["outputs"]:
        values = []
        for entity in entities:
            count = 0
            total = 0
            maximum = None
            latest_id = -1
            latest_value = None
            for payload in manifest["payloads"]:
                identifier = payload["event"]
                if identifier not in cut or events[identifier]["feature"] != output["feature"] or payload["entity"] != entity:
                    continue
                value = payload["value"]
                count += 1
                total += value
                maximum = value if maximum is None or value > maximum else maximum
                if identifier > latest_id:
                    latest_id, latest_value = identifier, value
            if count:
                result = {"count": count, "sum": total, "max": maximum, "latest": latest_value}[output["operator"]]
                values.append({"entity": entity, "value": result})
        features.append({"name": output["name"], "values": values})
    return {"features": features}


def reference_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


class ReplayRegression(unittest.TestCase):
    def test_finite_scalar_reference(self):
        for shift, left, right in itertools.product(range(5), range(3), range(3)):
            manifest = fixture(shift, (left, right))
            expected = reference_replay(manifest)
            actual = CORE.replay(CORE.prepare_manifest(manifest))
            self.assertEqual(actual, expected)
            self.assertEqual(CORE.canonical_bytes(actual), reference_bytes(expected))
            self.assertEqual(CORE.digest_json(actual), hashlib.sha256(reference_bytes(expected)).hexdigest())

    def test_latest_is_event_id_and_empty_outputs(self):
        manifest = fixture()
        for row in manifest["payloads"]:
            row["entity"] = "same"
        manifest["payloads"][0]["value"] = 50
        manifest["payloads"][1]["value"] = -10
        output = CORE.replay(CORE.prepare_manifest(manifest))
        self.assertEqual(output, reference_replay(manifest))
        by_name = {row["name"]: row["values"] for row in output["features"]}
        self.assertEqual(by_name["f_latest"], [{"entity": "same", "value": -10}])
        self.assertEqual(by_name["f_max"], [{"entity": "same", "value": 50}])
        manifest["model"]["cut"] = []
        self.assertTrue(all(not row["values"] for row in CORE.replay(CORE.prepare_manifest(manifest))["features"]))

    def test_groups_are_rebuilt_per_call(self):
        prepared = CORE.prepare_manifest(fixture())
        before = CORE.replay(prepared)
        prepared.payload_by_event[0] = ("new-entity", 100)
        after = CORE.replay(prepared)
        self.assertNotEqual(before, after)
        manifest = copy.deepcopy(prepared.manifest)
        manifest["payloads"][0].update(entity="new-entity", value=100)
        self.assertEqual(after, reference_replay(manifest))
        prepared.manifest["model"]["cut"] = [0, 2]
        manifest["model"]["cut"] = [0, 2]
        self.assertEqual(CORE.replay(prepared), reference_replay(manifest))
        # This is a replay-locality probe, not permission to mutate a trusted header.

    def test_fact_lists_and_bindings(self):
        manifest = fixture()
        expected = CORE.digest_json(manifest)
        packet = CORE.make_packet(manifest, ["s:0", "s:1"])
        for facts in (["s:0", "s:1"], ["s:1", "s:0"], ["s:0", "s:1", "e:0"]):
            item = copy.deepcopy(packet)
            item["facts"] = facts
            self.assertTrue(CORE.check_packet(manifest, item, expected)["accepted"])
        for facts, reason in (([], "timing_rejected"), (["s:0", "s:0"], "invalid_facts:certificate facts must be unique strings"),
                              (["unknown"], "invalid_facts:unknown fact identifier")):
            item = copy.deepcopy(packet)
            item["facts"] = facts
            self.assertEqual(CORE.check_packet(manifest, item, expected), {"accepted": False, "reason": reason})
        item = copy.deepcopy(packet)
        item["output"]["features"][0]["values"][0]["value"] += 1
        self.assertEqual(CORE.check_packet(manifest, item, expected)["reason"], "output_digest_mismatch")
        item["output_sha256"] = CORE.digest_json(item["output"])
        self.assertEqual(CORE.check_packet(manifest, item, expected)["reason"], "replay_digest_mismatch")
        self.assertEqual(CORE.check_packet(manifest, packet, "0" * 64)["reason"], "untrusted_manifest")

    def test_checker_replays_each_accepted_packet(self):
        manifest = fixture()
        packet = CORE.make_packet(manifest, ["s:0", "s:1"])
        actual_replay = CORE.replay
        calls = []
        def observed(prepared):
            calls.append(prepared)
            return actual_replay(prepared)
        CORE.replay = observed
        try:
            for _ in range(2):
                self.assertTrue(CORE.check_packet(manifest, packet, CORE.digest_json(manifest))["accepted"])
        finally:
            CORE.replay = actual_replay
        self.assertEqual(len(calls), 2)
        self.assertIsNot(calls[0], calls[1])

    def test_admission_and_duplicate_json_stay_fail_closed(self):
        manifest = fixture()
        packet = CORE.make_packet(manifest, ["s:0", "s:1"])
        for edit in ("program", "payloads", "cut"):
            changed = copy.deepcopy(manifest)
            if edit == "program":
                changed["program"]["outputs"][0]["operator"] = "sum"
            elif edit == "payloads":
                changed["payloads"][0]["value"] += 1
            else:
                changed["model"]["cut"] = [0, 2]
            self.assertFalse(CORE.check_packet(changed, packet, CORE.digest_json(manifest))["accepted"])
        for edit in ("unknown-field", "duplicate-name", "payload-order"):
            changed = copy.deepcopy(manifest)
            if edit == "unknown-field":
                changed["extra"] = 1
            elif edit == "duplicate-name":
                changed["program"]["outputs"][1]["name"] = changed["program"]["outputs"][0]["name"]
            else:
                changed["payloads"].reverse()
            with self.assertRaises(CORE.MaterializationError):
                CORE.prepare_manifest(changed)
        with self.assertRaisesRegex(CORE.MaterializationError, "duplicate JSON key"):
            json.loads('{"schema":1,"schema":2}', object_pairs_hook=CORE._no_duplicates)


def main():
    global CORE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pure-core", action="store_true")
    args = parser.parse_args()
    print("Scope: unchanged pure declarations only; native entry/resource/campaign UNVERIFIED."
          if args.pure_core else "Scope: native module import and finite pure APIs; no campaign or timing.", flush=True)
    CORE = load_materializer(ROOT, args.pure_core)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReplayRegression))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
