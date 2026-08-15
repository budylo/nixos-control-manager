from pathlib import Path
import tempfile
import unittest

from nix_control_manager.helper_client import (
    build_home_manager_validate_request,
    build_managed_validate_request,
    build_validate_request,
)
from nix_control_manager.model import ManagedState
from nix_control_manager.ui_helper import HelperUiAdapter, HelperUiError


class SequenceSender:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, socket_path, request, *, timeout):
        self.requests.append((socket_path, request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        response["requestId"] = request["requestId"]
        if (
            request["operation"] == "validate-plan"
            and isinstance(response.get("result"), dict)
            and response["result"].get("planFingerprint") == "a" * 64
        ):
            response["result"]["planFingerprint"] = request["payload"][
                "planFingerprint"
            ]
        if (
            request["operation"] == "validate-home-manager-plan"
            and isinstance(response.get("result"), dict)
        ):
            response["result"]["planFingerprint"] = request["payload"][
                "planFingerprint"
            ]
        if (
            request["operation"] == "validate-managed-plan"
            and isinstance(response.get("result"), dict)
        ):
            response["result"]["planFingerprint"] = request["payload"][
                "planFingerprint"
            ]
        if (
            request["operation"] == "preview-activation"
            and isinstance(response.get("result"), dict)
        ):
            response["result"]["planFingerprint"] = request["payload"][
                "planFingerprint"
            ]
            response["result"]["systemPath"] = request["payload"]["systemPath"]
        if request["operation"] == "test-activation" and isinstance(response.get("result"), dict):
            response["result"]["planFingerprint"] = request["payload"]["planFingerprint"]
            response["result"]["systemPath"] = request["payload"]["systemPath"]
        return response


def capabilities(*, safe: bool = True, test_enabled: bool = False) -> dict:
    return {
        "schemaVersion": 1,
        "requestId": "helper-capabilities",
        "status": "ok",
        "result": {
            "protocolVersion": 1,
            "operations": [
                "capabilities",
                "validate-plan",
                "preview-activation",
                "test-activation",
                "recover-test-activation",
            ],
            "targets": [
                {
                    "targetId": "live",
                    "allowedRelativePaths": ["configuration.nix"],
                    "fixtureOnly": False,
                    "liveTarget": True,
                    "readOnly": True,
                    "applyEnabled": not safe,
                    "recoveryEnabled": False,
                    "dryActivatePreviewEnabled": True,
                    "testActivationEnabled": test_enabled,
                    "homeManagerApplyEnabled": False,
                    "homeManagerLiveWriteEnabled": False,
                }
            ],
            "arbitraryCommandsAccepted": False,
            "activationEnabled": False,
        },
        "error": None,
    }


def home_manager_capabilities() -> dict:
    result = capabilities()
    target = result["result"]["targets"][0]
    target["dryActivatePreviewEnabled"] = False
    target["homeManagerApplyEnabled"] = True
    target["homeManagerLiveWriteEnabled"] = True
    result["result"]["operations"].extend(
        ["validate-home-manager-plan", "apply-validated-home-manager-plan"]
    )
    return result


def home_manager_validation() -> dict:
    return {
        "schemaVersion": 1,
        "requestId": "home-validation",
        "status": "ok",
        "result": {
            "validationReceipt": "H" * 43,
            "expiresInSeconds": 300,
            "targetId": "live",
            "planFingerprint": "a" * 64,
            "username": "alice",
            "integration": "nixos-module",
            "fixtureOnly": False,
            "liveWriteEnabled": True,
            "activationEnabled": False,
            "validation": {
                "status": "passed",
                "checks": [{"name": "Parse", "status": "passed"}],
                "warnings": [],
                "workingCopyRemoved": True,
            },
        },
        "error": None,
    }


def home_manager_apply_result() -> dict:
    return {
        "schemaVersion": 1,
        "requestId": "home-apply",
        "status": "ok",
        "result": {
            "state": "committed",
            "fixtureOnly": False,
            "writeEnabled": True,
            "liveWriteEnabled": True,
            "activationEnabled": False,
            "buildEnabled": False,
            "filesWritten": 4,
            "transaction": {
                "transactionId": "c" * 24,
                "state": "committed",
                "journalPath": "/var/lib/ncm/example",
                "changedFiles": ["configuration.nix"],
                "fixtureOnly": False,
                "activationEnabled": False,
            },
        },
        "error": None,
    }


def managed_capabilities() -> dict:
    result = capabilities()
    target = result["result"]["targets"][0]
    target.update(
        {
            "allowedRelativePaths": ["ncm/state.json", "ncm/packages.nix"],
            "dryActivatePreviewEnabled": False,
            "managedWriteEnabled": True,
            "managedRecoveryEnabled": True,
        }
    )
    result["result"]["operations"].extend(
        [
            "validate-managed-plan",
            "apply-validated-managed-plan",
            "recover-managed-transaction",
        ]
    )
    return result


def managed_validation() -> dict:
    return {
        "schemaVersion": 1,
        "requestId": "managed-validation",
        "status": "ok",
        "result": {
            "validationReceipt": "M" * 43,
            "expiresInSeconds": 300,
            "targetId": "live",
            "planFingerprint": "a" * 64,
            "fixtureOnly": False,
            "managedWriteEnabled": True,
            "activationEnabled": False,
            "validation": {
                "status": "passed",
                "checks": [{"name": "Evaluate", "status": "passed"}],
                "warnings": [],
                "workingCopyRemoved": True,
                "writeScope": ["ncm/state.json", "ncm/packages.nix"],
            },
        },
        "error": None,
    }


def managed_apply_result() -> dict:
    return {
        "schemaVersion": 1,
        "requestId": "managed-apply",
        "status": "ok",
        "result": {
            "state": "committed",
            "fixtureOnly": False,
            "writeEnabled": True,
            "managedWriteEnabled": True,
            "activationEnabled": False,
            "buildEnabled": False,
            "switchEnabled": False,
            "filesWritten": 2,
            "transaction": {
                "transactionId": "d" * 24,
                "state": "committed",
                "fixtureOnly": False,
                "activationEnabled": False,
                "changedFiles": ["ncm/state.json", "ncm/packages.nix"],
            },
        },
        "error": None,
    }


def validation(*, receipt: bool = False) -> dict:
    result = {
        "targetId": "live",
        "planFingerprint": "a" * 64,
        "readOnly": True,
        "applyEnabled": False,
        "activationEnabled": False,
        "validation": {
            "status": "passed",
            "checks": [
                {
                    "name": "Parse configuration.nix",
                    "status": "passed",
                    "exitCode": 0,
                    "durationMs": 4,
                }
            ],
            "warnings": [],
            "workingCopyRemoved": True,
            "fixtureOnly": False,
            "liveTarget": True,
            "readOnly": True,
            "applyEnabled": False,
            "activationEnabled": False,
        },
    }
    if receipt:
        result["validationReceipt"] = "A" * 32
    return {
        "schemaVersion": 1,
        "requestId": "helper-validation",
        "status": "ok",
        "result": result,
        "error": None,
    }


def activation_preview() -> dict:
    return {
        "schemaVersion": 1,
        "requestId": "helper-preview",
        "status": "ok",
        "result": {
            "status": "passed",
            "systemPath": "/nix/store/" + "a" * 32 + "-system",
            "planFingerprint": "a" * 64,
            "command": ["/nix/store/example/bin/switch-to-configuration", "dry-activate"],
            "stdout": "would restart example.service\n",
            "stderr": "",
            "sourceFilesUnchanged": True,
            "currentSystemUnchanged": True,
            "configurationWriteEnabled": False,
            "activationEnabled": False,
            "testEnabled": False,
            "switchEnabled": False,
            "reportIncomplete": True,
        },
        "error": None,
    }


def test_activation_result() -> dict:
    return {
        "schemaVersion": 1,
        "requestId": "helper-test",
        "status": "ok",
        "result": {
            "status": "active",
            "sessionId": "c" * 24,
            "systemPath": "/nix/store/" + "a" * 32 + "-system",
            "previousSystemPath": "/nix/store/" + "b" * 32 + "-previous",
            "planFingerprint": "a" * 64,
            "testEnabled": True,
            "switchEnabled": False,
            "configurationWriteEnabled": False,
            "autoRecoveryScheduled": True,
        },
        "error": None,
    }


def test_recovery_result() -> dict:
    return {
        "schemaVersion": 1,
        "requestId": "helper-recovery",
        "status": "ok",
        "result": {
            "status": "recovered",
            "sessionId": "c" * 24,
            "currentSystemRestored": True,
            "testEnabled": True,
            "switchEnabled": False,
            "configurationWriteEnabled": False,
        },
        "error": None,
    }


class HelperUiAdapterTests(unittest.TestCase):
    def test_status_fails_closed_when_unix_sockets_are_unavailable(self) -> None:
        def unsupported_sender(*_args, **_kwargs):
            raise AttributeError("module 'socket' has no attribute 'AF_UNIX'")

        adapter = HelperUiAdapter(
            socket_path=Path("/run/nix-control-manager/helper.sock"),
            target_id="live",
            config_root=Path("/etc/nixos"),
            sender=unsupported_sender,
        )

        status = adapter.status()

        self.assertFalse(status["available"])
        self.assertFalse(status["dryActivatePreviewEnabled"])
        self.assertIn("AF_UNIX", status["reason"])

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "etc-nixos"
        self.root.mkdir()
        (self.root / "configuration.nix").write_text(
            "{ ... }: {\n  imports = [\n  ];\n"
            "  home-manager.users.alice = ./alice.nix;\n}\n",
            encoding="utf-8",
        )
        self.socket = Path(self.temporary.name) / "helper.sock"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def adapter(self, sender) -> HelperUiAdapter:
        return HelperUiAdapter(
            socket_path=self.socket,
            target_id="live",
            config_root=self.root,
            sender=sender,
        )

    def test_status_accepts_only_a_hard_read_only_live_target(self) -> None:
        safe = self.adapter(SequenceSender(capabilities())).status()
        unsafe = self.adapter(SequenceSender(capabilities(safe=False))).status()

        self.assertTrue(safe["available"])
        self.assertTrue(safe["readOnly"])
        self.assertFalse(safe["applyEnabled"])
        self.assertFalse(unsafe["available"])
        self.assertIn("read-only", unsafe["reason"])
        self.assertTrue(safe["dryActivatePreviewEnabled"])

    def test_managed_validation_and_apply_keep_exact_two_file_scope(self) -> None:
        state = ManagedState.from_mapping(
            {"schemaVersion": 1, "packages": ["git"], "options": {}}
        )
        sender = SequenceSender(
            managed_capabilities(),
            managed_validation(),
            managed_capabilities(),
            managed_apply_result(),
        )
        adapter = self.adapter(sender)
        validated = adapter.validate_managed(state)
        expected = build_managed_validate_request(
            self.root, state, target_id="live", flake_target=None
        )
        self.assertEqual(sender.requests[1][1]["payload"], expected["payload"])
        self.assertTrue(validated["managedWriteEnabled"])
        applied = adapter.apply_managed(
            plan_fingerprint=validated["planFingerprint"],
            validation_receipt=validated["validationReceipt"],
        )
        self.assertEqual(applied["state"], "committed")
        self.assertTrue(applied["authorizedByPolkit"])
        self.assertFalse(applied["switchEnabled"])

    def test_unavailable_socket_is_reported_without_raising(self) -> None:
        status = self.adapter(SequenceSender(FileNotFoundError("missing socket"))).status()

        self.assertFalse(status["available"])
        self.assertEqual(status["reason"], "missing socket")

    def test_validation_builds_a_typed_plan_and_normalizes_safe_result(self) -> None:
        sender = SequenceSender(capabilities(), validation())
        result = self.adapter(sender).validate_adoption()

        request = sender.requests[1][1]
        self.assertEqual(request["operation"], "validate-plan")
        self.assertEqual(request["payload"]["targetId"], "live")
        self.assertGreater(len(request["payload"]["changes"]), 0)
        self.assertEqual(result["source"], "system-helper")
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["workingCopyRemoved"])
        self.assertFalse(result["validationReceiptIssued"])
        self.assertFalse(result["applyEnabled"])

    def test_validation_fails_closed_if_a_receipt_appears(self) -> None:
        adapter = self.adapter(SequenceSender(capabilities(), validation(receipt=True)))

        with self.assertRaisesRegex(HelperUiError, "unexpectedly issued"):
            adapter.validate_adoption()

    def test_validation_fails_closed_on_fingerprint_mismatch(self) -> None:
        response = validation()
        response["result"]["planFingerprint"] = "b" * 64
        adapter = self.adapter(SequenceSender(capabilities(), response))

        with self.assertRaisesRegex(HelperUiError, "read-only UI boundary"):
            adapter.validate_adoption()

    def test_backend_validation_failure_remains_a_renderable_result(self) -> None:
        failed = validation()
        failed["status"] = "error"
        failed["error"] = {"code": "validation-failed", "message": "Nix failed"}
        failed["result"] = failed["result"]["validation"]
        failed["result"]["status"] = "failed"
        adapter = self.adapter(SequenceSender(capabilities(), failed))

        result = adapter.validate_adoption()

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["transportStatus"], "error")
        self.assertEqual(result["error"]["code"], "validation-failed")

    def test_activation_preview_is_exact_and_remains_non_activating(self) -> None:
        sender = SequenceSender(capabilities(), activation_preview())
        adapter = self.adapter(sender)
        validation_request = build_validate_request(
            self.root, target_id="live", flake_target=None
        )
        system_path = "/nix/store/" + "b" * 32 + "-nixos-system-preview"
        result = adapter.preview_activation(
            system_path=system_path,
            plan_fingerprint=validation_request["payload"]["planFingerprint"],
        )

        request = sender.requests[1][1]
        self.assertEqual(request["operation"], "preview-activation")
        self.assertEqual(request["payload"]["systemPath"], system_path)
        self.assertTrue(result["dryActivateExecuted"])
        self.assertTrue(result["authorizedByPolkit"])
        self.assertFalse(result["activationEnabled"])
        self.assertFalse(result["testEnabled"])
        self.assertFalse(result["switchEnabled"])

    def test_bounded_test_activation_and_recovery_are_strictly_normalized(self) -> None:
        sender = SequenceSender(
            capabilities(test_enabled=True),
            test_activation_result(),
            capabilities(test_enabled=True),
            test_recovery_result(),
        )
        adapter = self.adapter(sender)
        system_path = "/nix/store/" + "d" * 32 + "-nixos-system-test"
        active = adapter.test_activation(
            system_path=system_path,
            plan_fingerprint="e" * 64,
            test_receipt="R" * 32,
        )
        self.assertEqual(active["status"], "active")
        self.assertTrue(active["autoRecoveryScheduled"])
        self.assertFalse(active["switchEnabled"])
        self.assertEqual(sender.requests[1][1]["operation"], "test-activation")

        recovered = adapter.recover_test_activation(session_id="c" * 24)
        self.assertEqual(recovered["status"], "recovered")
        self.assertTrue(recovered["currentSystemRestored"])
        self.assertEqual(
            sender.requests[3][1]["operation"], "recover-test-activation"
        )

    def test_live_home_manager_validation_and_apply_are_exact_and_non_activating(self) -> None:
        validation_request = build_home_manager_validate_request(
            self.root,
            target_id="live",
            username="alice",
            integration="nixos-module",
            packages=("firefox",),
            flake_target=None,
        )
        fingerprint = validation_request["payload"]["planFingerprint"]
        sender = SequenceSender(
            home_manager_capabilities(),
            home_manager_validation(),
            home_manager_capabilities(),
            home_manager_apply_result(),
        )
        adapter = self.adapter(sender)

        validated = adapter.validate_home_manager(
            username="alice",
            integration="nixos-module",
            packages=("firefox",),
            expected_plan_fingerprint=fingerprint,
        )
        self.assertEqual(validated["planFingerprint"], fingerprint)
        self.assertTrue(validated["liveWriteEnabled"])
        self.assertFalse(validated["activationEnabled"])
        self.assertEqual(
            sender.requests[1][1]["operation"], "validate-home-manager-plan"
        )

        applied = adapter.apply_home_manager(
            plan_fingerprint=fingerprint,
            validation_receipt=validated["validationReceipt"],
        )
        self.assertEqual(applied["state"], "committed")
        self.assertTrue(applied["authorizedByPolkit"])
        self.assertFalse(applied["homeManagerActivationEnabled"])
        self.assertFalse(applied["switchEnabled"])
        self.assertEqual(
            sender.requests[3][1]["operation"],
            "apply-validated-home-manager-plan",
        )

    def test_live_home_manager_fails_closed_on_displayed_plan_mismatch(self) -> None:
        adapter = self.adapter(SequenceSender(home_manager_capabilities()))
        with self.assertRaisesRegex(HelperUiError, "displayed Home Manager plan"):
            adapter.validate_home_manager(
                username="alice",
                integration="nixos-module",
                packages=("firefox",),
                expected_plan_fingerprint="f" * 64,
            )


if __name__ == "__main__":
    unittest.main()
