from pathlib import Path
import tempfile
import unittest

from nix_control_manager.adoption import plan_adoption
from nix_control_manager.candidate import plan_identity
from nix_control_manager.helper_client import (
    build_activation_preview_request,
    build_test_activation_request,
    build_test_recovery_request,
    build_validate_request,
)


class HelperClientTests(unittest.TestCase):
    def test_builds_the_exact_typed_plan_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            configuration = root / "configuration.nix"
            original = "{ ... }:\n\n{\n  imports = [\n  ];\n}\n"
            configuration.write_text(original, encoding="utf-8")

            request = build_validate_request(
                root, target_id="fixture", flake_target=None
            )

            self.assertEqual(request["operation"], "validate-plan")
            self.assertEqual(request["payload"]["targetId"], "fixture")
            self.assertEqual(len(request["payload"]["planFingerprint"]), 64)
            self.assertGreater(len(request["payload"]["changes"]), 0)
            self.assertEqual(configuration.read_text(encoding="utf-8"), original)

    def test_activation_preview_is_bound_to_exact_plan_and_store_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "configuration.nix").write_text(
                "{ ... }:\n\n{\n  imports = [\n  ];\n}\n", encoding="utf-8"
            )
            validation = build_validate_request(
                root, target_id="live", flake_target=None
            )
            system_path = "/nix/store/" + "a" * 32 + "-nixos-system-preview"
            request = build_activation_preview_request(
                root,
                target_id="live",
                flake_target=None,
                system_path=system_path,
                expected_fingerprint=validation["payload"]["planFingerprint"],
            )

            self.assertEqual(request["operation"], "preview-activation")
            self.assertEqual(request["payload"]["systemPath"], system_path)
            with self.assertRaisesRegex(ValueError, "changed"):
                build_activation_preview_request(
                    root,
                    target_id="live",
                    flake_target=None,
                    system_path=system_path,
                    expected_fingerprint="f" * 64,
                )

    def test_refuses_a_root_without_safe_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "No safe adoption changes"):
                build_validate_request(
                    Path(temporary), target_id="fixture", flake_target=None
                )

    def test_test_activation_requests_accept_no_command_or_rebuild_mode(self) -> None:
        system_path = "/nix/store/" + "a" * 32 + "-nixos-system-test"
        request = build_test_activation_request(
            target_id="live-test",
            system_path=system_path,
            plan_fingerprint="b" * 64,
            test_receipt="R" * 32,
        )
        self.assertEqual(request["operation"], "test-activation")
        self.assertEqual(
            set(request["payload"]),
            {"targetId", "systemPath", "planFingerprint", "testReceipt"},
        )
        recovery = build_test_recovery_request(
            target_id="live-test", session_id="c" * 24
        )
        self.assertEqual(recovery["operation"], "recover-test-activation")
        self.assertEqual(set(recovery["payload"]), {"targetId", "sessionId"})

    def test_flake_fingerprint_uses_hostname_when_target_is_implicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "flake.nix").write_text(
                "{ outputs = _: { }; }\n", encoding="utf-8"
            )
            (root / "configuration.nix").write_text(
                "{ ... }: {\n  imports = [\n  ];\n}\n", encoding="utf-8"
            )
            plan = plan_adoption(root)

            request = build_validate_request(
                root, target_id="live", flake_target=None
            )

            expected, _ = plan_identity(plan, plan.inspection.hostname)
            self.assertEqual(request["payload"]["planFingerprint"], expected)


if __name__ == "__main__":
    unittest.main()
