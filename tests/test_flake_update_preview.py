import json
from pathlib import Path
import tempfile
import time
import unittest

from nix_control_manager.flake_update_preview import FlakeUpdatePreviewManager


TERMINAL = {
    "passed",
    "no-change",
    "failed",
    "cancelled",
    "blocked",
    "unavailable",
}


class FlakeUpdatePreviewManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "configuration"
        self.root.mkdir()
        (self.root / "flake.nix").write_text(
            '{ inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable"; outputs = _: { }; }\n',
            encoding="utf-8",
        )
        self.lock = {
            "nodes": {
                "nixpkgs": {
                    "locked": {
                        "lastModified": 1_786_384_358,
                        "narHash": "sha256-before",
                        "owner": "NixOS",
                        "repo": "nixpkgs",
                        "rev": "a" * 40,
                        "type": "github",
                    },
                    "original": {
                        "owner": "NixOS",
                        "ref": "nixos-unstable",
                        "repo": "nixpkgs",
                        "type": "github",
                    },
                },
                "root": {"inputs": {"nixpkgs": "nixpkgs"}},
            },
            "root": "root",
            "version": 7,
        }
        self.write_lock(self.root / "flake.lock", self.lock)
        self.managers: list[FlakeUpdatePreviewManager] = []

    def tearDown(self) -> None:
        for manager in self.managers:
            manager.close()
        self.temporary.cleanup()

    @staticmethod
    def write_lock(path: Path, value: dict) -> None:
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def manager(self, executor, **kwargs) -> FlakeUpdatePreviewManager:
        timeout = kwargs.pop("timeout", 2)
        manager = FlakeUpdatePreviewManager(
            config_root=self.root,
            timeout=timeout,
            executor=executor,
            which=lambda _: "/run/current-system/sw/bin/nix",
            effective_uid=lambda: None,
            **kwargs,
        )
        self.managers.append(manager)
        return manager

    @staticmethod
    def wait(manager: FlakeUpdatePreviewManager, job_id: str) -> dict:
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            snapshot = manager.poll(job_id)
            if snapshot["status"] in TERMINAL:
                return snapshot
            time.sleep(0.01)
        raise AssertionError("Flake update preview did not finish")

    def test_idle_snapshot_publishes_hard_preview_only_boundary(self) -> None:
        manager = self.manager(lambda *args: (0, ()))

        snapshot = manager.latest()

        self.assertEqual(snapshot["status"], "idle")
        self.assertTrue(snapshot["networkRequired"])
        self.assertFalse(snapshot["sourceWriteEnabled"])
        self.assertTrue(snapshot["temporaryLockWriteEnabled"])
        self.assertTrue(snapshot["nixStoreWriteExpected"])
        self.assertFalse(snapshot["applyEnabled"])
        self.assertFalse(snapshot["activationEnabled"])

    def test_exact_single_input_command_produces_structured_diff(self) -> None:
        calls = []

        def executor(command, cwd, cancel_event, line_sink):
            calls.append((tuple(command), cwd, cancel_event.is_set()))
            updated = json.loads((cwd / "flake.lock").read_text(encoding="utf-8"))
            updated["nodes"]["nixpkgs"]["locked"].update(
                {
                    "lastModified": 1_787_498_568,
                    "narHash": "sha256-after",
                    "rev": "b" * 40,
                }
            )
            self.write_lock(cwd / "flake.lock", updated)
            line_sink("stderr", "a secret-bearing Nix diagnostic must not reach the API")
            return 0, ()

        manager = self.manager(executor)
        started = manager.start("nixpkgs")
        result = self.wait(manager, started["jobId"])

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["before"]["revision"], "a" * 40)
        self.assertEqual(result["after"]["revision"], "b" * 40)
        self.assertEqual(result["changedNodes"], ["nixpkgs"])
        self.assertEqual(result["changedNodeCount"], 1)
        self.assertIn('"rev": "' + "a" * 40 + '"', result["lockDiff"])
        self.assertIn('"rev": "' + "b" * 40 + '"', result["lockDiff"])
        self.assertTrue(result["sourceUnchanged"])
        self.assertTrue(result["candidateOnlyChanges"])
        self.assertTrue(result["temporaryCopyRemoved"])
        self.assertFalse(result["sourceWriteEnabled"])
        self.assertFalse(result["applyEnabled"])
        self.assertTrue(result["readyForApply"])
        self.assertRegex(result["planFingerprint"], r"^[0-9a-f]{64}$")
        self.assertNotIn("privateCandidateLock", result)
        exact = manager.candidate_for_apply(
            started["jobId"], plan_fingerprint=result["planFingerprint"]
        )
        self.assertIn("b" * 40, exact["candidateLock"])
        manager.mark_applied(
            started["jobId"],
            plan_fingerprint=result["planFingerprint"],
            transaction_id="f" * 24,
        )
        applied = manager.poll(started["jobId"])
        self.assertTrue(applied["applied"])
        self.assertFalse(applied["readyForApply"])
        self.assertNotIn("secret-bearing", json.dumps(result))
        command, cwd, cancelled = calls[0]
        self.assertFalse(cancelled)
        self.assertEqual(command[0], "/run/current-system/sw/bin/nix")
        self.assertIn("--no-use-registries", command)
        self.assertIn("--refresh", command)
        self.assertEqual(command[command.index("update") + 1], "nixpkgs")
        self.assertEqual(command[command.index("--flake") + 1], f"path:{cwd}")
        self.assertNotEqual(cwd, self.root)
        self.assertEqual(
            json.loads((self.root / "flake.lock").read_text(encoding="utf-8")),
            self.lock,
        )

    def test_current_input_is_a_distinct_no_change_result(self) -> None:
        manager = self.manager(lambda *args: (0, ()))

        started = manager.start("nixpkgs")
        result = self.wait(manager, started["jobId"])

        self.assertEqual(result["status"], "no-change")
        self.assertEqual(result["before"], result["after"])
        self.assertEqual(result["lockDiff"], "")
        self.assertEqual(result["changedNodes"], [])
        self.assertTrue(result["sourceUnchanged"])

    def test_unknown_and_unsupported_inputs_never_start_nix(self) -> None:
        calls = []
        manager = self.manager(lambda *args: calls.append(args) or (0, ()))

        unknown = self.wait(manager, manager.start("home-manager")["jobId"])
        path_lock = json.loads((self.root / "flake.lock").read_text(encoding="utf-8"))
        path_lock["nodes"]["nixpkgs"]["locked"] = {
            "type": "path",
            "path": "/etc/nixos/local-input",
            "narHash": "sha256-local",
        }
        path_lock["nodes"]["nixpkgs"]["original"] = {
            "type": "path",
            "path": "/etc/nixos/local-input",
        }
        self.write_lock(self.root / "flake.lock", path_lock)
        unsupported = self.wait(manager, manager.start("nixpkgs")["jobId"])

        self.assertEqual(unknown["status"], "blocked")
        self.assertEqual(unknown["error"]["code"], "unknown-input")
        self.assertEqual(unsupported["status"], "blocked")
        self.assertEqual(unsupported["error"]["code"], "unsupported-input")
        self.assertEqual(calls, [])

    def test_candidate_mutation_outside_lock_fails_closed(self) -> None:
        def executor(command, cwd, cancel_event, line_sink):
            (cwd / "flake.nix").write_text("{ outputs = _: { changed = true; }; }\n")
            return 0, ()

        manager = self.manager(executor)

        result = self.wait(manager, manager.start("nixpkgs")["jobId"])

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["code"], "candidate-scope-changed")
        self.assertFalse(result["candidateOnlyChanges"])
        self.assertTrue(result["sourceUnchanged"])

    def test_concurrent_source_edit_invalidates_the_preview(self) -> None:
        def executor(command, cwd, cancel_event, line_sink):
            (self.root / "configuration.nix").write_text("{ networking.hostName = \"edited\"; }\n")
            return 0, ()

        manager = self.manager(executor)

        result = self.wait(manager, manager.start("nixpkgs")["jobId"])

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["code"], "source-changed")
        self.assertFalse(result["sourceUnchanged"])
        self.assertTrue(result["temporaryCopyRemoved"])

    def test_cancellation_removes_the_disposable_copy(self) -> None:
        def executor(command, cwd, cancel_event, line_sink):
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and not cancel_event.is_set():
                time.sleep(0.01)
            return 130, ()

        manager = self.manager(executor)
        started = manager.start("nixpkgs")
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if manager.poll(started["jobId"])["status"] == "running":
                break
            time.sleep(0.01)
        else:
            self.fail("Preview did not reach the network execution stage")
        manager.cancel(started["jobId"])

        result = self.wait(manager, started["jobId"])

        self.assertEqual(result["status"], "cancelled")
        self.assertTrue(result["cancelRequested"])
        self.assertTrue(result["temporaryCopyRemoved"])
        self.assertTrue(result["sourceUnchanged"])

    def test_timeout_stops_nix_and_removes_the_disposable_copy(self) -> None:
        def executor(command, cwd, cancel_event, line_sink):
            while not cancel_event.is_set():
                time.sleep(0.01)
            return 130, ()

        manager = self.manager(executor, timeout=1)

        result = self.wait(manager, manager.start("nixpkgs")["jobId"])

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["code"], "preview-timed-out")
        self.assertTrue(result["timedOut"])
        self.assertTrue(result["temporaryCopyRemoved"])
        self.assertTrue(result["sourceUnchanged"])

    def test_privileged_execution_is_blocked_before_copy_or_nix(self) -> None:
        calls = []
        manager = FlakeUpdatePreviewManager(
            config_root=self.root,
            executor=lambda *args: calls.append(args) or (0, ()),
            which=lambda _: "/bin/nix",
            effective_uid=lambda: 0,
        )
        self.managers.append(manager)

        result = self.wait(manager, manager.start("nixpkgs")["jobId"])

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error"]["code"], "privileged-execution")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
