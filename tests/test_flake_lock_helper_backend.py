import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from nix_control_manager.flake_lock_helper_backend import LiveFlakeLockHelperBackend
from nix_control_manager.flake_lock_update import plan_flake_lock_update, source_manifest
from nix_control_manager.helper_service import (
    FLAKE_LOCK_APPLY_ACTION_ID,
    HelperDispatcher,
    HelperTarget,
    MockPolkitAuthorizer,
)
from nix_control_manager.transaction import (
    SimulatedTransactionCrash,
    apply_flake_lock_update_live,
    recover_pending_flake_lock_live_transactions,
)


def lock(revision: str, nar_hash: str) -> str:
    return json.dumps(
        {
            "nodes": {
                "root": {"inputs": {"nixpkgs": "nixpkgs"}},
                "nixpkgs": {
                    "locked": {
                        "type": "github",
                        "owner": "NixOS",
                        "repo": "nixpkgs",
                        "rev": revision,
                        "narHash": nar_hash,
                    },
                    "original": {
                        "type": "github",
                        "owner": "NixOS",
                        "repo": "nixpkgs",
                    },
                },
            },
            "root": "root",
            "version": 7,
        },
        indent=2,
    ) + "\n"


class FlakeLockHelperBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / "etc" / "nixos"
        self.root.mkdir(parents=True)
        (self.root / "flake.nix").write_text("{ outputs = _: {}; }\n", encoding="utf-8")
        self.before = lock("a" * 40, "sha256-old")
        self.after = lock("b" * 40, "sha256-new")
        (self.root / "flake.lock").write_text(self.before, encoding="utf-8")
        self.journal = base / "flake-journal"
        self.target = HelperTarget(
            target_id="control",
            configuration_root=self.root,
            allowed_relative_paths=frozenset({"ncm/state.json", "ncm/packages.nix"}),
            fixture_only=False,
            apply_enabled=False,
            flake_target="host",
            test_activation_enabled=True,
            test_journal_root=base / "test-journal",
            managed_write_enabled=True,
            managed_journal_root=base / "managed-journal",
            permanent_switch_enabled=True,
            flake_lock_write_enabled=True,
            flake_lock_journal_root=self.journal,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "/nix/store/test.drv\n", "")

    def request(self):
        fingerprint, _, _ = source_manifest(self.root)
        plan = plan_flake_lock_update(
            self.root,
            input_name="nixpkgs",
            source_fingerprint=fingerprint,
            candidate=self.after,
        )
        return plan, {
            "schemaVersion": 1,
            "requestId": "flake-validate1",
            "operation": "validate-flake-lock-update",
            "payload": {
                "targetId": "control",
                "planFingerprint": plan.plan_fingerprint,
                "inputName": "nixpkgs",
                "sourceFingerprint": fingerprint,
                "changes": [
                    {
                        "relativePath": "flake.lock",
                        "action": "modify",
                        "previousSha256": plan.change.previous_sha256,
                        "candidateSha256": plan.change.candidate_sha256,
                        "candidate": self.after,
                    }
                ],
            },
        }

    def test_exact_receipt_commits_only_flake_lock_after_two_evaluations(self) -> None:
        authorizer = MockPolkitAuthorizer(allowed={(1000, FLAKE_LOCK_APPLY_ACTION_ID)})
        dispatcher = HelperDispatcher(
            targets=(self.target,),
            authorizer=authorizer,
            backend=LiveFlakeLockHelperBackend(
                runner=self.runner, which=lambda name: "/bin/nix" if name == "nix" else None
            ),
        )
        plan, request = self.request()
        validated = dispatcher.handle(request, peer_uid=1000)
        self.assertEqual(validated["status"], "ok", validated)
        applied = dispatcher.handle(
            {
                "schemaVersion": 1,
                "requestId": "flake-apply001",
                "operation": "apply-validated-flake-lock-update",
                "payload": {
                    "targetId": "control",
                    "planFingerprint": plan.plan_fingerprint,
                    "validationReceipt": validated["result"]["validationReceipt"],
                },
            },
            peer_uid=1000,
        )
        self.assertEqual(applied["status"], "ok", applied)
        self.assertEqual(applied["result"]["state"], "committed")
        self.assertEqual(applied["result"]["filesWritten"], 1)
        self.assertEqual((self.root / "flake.lock").read_text(encoding="utf-8"), self.after)
        manifest = json.loads(next(self.journal.glob("*/manifest.json")).read_text())
        self.assertEqual(manifest["transactionKind"], "flake-lock-update")
        self.assertEqual([item["path"] for item in manifest["changes"]], ["flake.lock"])

    def test_source_edit_after_preview_is_rejected_before_receipt(self) -> None:
        dispatcher = HelperDispatcher(
            targets=(self.target,),
            authorizer=MockPolkitAuthorizer(),
            backend=LiveFlakeLockHelperBackend(
                runner=self.runner, which=lambda name: "/bin/nix" if name == "nix" else None
            ),
        )
        _, request = self.request()
        (self.root / "flake.nix").write_text("{ outputs = _: { changed = true; }; }\n")
        response = dispatcher.handle(request, peer_uid=1000)
        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"]["code"], "plan-mismatch")
        self.assertEqual((self.root / "flake.lock").read_text(), self.before)

    def test_protocol_rejects_a_second_candidate_path(self) -> None:
        dispatcher = HelperDispatcher(
            targets=(self.target,),
            authorizer=MockPolkitAuthorizer(),
            backend=LiveFlakeLockHelperBackend(),
        )
        _, request = self.request()
        request["payload"]["changes"].append(
            {**request["payload"]["changes"][0], "relativePath": "flake.nix"}
        )
        response = dispatcher.handle(request, peer_uid=1000)
        self.assertEqual(response["error"]["code"], "path-not-allowed")

    def test_interrupted_one_file_commit_recovers_only_the_previous_lock(self) -> None:
        plan, _ = self.request()
        validation = {
            "status": "passed",
            "workingCopyRemoved": True,
            "planFingerprint": plan.plan_fingerprint,
            "writeScope": ["flake.lock"],
        }
        with self.assertRaises(SimulatedTransactionCrash):
            apply_flake_lock_update_live(
                plan.change,
                root=self.root,
                plan_fingerprint=plan.plan_fingerprint,
                validation=validation,
                journal_root=self.journal,
                fault_after_commits=1,
                simulate_crash=True,
            )
        self.assertEqual((self.root / "flake.lock").read_text(), self.after)
        recovered = recover_pending_flake_lock_live_transactions(
            self.root, journal_root=self.journal
        )
        self.assertEqual(len(recovered), 1)
        self.assertEqual((self.root / "flake.lock").read_text(), self.before)


if __name__ == "__main__":
    unittest.main()
