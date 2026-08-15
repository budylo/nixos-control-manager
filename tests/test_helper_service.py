import hashlib
from pathlib import Path
import tempfile
import unittest

from nix_control_manager.helper_service import (
    APPLY_ACTION_ID,
    HOME_MANAGER_APPLY_ACTION_ID,
    MANAGED_APPLY_ACTION_ID,
    PREVIEW_ACTIVATION_ACTION_ID,
    RECOVER_TEST_ACTIVATION_ACTION_ID,
    RECOVER_ACTION_ID,
    TEST_ACTIVATION_ACTION_ID,
    HelperDispatcher,
    HelperTarget,
    MockPolkitAuthorizer,
    RecordingMockBackend,
)


class HelperServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.mock_root = Path(self.temporary.name) / "never-written-target"
        self.authorizer = MockPolkitAuthorizer()
        self.backend = RecordingMockBackend()
        self.dispatcher = HelperDispatcher(
            targets=(
                HelperTarget(
                    target_id="system",
                    configuration_root=self.mock_root,
                    allowed_relative_paths=frozenset(
                        {
                            "configuration.nix",
                            "ncm/default.nix",
                            "ncm/managed.nix",
                            "ncm/packages.nix",
                            "ncm/state.json",
                        }
                    ),
                ),
            ),
            authorizer=self.authorizer,
            backend=self.backend,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def request(operation: str, payload: dict, request_id: str = "request-0001") -> dict:
        return {
            "schemaVersion": 1,
            "requestId": request_id,
            "operation": operation,
            "payload": payload,
        }

    @staticmethod
    def change(path: str = "ncm/state.json", candidate: str = "{}\n") -> dict:
        return {
            "relativePath": path,
            "action": "modify",
            "previousSha256": "1" * 64,
            "candidateSha256": hashlib.sha256(candidate.encode("utf-8")).hexdigest(),
            "candidate": candidate,
        }

    def validate(self, *, uid: int = 1000, fingerprint: str = "2" * 64) -> dict:
        response = self.dispatcher.handle(
            self.request(
                "validate-plan",
                {
                    "targetId": "system",
                    "planFingerprint": fingerprint,
                    "changes": [self.change()],
                },
            ),
            peer_uid=uid,
        )
        self.assertEqual(response["status"], "ok")
        return response

    def test_capabilities_are_read_only_and_need_no_authorization(self) -> None:
        response = self.dispatcher.handle(
            self.request("capabilities", {}), peer_uid=1000
        )

        self.assertEqual(response["status"], "ok")
        self.assertFalse(response["result"]["arbitraryCommandsAccepted"])
        self.assertFalse(response["result"]["activationEnabled"])
        self.assertEqual(self.authorizer.calls, [])
        self.assertFalse(self.mock_root.exists())

    def test_managed_target_uses_separate_receipt_and_polkit_boundary(self) -> None:
        managed = HelperTarget(
            target_id="managed",
            configuration_root=self.mock_root,
            allowed_relative_paths=frozenset(
                {"ncm/state.json", "ncm/packages.nix"}
            ),
            fixture_only=False,
            apply_enabled=False,
            managed_write_enabled=True,
            managed_journal_root=Path(self.temporary.name) / "managed-journal",
        )
        dispatcher = HelperDispatcher(
            targets=(managed,),
            authorizer=self.authorizer,
            backend=self.backend,
        )
        capabilities = dispatcher.handle(
            self.request("capabilities", {}), peer_uid=1000
        )["result"]["targets"][0]
        self.assertTrue(capabilities["readOnly"])
        self.assertFalse(capabilities["applyEnabled"])
        self.assertTrue(capabilities["managedWriteEnabled"])
        self.assertTrue(capabilities["managedRecoveryEnabled"])
        self.assertFalse(capabilities["dryActivatePreviewEnabled"])

        validated = dispatcher.handle(
            self.request(
                "validate-managed-plan",
                {
                    "targetId": "managed",
                    "planFingerprint": "2" * 64,
                    "changes": [self.change()],
                },
            ),
            peer_uid=1000,
        )
        self.assertEqual(validated["status"], "ok")
        receipt = validated["result"]["validationReceipt"]
        request = self.request(
            "apply-validated-managed-plan",
            {
                "targetId": "managed",
                "planFingerprint": "2" * 64,
                "validationReceipt": receipt,
            },
            request_id="managed-apply1",
        )
        self.assertEqual(dispatcher.handle(request, peer_uid=1000)["status"], "denied")
        self.assertEqual(self.backend.managed_apply_calls, [])
        self.authorizer.allowed.add((1000, MANAGED_APPLY_ACTION_ID))
        applied = dispatcher.handle(request, peer_uid=1000)
        self.assertEqual(applied["status"], "ok")
        self.assertEqual(applied["result"]["state"], "committed")

        escaped = dispatcher.handle(
            self.request(
                "validate-managed-plan",
                {
                    "targetId": "managed",
                    "planFingerprint": "3" * 64,
                    "changes": [self.change("configuration.nix")],
                },
                request_id="managed-path1",
            ),
            peer_uid=1000,
        )
        self.assertEqual(escaped["error"]["code"], "path-not-allowed")

    def test_rejects_traversal_unknown_fields_and_wrong_digest(self) -> None:
        traversal = self.change("../configuration.nix")
        response = self.dispatcher.handle(
            self.request(
                "validate-plan",
                {"targetId": "system", "planFingerprint": "2" * 64, "changes": [traversal]},
            ),
            peer_uid=1000,
        )
        self.assertEqual(response["error"]["code"], "path-not-allowed")

        wrong_digest = self.change()
        wrong_digest["candidateSha256"] = "3" * 64
        response = self.dispatcher.handle(
            self.request(
                "validate-plan",
                {"targetId": "system", "planFingerprint": "2" * 64, "changes": [wrong_digest]},
            ),
            peer_uid=1000,
        )
        self.assertEqual(response["error"]["code"], "invalid-digest")

        request = self.request("capabilities", {})
        request["command"] = "rm -rf /"
        response = self.dispatcher.handle(request, peer_uid=1000)
        self.assertEqual(response["error"]["code"], "invalid-request")
        self.assertFalse(self.mock_root.exists())

    def test_exact_target_allow_list_rejects_an_otherwise_safe_path(self) -> None:
        response = self.dispatcher.handle(
            self.request(
                "validate-plan",
                {
                    "targetId": "system",
                    "planFingerprint": "2" * 64,
                    "changes": [self.change("users/alice.nix")],
                },
            ),
            peer_uid=1000,
        )

        self.assertEqual(response["error"]["code"], "path-not-allowed")
        self.assertEqual(self.backend.validate_calls, [])

    def test_apply_requires_polkit_then_consumes_receipt_once(self) -> None:
        validated = self.validate()
        receipt = validated["result"]["validationReceipt"]
        apply_request = self.request(
            "apply-validated-plan",
            {
                "targetId": "system",
                "planFingerprint": "2" * 64,
                "validationReceipt": receipt,
            },
            request_id="request-apply1",
        )

        denied = self.dispatcher.handle(apply_request, peer_uid=1000)
        self.assertEqual(denied["status"], "denied")
        self.assertEqual(self.backend.apply_calls, [])

        self.authorizer.allowed.add((1000, APPLY_ACTION_ID))
        accepted = self.dispatcher.handle(apply_request, peer_uid=1000)
        self.assertEqual(accepted["status"], "ok")
        self.assertEqual(accepted["result"]["state"], "mock-applied")
        self.assertEqual(accepted["result"]["filesWritten"], 0)

        replay = self.dispatcher.handle(apply_request, peer_uid=1000)
        self.assertEqual(replay["error"]["code"], "invalid-receipt")
        self.assertEqual(len(self.backend.apply_calls), 1)
        self.assertFalse(self.mock_root.exists())

    def test_receipt_is_bound_to_peer_uid_target_and_fingerprint(self) -> None:
        validated = self.validate(uid=1000)
        receipt = validated["result"]["validationReceipt"]
        self.authorizer.allowed.add((1001, APPLY_ACTION_ID))
        response = self.dispatcher.handle(
            self.request(
                "apply-validated-plan",
                {
                    "targetId": "system",
                    "planFingerprint": "2" * 64,
                    "validationReceipt": receipt,
                },
            ),
            peer_uid=1001,
        )
        self.assertEqual(response["error"]["code"], "invalid-receipt")
        self.assertEqual(self.authorizer.calls, [])

        response = self.dispatcher.handle(
            self.request(
                "apply-validated-plan",
                {
                    "targetId": "system",
                    "planFingerprint": "3" * 64,
                    "validationReceipt": receipt,
                },
            ),
            peer_uid=1000,
        )
        self.assertEqual(response["error"]["code"], "invalid-receipt")

    def test_system_receipt_cannot_authorize_home_manager_apply(self) -> None:
        validated = self.validate()
        self.authorizer.allowed.add((1000, HOME_MANAGER_APPLY_ACTION_ID))

        response = self.dispatcher.handle(
            self.request(
                "apply-validated-home-manager-plan",
                {
                    "targetId": "system",
                    "planFingerprint": "2" * 64,
                    "validationReceipt": validated["result"]["validationReceipt"],
                },
                "cross-home-apply",
            ),
            peer_uid=1000,
        )

        self.assertEqual(response["error"]["code"], "invalid-receipt")
        self.assertEqual(self.backend.home_manager_apply_calls, [])
        self.assertEqual(self.authorizer.calls, [])

    def test_failed_helper_validation_never_issues_a_receipt(self) -> None:
        self.backend.validation_status = "failed"
        response = self.dispatcher.handle(
            self.request(
                "validate-plan",
                {
                    "targetId": "system",
                    "planFingerprint": "2" * 64,
                    "changes": [self.change()],
                },
            ),
            peer_uid=1000,
        )

        self.assertEqual(response["error"]["code"], "validation-failed")
        self.assertNotIn("validationReceipt", response.get("result") or {})

    def test_recovery_has_a_separate_polkit_action(self) -> None:
        request = self.request(
            "recover-transaction",
            {"targetId": "system", "transactionId": "a" * 24},
        )
        denied = self.dispatcher.handle(request, peer_uid=1000)
        self.assertEqual(denied["status"], "denied")
        self.assertEqual(self.backend.recover_calls, [])

        self.authorizer.allowed.add((1000, RECOVER_ACTION_ID))
        accepted = self.dispatcher.handle(request, peer_uid=1000)
        self.assertEqual(accepted["status"], "ok")
        self.assertEqual(accepted["result"]["state"], "mock-recovered")
        self.assertEqual(self.authorizer.calls[-1][0], RECOVER_ACTION_ID)
        self.assertFalse(self.mock_root.exists())

    def test_live_target_rejects_all_home_manager_write_operations_before_backend(self) -> None:
        backend = RecordingMockBackend()
        authorizer = MockPolkitAuthorizer()
        dispatcher = HelperDispatcher(
            targets=(
                HelperTarget(
                    target_id="live",
                    configuration_root=self.mock_root,
                    allowed_relative_paths=frozenset({"ncm/user-state.json"}),
                    fixture_only=False,
                    apply_enabled=False,
                ),
            ),
            authorizer=authorizer,
            backend=backend,
        )
        candidate = self.change("ncm/user-state.json")
        validate = dispatcher.handle(
            self.request(
                "validate-home-manager-plan",
                {
                    "targetId": "live",
                    "planFingerprint": "2" * 64,
                    "username": "alice",
                    "integration": "standalone",
                    "packages": ["firefox"],
                    "changes": [candidate],
                },
                "live-home-valid",
            ),
            peer_uid=1000,
        )
        apply = dispatcher.handle(
            self.request(
                "apply-validated-home-manager-plan",
                {
                    "targetId": "live",
                    "planFingerprint": "2" * 64,
                    "validationReceipt": "R" * 32,
                },
                "live-home-apply",
            ),
            peer_uid=1000,
        )
        recover = dispatcher.handle(
            self.request(
                "recover-home-manager-transaction",
                {"targetId": "live", "transactionId": "a" * 24},
                "live-home-recov",
            ),
            peer_uid=1000,
        )

        self.assertEqual(validate["error"]["code"], "operation-disabled")
        self.assertEqual(apply["error"]["code"], "operation-disabled")
        self.assertEqual(recover["error"]["code"], "operation-disabled")
        self.assertEqual(backend.home_manager_validate_calls, [])
        self.assertEqual(backend.home_manager_apply_calls, [])
        self.assertEqual(backend.home_manager_recover_calls, [])
        self.assertEqual(authorizer.calls, [])
        self.assertFalse(self.mock_root.exists())

    def test_home_manager_payload_rejects_untyped_packages_and_extra_fields(self) -> None:
        payload = {
            "targetId": "system",
            "planFingerprint": "2" * 64,
            "username": "alice",
            "integration": "standalone",
            "packages": ["../arbitrary"],
            "changes": [self.change()],
        }
        invalid_package = self.dispatcher.handle(
            self.request(
                "validate-home-manager-plan", payload, "typed-home-pack1"
            ),
            peer_uid=1000,
        )
        self.assertEqual(invalid_package["error"]["code"], "invalid-package")

        payload["packages"] = ["firefox"]
        payload["command"] = ["sh", "-c", "anything"]
        extra = self.dispatcher.handle(
            self.request(
                "validate-home-manager-plan", payload, "typed-home-extra"
            ),
            peer_uid=1000,
        )
        self.assertEqual(extra["error"]["code"], "invalid-request")
        self.assertEqual(self.backend.home_manager_validate_calls, [])

    def test_dry_activation_preview_is_live_only_polkit_scoped_and_typed(self) -> None:
        live_backend = RecordingMockBackend()
        live_authorizer = MockPolkitAuthorizer()
        live_dispatcher = HelperDispatcher(
            targets=(
                HelperTarget(
                    target_id="live",
                    configuration_root=self.mock_root,
                    allowed_relative_paths=frozenset({"ncm/state.json"}),
                    fixture_only=False,
                    apply_enabled=False,
                ),
            ),
            authorizer=live_authorizer,
            backend=live_backend,
        )
        system_path = "/nix/store/" + "a" * 32 + "-nixos-system-preview"
        payload = {
            "targetId": "live",
            "planFingerprint": "2" * 64,
            "changes": [self.change()],
            "systemPath": system_path,
        }
        request = self.request("preview-activation", payload, "dry-preview-01")

        denied = live_dispatcher.handle(request, peer_uid=1000)
        self.assertEqual(denied["status"], "denied")
        self.assertEqual(live_backend.preview_activation_calls, [])

        live_authorizer.allowed.add((1000, PREVIEW_ACTIVATION_ACTION_ID))
        accepted = live_dispatcher.handle(request, peer_uid=1000)
        self.assertEqual(accepted["status"], "ok")
        self.assertFalse(accepted["result"]["activationEnabled"])
        self.assertEqual(live_backend.preview_activation_calls[0][2], system_path)

        payload["systemPath"] = "/tmp/not-a-store-path"
        invalid = live_dispatcher.handle(
            self.request("preview-activation", payload, "dry-preview-02"),
            peer_uid=1000,
        )
        self.assertEqual(invalid["error"]["code"], "invalid-store-path")

        fixture_payload = dict(payload)
        fixture_payload["targetId"] = "system"
        fixture_payload["systemPath"] = system_path
        fixture = self.dispatcher.handle(
            self.request("preview-activation", fixture_payload, "dry-preview-03"),
            peer_uid=1000,
        )
        self.assertEqual(fixture["error"]["code"], "operation-disabled")

    def test_test_activation_requires_dry_receipt_separate_polkit_and_is_recoverable(self) -> None:
        backend = RecordingMockBackend()
        authorizer = MockPolkitAuthorizer()
        target = HelperTarget(
            target_id="live-test",
            configuration_root=self.mock_root,
            allowed_relative_paths=frozenset({"ncm/state.json"}),
            fixture_only=False,
            apply_enabled=False,
            test_activation_enabled=True,
            test_journal_root=Path(self.temporary.name) / "test-journal",
            test_timeout_seconds=60,
        )
        dispatcher = HelperDispatcher(
            targets=(target,), authorizer=authorizer, backend=backend
        )
        system_path = "/nix/store/" + "b" * 32 + "-nixos-system-test"
        preview_payload = {
            "targetId": "live-test",
            "planFingerprint": "2" * 64,
            "changes": [self.change()],
            "systemPath": system_path,
        }
        authorizer.allowed.add((1000, PREVIEW_ACTIVATION_ACTION_ID))
        preview = dispatcher.handle(
            self.request("preview-activation", preview_payload, "test-preview-01"),
            peer_uid=1000,
        )
        self.assertEqual(preview["status"], "ok")
        self.assertTrue(preview["result"]["testActivationPrepared"])
        receipt = preview["result"]["testReceipt"]
        request = self.request(
            "test-activation",
            {
                "targetId": "live-test",
                "planFingerprint": "2" * 64,
                "systemPath": system_path,
                "testReceipt": receipt,
            },
            "test-activate-01",
        )

        wrong_user = dispatcher.handle(request, peer_uid=1001)
        self.assertEqual(wrong_user["error"]["code"], "invalid-receipt")
        self.assertEqual(len(authorizer.calls), 1)

        denied = dispatcher.handle(request, peer_uid=1000)
        self.assertEqual(denied["status"], "denied")
        self.assertEqual(backend.test_activation_calls, [])

        authorizer.allowed.add((1000, TEST_ACTIVATION_ACTION_ID))
        active = dispatcher.handle(request, peer_uid=1000)
        self.assertEqual(active["status"], "ok")
        self.assertTrue(active["result"]["autoRecoveryScheduled"])
        session_id = active["result"]["sessionId"]
        replay = dispatcher.handle(request, peer_uid=1000)
        self.assertEqual(replay["error"]["code"], "invalid-receipt")

        recovery_request = self.request(
            "recover-test-activation",
            {"targetId": "live-test", "sessionId": session_id},
            "test-recover-01",
        )
        denied_recovery = dispatcher.handle(recovery_request, peer_uid=1000)
        self.assertEqual(denied_recovery["status"], "denied")
        authorizer.allowed.add((1000, RECOVER_TEST_ACTIVATION_ACTION_ID))
        recovered = dispatcher.handle(recovery_request, peer_uid=1000)
        self.assertEqual(recovered["result"]["status"], "recovered")
        self.assertTrue(recovered["result"]["currentSystemRestored"])
        self.assertEqual(backend.recover_test_activation_calls[-1][1], session_id)

    def test_read_only_live_target_rejects_test_before_polkit(self) -> None:
        backend = RecordingMockBackend()
        authorizer = MockPolkitAuthorizer()
        dispatcher = HelperDispatcher(
            targets=(
                HelperTarget(
                    target_id="live",
                    configuration_root=self.mock_root,
                    allowed_relative_paths=frozenset({"ncm/state.json"}),
                    fixture_only=False,
                    apply_enabled=False,
                ),
            ),
            authorizer=authorizer,
            backend=backend,
        )
        response = dispatcher.handle(
            self.request(
                "test-activation",
                {
                    "targetId": "live",
                    "planFingerprint": "2" * 64,
                    "systemPath": "/nix/store/" + "b" * 32 + "-system",
                    "testReceipt": "A" * 32,
                },
                "readonly-test-01",
            ),
            peer_uid=1000,
        )
        self.assertEqual(response["error"]["code"], "operation-disabled")
        self.assertEqual(authorizer.calls, [])


if __name__ == "__main__":
    unittest.main()
