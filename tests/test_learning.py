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
    def test_history_policy_fails_closed_when_task_list_saturates(self) -> None:
        policy = ANALYZER.load_json(ROOT / "plugins/revit-mcp-cowork/learning/policy.json")
        self.assertEqual(policy["history_task_limit"], 50)
        self.assertTrue(policy["fail_on_history_saturation"])

    def test_repeated_incident_routes_to_existing_skill(self) -> None:
        policy = ANALYZER.load_json(ROOT / "plugins/revit-mcp-cowork/learning/policy.json")
        catalog = ANALYZER.load_json(ROOT / "plugins/revit-mcp-cowork/learning/capabilities.json")
        events = [json.loads(line) for line in (ROOT / "tests/fixtures/sanitized-events.jsonl").read_text().splitlines()]
        report = ANALYZER.analyze(events, policy, catalog)
        self.assertEqual(report["eligible_count"], 1)
        self.assertEqual(report["candidates"][0]["existing_owner"], "work-revit")
        self.assertEqual(report["candidates"][0]["recommended_action"], "update-existing-skill")

    def test_ledger_reopens_only_after_later_evidence_clears_thresholds(self) -> None:
        policy = ANALYZER.load_json(ROOT / "plugins/revit-mcp-cowork/learning/policy.json")
        catalog = ANALYZER.load_json(ROOT / "plugins/revit-mcp-cowork/learning/capabilities.json")
        events = [json.loads(line) for line in (ROOT / "tests/fixtures/sanitized-events.jsonl").read_text().splitlines()]
        incident = ANALYZER.fingerprint(events[0])
        ledger = {
            "schema_version": 1,
            "incidents": [{
                "fingerprint": incident, "status": "dismissed", "plugin_version": "1.1.0",
                "decided_at_utc": "2099-08-03T12:00:00+00:00", "decision": "Covered by existing guidance.",
            }],
        }
        now = ANALYZER.datetime(2099, 9, 1, tzinfo=ANALYZER.timezone.utc)
        suppressed = ANALYZER.analyze(events, policy, catalog, ledger, now=now)
        self.assertEqual(suppressed["eligible_count"], 0)
        self.assertEqual(suppressed["candidates"][0]["occurrences"], 0)

        one_later = dict(events[0], timestamp_utc="2099-08-04T10:00:00+00:00", plugin_version="1.2.0")
        still_suppressed = ANALYZER.analyze(events + [one_later], policy, catalog, ledger, now=now)
        self.assertEqual(still_suppressed["eligible_count"], 0)
        self.assertFalse(still_suppressed["candidates"][0]["reopened_after_decision"])

        later = [
            dict(events[0], timestamp_utc="2099-08-04T10:00:00+00:00", turn_hash="later-turn-00001"),
            dict(events[1], timestamp_utc="2099-08-05T10:00:00+00:00", turn_hash="later-turn-00002"),
            dict(events[2], timestamp_utc="2099-08-05T11:00:00+00:00", turn_hash="later-turn-00003"),
        ]
        reopened = ANALYZER.analyze(events + later, policy, catalog, ledger, now=now)
        self.assertEqual(reopened["eligible_count"], 1)
        self.assertEqual(reopened["candidates"][0]["occurrences"], 3)
        self.assertTrue(reopened["candidates"][0]["reopened_after_decision"])

    def test_invalid_ledger_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid schema"):
            ANALYZER.validate_ledger({"schema_version": 1, "incidents": [{"fingerprint": "a" * 20}]})

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

    def test_unrecognized_error_code_cannot_enter_report(self) -> None:
        catalog = ANALYZER.load_json(ROOT / "plugins/revit-mcp-cowork/learning/capabilities.json")
        now = ANALYZER.datetime(2026, 8, 13, 12, tzinfo=ANALYZER.timezone.utc)
        event = {
            "schema_version": 1, "timestamp_utc": "2026-08-13T10:00:00+00:00",
            "session_hash": "a" * 16, "turn_hash": "b" * 16,
            "tool_name": "mcp__revit-mcp-next__status", "plugin_version": "1.1.0",
            "outcome": "error", "error_code": "CONFIDENTIAL_CLIENT_NAME",
            "input_shape": [], "response_shape": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text(json.dumps(event) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unrecognized error_code"):
                list(ANALYZER.iter_events(
                    [path], ANALYZER.datetime.min.replace(tzinfo=ANALYZER.timezone.utc), 4096,
                    now=now, allowed_error_codes=ANALYZER.known_error_codes(catalog),
                ))
            event["error_code"] = "UNKNOWN_ERROR"
            event["tool_name"] = "mcp__revit-mcp-next__" + ("x" * 1000)
            path.write_text(json.dumps(event) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid tool_name"):
                list(ANALYZER.iter_events(
                    [path], ANALYZER.datetime.min.replace(tzinfo=ANALYZER.timezone.utc), 4096,
                    now=now, allowed_error_codes=ANALYZER.known_error_codes(catalog),
                ))

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
    COLLECTOR = ROOT / "plugins/revit-mcp-cowork/hooks/collect-revit-evidence.ps1"

    def run_collector(self, directory: str, payload: dict) -> Path:
        env = os.environ.copy()
        env["PLUGIN_DATA"] = directory
        env["PLUGIN_ROOT"] = str(ROOT / "plugins/revit-mcp-cowork")
        env["LOCALAPPDATA"] = str(Path(directory) / "local")
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
             str(self.COLLECTOR)],
            input=json.dumps(payload), text=True, env=env, check=True, capture_output=True,
        )
        return Path(directory) / "learning-evidence"

    def test_collector_never_persists_payload_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload = {
                "session_id": "secret-session-id",
                "turn_id": "secret-turn-id",
                "hook_event_name": "PostToolUse",
                "tool_name": "mcp__revit-mcp-next__apply_change_set",
                "tool_input": {"PROJECTNAME": "TOP SECRET", "previewId": "sensitive-token"},
                "tool_response": {"isError": True, "STRUCTUREDCONTENT": {"errorCode": "CHANGE_SET_HASH_MISMATCH", "message": "private model data", "SECRET_PROJECT_ALPHA": True}},
            }
            evidence_root = self.run_collector(directory, payload)
            content = (evidence_root / "events.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("TOP SECRET", content)
            self.assertNotIn("sensitive-token", content)
            self.assertNotIn("private model data", content)
            self.assertNotIn("SECRET_PROJECT_ALPHA", content)
            event = json.loads(content)
            self.assertEqual(event["error_code"], "CHANGE_SET_HASH_MISMATCH")
            self.assertIn("projectName", event["input_shape"])
            self.assertNotIn("PROJECTNAME", event["input_shape"])
            self.assertIn("structuredContent.errorCode", event["response_shape"])
            self.assertLess((evidence_root / "events.jsonl").stat().st_size, 16384)

            payload["turn_id"] = "another-secret-turn"
            payload["tool_response"] = {
                "isError": False,
                "structuredContent": {"error": True, "failed": True, "code": "CONFIDENTIAL_CLIENT_2026"},
            }
            self.run_collector(directory, payload)
            events = [json.loads(line) for line in (evidence_root / "events.jsonl").read_text().splitlines()]
            self.assertEqual(events[1]["outcome"], "success")
            self.assertIsNone(events[1]["error_code"])
            self.assertNotIn("CONFIDENTIAL_CLIENT_2026", json.dumps(events[1]))

            payload["turn_id"] = "explicit-failure-turn"
            payload["tool_response"] = {
                "success": False,
                "structuredContent": {"errorCode": "CHANGE_SET_HASH_MISMATCH"},
            }
            self.run_collector(directory, payload)
            events = [json.loads(line) for line in (evidence_root / "events.jsonl").read_text().splitlines()]
            self.assertEqual(events[2]["outcome"], "error")
            self.assertEqual(events[2]["error_code"], "CHANGE_SET_HASH_MISMATCH")

    def test_collector_rotates_before_append_and_caps_total_logs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            evidence_root = Path(directory) / "learning-evidence"
            evidence_root.mkdir()
            active = evidence_root / "events.jsonl"
            backup = evidence_root / "events.1.jsonl"
            active.write_bytes(b"a" * (5 * 1024 * 1024 - 32))
            backup.write_bytes(b"b" * (6 * 1024 * 1024))
            (evidence_root / "last-pruned.txt").write_text("recent", encoding="utf-8")
            payload = {
                "session_id": "rotation-session",
                "turn_id": "rotation-turn",
                "hook_event_name": "PostToolUse",
                "tool_name": "mcp__revit-mcp-next__status",
                "tool_input": {},
                "tool_response": {"isError": False},
            }

            self.run_collector(directory, payload)

            self.assertTrue(active.is_file())
            self.assertTrue(backup.is_file())
            self.assertLessEqual(active.stat().st_size, 5 * 1024 * 1024)
            self.assertLessEqual(active.stat().st_size + backup.stat().st_size, 10 * 1024 * 1024)
            self.assertEqual(len(active.read_text(encoding="utf-8").splitlines()), 1)

    def test_collector_drops_an_event_over_the_per_event_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload = {
                "session_id": "oversized-session",
                "turn_id": "oversized-turn",
                "hook_event_name": "PostToolUse",
                "tool_name": "mcp__revit-mcp-next__" + ("x" * 20000),
                "tool_input": {"SECRET_" + ("Y" * 20000): "private value"},
                "tool_response": {"isError": False},
            }

            evidence_root = self.run_collector(directory, payload)

            self.assertFalse((evidence_root / "events.jsonl").exists())

    def test_collector_discards_oversized_backup_before_append(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            evidence_root = Path(directory) / "learning-evidence"
            evidence_root.mkdir()
            active = evidence_root / "events.jsonl"
            backup = evidence_root / "events.1.jsonl"
            active.write_bytes(b"a" * 1024)
            backup.write_bytes(b"b" * (10 * 1024 * 1024))
            (evidence_root / "last-pruned.txt").write_text("recent", encoding="utf-8")
            payload = {
                "session_id": "retention-session",
                "turn_id": "retention-turn",
                "hook_event_name": "PostToolUse",
                "tool_name": "mcp__revit-mcp-next__status",
                "tool_input": {},
                "tool_response": {"isError": False},
            }

            self.run_collector(directory, payload)

            self.assertFalse(backup.exists())
            self.assertLessEqual(active.stat().st_size, 10 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
