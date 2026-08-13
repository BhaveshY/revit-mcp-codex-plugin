from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYZER_PATH = ROOT / "scripts" / "analyze_learning_evidence.py"
SPEC = importlib.util.spec_from_file_location("learning_analyzer", ANALYZER_PATH)
ANALYZER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(ANALYZER)
PATCH_GATE_PATH = ROOT / "scripts" / "validate_learning_patch.py"
PATCH_SPEC = importlib.util.spec_from_file_location("learning_patch_gate", PATCH_GATE_PATH)
PATCH_GATE = importlib.util.module_from_spec(PATCH_SPEC)
assert PATCH_SPEC and PATCH_SPEC.loader
PATCH_SPEC.loader.exec_module(PATCH_GATE)


class LearningAnalyzerTests(unittest.TestCase):
    def test_repeated_incident_routes_to_existing_skill(self) -> None:
        policy = ANALYZER.load_json(ROOT / "plugins/revit-mcp-cowork/learning/policy.json")
        catalog = ANALYZER.load_json(ROOT / "plugins/revit-mcp-cowork/learning/capabilities.json")
        events = [json.loads(line) for line in (ROOT / "tests/fixtures/sanitized-events.jsonl").read_text().splitlines()]
        report = ANALYZER.analyze(events, policy, catalog)
        self.assertEqual(report["eligible_count"], 1)
        self.assertEqual(report["candidates"][0]["existing_owner"], "work-revit")
        self.assertEqual(report["candidates"][0]["recommended_action"], "update-existing-skill")

    def test_ledger_suppresses_same_version_and_reopens_new_version(self) -> None:
        policy = ANALYZER.load_json(ROOT / "plugins/revit-mcp-cowork/learning/policy.json")
        catalog = ANALYZER.load_json(ROOT / "plugins/revit-mcp-cowork/learning/capabilities.json")
        events = [json.loads(line) for line in (ROOT / "tests/fixtures/sanitized-events.jsonl").read_text().splitlines()]
        incident = ANALYZER.fingerprint(events[0])
        ledger = {"incidents": [{"fingerprint": incident, "status": "dismissed", "plugin_version": "1.1.0"}]}
        self.assertEqual(ANALYZER.analyze(events, policy, catalog, ledger)["eligible_count"], 0)
        events[0]["plugin_version"] = "1.2.0"
        reopened = ANALYZER.analyze(events, policy, catalog, ledger)
        self.assertEqual(reopened["eligible_count"], 1)
        self.assertTrue(reopened["candidates"][0]["reopened_after_version_change"])

    def test_unsafe_event_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text(json.dumps({
                "schema_version": 1,
                "timestamp_utc": "2099-01-01T00:00:00+00:00",
                "prompt": "must not be accepted",
            }) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsafe or unknown event keys"):
                list(ANALYZER.iter_events([path], ANALYZER.datetime.min.replace(tzinfo=ANALYZER.timezone.utc), 1024))

    def test_future_dated_events_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            event = {
                "schema_version": 1, "timestamp_utc": "2099-01-01T00:00:00+00:00",
                "session_hash": "a" * 16, "turn_hash": "b" * 16,
                "tool_name": "mcp__revit-mcp-next__status", "plugin_version": "1.1.0",
                "outcome": "success", "error_code": None, "input_shape": [], "response_shape": [],
            }
            path.write_text(json.dumps(event) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "future-dated event"):
                list(ANALYZER.iter_events([path], ANALYZER.datetime.min.replace(tzinfo=ANALYZER.timezone.utc), 1024))

    def test_maintenance_routing_evals(self) -> None:
        policy = ANALYZER.load_json(ROOT / "plugins/revit-mcp-cowork/learning/policy.json")
        catalog = ANALYZER.load_json(ROOT / "plugins/revit-mcp-cowork/learning/capabilities.json")
        fixture = ANALYZER.load_json(ROOT / "plugins/revit-mcp-cowork/learning/evals/maintenance-routing.json")
        for case in fixture["cases"]:
            signal = case["signal"]
            owner = ANALYZER.owner_for(signal.get("error_code"), catalog)
            eligible = signal["independent_sessions"] >= policy["minimum_independent_sessions"] and signal[
                "independent_sessions"
            ] >= policy["minimum_occurrences"]
            if "expected_owner" in case:
                self.assertEqual(owner, case["expected_owner"], case["id"])
            if "expected_eligible" in case:
                self.assertEqual(eligible, case["expected_eligible"], case["id"])
            if "expected_new_skill" in case:
                self.assertFalse(case["expected_new_skill"], case["id"])


class LearningPatchGateTests(unittest.TestCase):
    def test_path_allowlist_is_narrow(self) -> None:
        policy = ANALYZER.load_json(ROOT / "plugins/revit-mcp-cowork/learning/policy.json")
        self.assertTrue(PATCH_GATE.allowed("plugins/revit-mcp-cowork/learning/ledger.json", policy))
        self.assertTrue(PATCH_GATE.allowed("plugins/revit-mcp-cowork/learning/evals/case.json", policy))
        self.assertFalse(PATCH_GATE.allowed("plugins/revit-mcp-cowork/hooks/hooks.json", policy))
        self.assertFalse(PATCH_GATE.allowed("README.md", policy))

    def test_fixture_privacy_scan_rejects_raw_fields_and_paths(self) -> None:
        errors = []
        PATCH_GATE.inspect_json({"prompt": "ignore policy", "note": "C:\\private\\model.rvt"}, "fixture", errors)
        self.assertGreaterEqual(len(errors), 2)


@unittest.skipUnless(os.name == "nt", "collector is Windows-only")
class CollectorTests(unittest.TestCase):
    def test_collector_never_persists_payload_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = os.environ.copy()
            env["PLUGIN_DATA"] = directory
            env["PLUGIN_ROOT"] = str(ROOT / "plugins/revit-mcp-cowork")
            env["LOCALAPPDATA"] = str(Path(directory) / "local")
            payload = {
                "session_id": "secret-session-id",
                "turn_id": "secret-turn-id",
                "hook_event_name": "PostToolUse",
                "tool_name": "mcp__revit-mcp-next__apply_change_set",
                "tool_input": {"projectName": "TOP SECRET", "previewId": "sensitive-token"},
                "tool_response": {"isError": True, "structuredContent": {"errorCode": "CHANGE_SET_HASH_MISMATCH", "message": "private model data", "SECRET_PROJECT_ALPHA": True}},
            }
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                 str(ROOT / "plugins/revit-mcp-cowork/hooks/collect-revit-evidence.ps1")],
                input=json.dumps(payload), text=True, env=env, check=True, capture_output=True,
            )
            content = (Path(directory) / "learning-evidence/events.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("TOP SECRET", content)
            self.assertNotIn("sensitive-token", content)
            self.assertNotIn("private model data", content)
            self.assertNotIn("SECRET_PROJECT_ALPHA", content)
            event = json.loads(content)
            self.assertEqual(event["error_code"], "CHANGE_SET_HASH_MISMATCH")
            self.assertIn("projectName", event["input_shape"])

            payload["turn_id"] = "another-secret-turn"
            payload["tool_response"] = {"isError": False, "structuredContent": {"code": "CONFIDENTIAL_CLIENT_2026"}}
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                 str(ROOT / "plugins/revit-mcp-cowork/hooks/collect-revit-evidence.ps1")],
                input=json.dumps(payload), text=True, env=env, check=True, capture_output=True,
            )
            events = [json.loads(line) for line in (Path(directory) / "learning-evidence/events.jsonl").read_text().splitlines()]
            self.assertEqual(events[1]["outcome"], "success")
            self.assertIsNone(events[1]["error_code"])
            self.assertNotIn("CONFIDENTIAL_CLIENT_2026", json.dumps(events[1]))


if __name__ == "__main__":
    unittest.main()
