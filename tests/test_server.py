import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from nix_control_manager.server import NcmServer, RequestHandler
from nix_control_manager.candidate_build import CandidateBuildManager, HomeManagerBuildManager
from nix_control_manager.home_manager_adoption import (
    home_manager_plan_identity,
    plan_home_manager_adoption,
)
from nix_control_manager.home_manager_inspector import (
    DetectedHomeUser,
    HomeManagerInspection,
    UserStateInspection,
)
from nix_control_manager.managed_plan import managed_plan_identity, plan_managed_state
from nix_control_manager.model import ManagedState
from nix_control_manager.package_compatibility import (
    PackageAssessment,
    PackageCompatibilityInspection,
    TargetContext,
)
from nix_control_manager.settings_inspector import (
    EffectiveDefinition,
    EffectiveSetting,
    EffectiveSettingsInspection,
)
from nix_control_manager.user_model import UserManagedState


class FakeHelperAdapter:
    def status(self):
        return {
            "available": True,
            "targetId": "live",
            "readOnly": True,
            "applyEnabled": False,
            "recoveryEnabled": False,
            "activationEnabled": False,
            "dryActivatePreviewEnabled": True,
            "testActivationEnabled": True,
            "homeManagerApplyEnabled": True,
            "homeManagerLiveWriteEnabled": True,
            "managedWriteEnabled": True,
            "managedRecoveryEnabled": True,
            "permanentSwitchEnabled": True,
            "rollbackGenerationEnabled": True,
        }

    def validate_adoption(self):
        return {
            "source": "system-helper",
            "status": "passed",
            "checks": [],
            "warnings": [],
            "readOnly": True,
            "applyEnabled": False,
            "recoveryEnabled": False,
            "activationEnabled": False,
            "validationReceiptIssued": False,
        }

    def preview_activation(self, *, system_path, plan_fingerprint):
        return {
            "source": "system-helper",
            "status": "passed",
            "systemPath": system_path,
            "planFingerprint": plan_fingerprint,
            "sourceFilesUnchanged": True,
            "currentSystemUnchanged": True,
            "configurationWriteEnabled": False,
            "activationEnabled": False,
            "testEnabled": False,
            "switchEnabled": False,
            "dryActivateExecuted": True,
            "testActivationPrepared": True,
            "testReceipt": "R" * 32,
        }

    def test_activation(self, *, system_path, plan_fingerprint, test_receipt):
        if test_receipt != "R" * 32:
            raise ValueError("bad test receipt")
        return {
            "source": "system-helper",
            "status": "active",
            "sessionId": "c" * 24,
            "systemPath": system_path,
            "previousSystemPath": "/nix/store/" + "a" * 32 + "-previous",
            "planFingerprint": plan_fingerprint,
            "testEnabled": True,
            "switchEnabled": False,
            "configurationWriteEnabled": False,
            "autoRecoveryScheduled": True,
        }

    def recover_test_activation(self, *, session_id):
        return {
            "source": "system-helper",
            "status": "recovered",
            "sessionId": session_id,
            "currentSystemRestored": True,
            "testEnabled": True,
            "switchEnabled": False,
            "configurationWriteEnabled": False,
        }

    def commit_tested_system(self, *, system_path, plan_fingerprint, session_id):
        return {
            "source": "system-helper",
            "status": "committing",
            "sessionId": session_id,
            "systemPath": system_path,
            "planFingerprint": plan_fingerprint,
            "switchEnabled": True,
            "rollbackEnabled": True,
            "arbitraryCommandsAccepted": False,
        }

    def activation_session_status(self, *, session_id):
        return {
            "source": "system-helper",
            "status": "committed",
            "sessionId": session_id,
            "switchEnabled": True,
            "rollbackEnabled": True,
            "arbitraryCommandsAccepted": False,
        }

    def rollback_committed_system(self, *, session_id):
        return {
            "source": "system-helper",
            "status": "rolling-back",
            "sessionId": session_id,
            "switchEnabled": True,
            "rollbackEnabled": True,
            "arbitraryCommandsAccepted": False,
        }

    def validate_home_manager(
        self,
        *,
        username,
        integration,
        packages,
        expected_plan_fingerprint,
    ):
        return {
            "source": "system-helper",
            "status": "passed",
            "targetId": "live",
            "username": username,
            "integration": integration,
            "planFingerprint": expected_plan_fingerprint,
            "validationReceipt": "H" * 43,
            "expiresInSeconds": 300,
            "checks": [],
            "warnings": [],
            "workingCopyRemoved": True,
            "fixtureOnly": False,
            "liveWriteEnabled": True,
            "activationEnabled": False,
            "homeManagerActivationEnabled": False,
        }

    def apply_home_manager(self, *, plan_fingerprint, validation_receipt):
        if validation_receipt != "H" * 43:
            raise ValueError("bad Home Manager receipt")
        return {
            "source": "system-helper",
            "state": "committed",
            "fixtureOnly": False,
            "writeEnabled": True,
            "liveWriteEnabled": True,
            "activationEnabled": False,
            "homeManagerActivationEnabled": False,
            "buildEnabled": False,
            "switchEnabled": False,
            "authorizedByPolkit": True,
            "filesWritten": 4,
            "transaction": {
                "transactionId": "c" * 24,
                "state": "committed",
                "fixtureOnly": False,
                "activationEnabled": False,
            },
        }

    def validate_managed(self, state):
        return {
            "source": "system-helper",
            "status": "passed",
            "targetId": "live",
            "planFingerprint": self.managed_fingerprint,
            "validationReceipt": "M" * 43,
            "expiresInSeconds": 300,
            "checks": [],
            "warnings": [],
            "workingCopyRemoved": True,
            "fixtureOnly": False,
            "managedWriteEnabled": True,
            "writeScope": ["ncm/state.json", "ncm/packages.nix"],
            "activationEnabled": False,
        }

    def apply_managed(self, *, plan_fingerprint, validation_receipt):
        if validation_receipt != "M" * 43:
            raise ValueError("bad managed receipt")
        return {
            "source": "system-helper",
            "state": "committed",
            "fixtureOnly": False,
            "writeEnabled": True,
            "managedWriteEnabled": True,
            "activationEnabled": False,
            "buildEnabled": False,
            "switchEnabled": False,
            "authorizedByPolkit": True,
            "filesWritten": 2,
            "transaction": {
                "transactionId": "d" * 24,
                "state": "committed",
                "fixtureOnly": False,
                "activationEnabled": False,
                "changedFiles": ["ncm/state.json", "ncm/packages.nix"],
            },
        }


class FakeHomeManagerValidation:
    def to_mapping(self):
        return {
            "status": "passed",
            "checks": [{"name": "Parse candidate", "status": "passed"}],
            "warnings": [],
            "workingCopyRemoved": True,
            "readOnly": True,
            "writeEnabled": False,
            "activationEnabled": False,
            "buildEnabled": False,
            "flakeInputMutationEnabled": False,
        }


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        directory = Path(self.temporary.name)
        self.server = NcmServer(
            ("127.0.0.1", 0),
            RequestHandler,
            state_path=directory / "state.json",
            output_path=directory / "managed.nix",
            config_root=directory / "etc-nixos",
            helper_adapter=FakeHelperAdapter(),
            settings_inspector=lambda *args, **kwargs: EffectiveSettingsInspection(
                status="passed",
                configuration_mode="channels",
                flake_target=None,
                settings=(
                    EffectiveSetting(
                        path="time.timeZone",
                        available=True,
                        value="Europe/Kyiv",
                        active_priority=100,
                        priority_kind="normal",
                        assessment="single-definition",
                        definitions=(
                            EffectiveDefinition(
                                file="/etc/nixos/configuration.nix",
                                value_available=True,
                                value="Europe/Kyiv",
                            ),
                        ),
                        ownership="inherited",
                    ),
                ),
                duration_ms=42,
            ),
            compatibility_inspector=lambda *args, **kwargs: PackageCompatibilityInspection(
                status="passed",
                configuration_mode="channels",
                flake_target=None,
                system="x86_64-linux",
                packages=(
                    PackageAssessment(
                        attribute="firefox",
                        status="compatible",
                        reason="available",
                        license_name="MPL-2.0",
                    ),
                    PackageAssessment(
                        attribute="vscode",
                        status="incompatible",
                        reason="evaluation-rejected",
                        unfree=True,
                        license_name="unfree",
                    ),
                ),
                context=TargetContext(
                    desktop_environments=("plasma",),
                    configuration_flags=("pipewire",),
                    form_factor="laptop",
                    gpu_vendors=("amd",),
                    kvm_available=True,
                    runtime_hardware_inspected=True,
                ),
                duration_ms=37,
            ),
            home_manager_inspector=lambda *args, **kwargs: HomeManagerInspection(
                status="detected",
                integrations=("nixos-module",),
                users=(
                    DetectedHomeUser(
                        name="alice",
                        integration="nixos-module",
                        source="flake.nix",
                    ),
                ),
                sources=("flake.nix",),
                config_root=directory / "etc-nixos",
                standalone_root=directory / "home-manager",
                user_state=UserStateInspection(
                    "current",
                    directory / "user-state.json",
                    UserManagedState.from_mapping(
                        {
                            "users": {
                                "alice": {
                                    "integration": "nixos-module",
                                    "packages": ["git"],
                                    "options": {"programs.git.enable": True},
                                }
                            }
                        }
                    ),
                ),
            ),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def request_json(self, path: str, *, method: str = "GET", body=None, token=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if token is not None:
            headers["X-NCM-Token"] = token
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        with urlopen(request, timeout=2) as response:
            return json.loads(response.read())

    def test_catalog_and_empty_state_are_available(self) -> None:
        catalog = self.request_json("/api/catalog")
        guidance = self.request_json("/api/catalog-guidance")
        compatibility = self.request_json("/api/catalog-compatibility")
        presets = self.request_json("/api/presets")
        settings_catalog = self.request_json("/api/settings-catalog")
        state = self.request_json("/api/state")
        system = self.request_json("/api/system")
        adoption = self.request_json("/api/adoption")
        helper = self.request_json("/api/helper")
        effective = self.request_json("/api/effective-settings")
        home_manager = self.request_json("/api/home-manager")
        self.assertGreaterEqual(len(catalog), 130)
        self.assertEqual(guidance["schemaVersion"], 1)
        self.assertGreaterEqual(len(guidance["alternativeGroups"]), 15)
        self.assertEqual(compatibility["status"], "passed")
        self.assertTrue(compatibility["readOnly"])
        self.assertEqual(compatibility["system"], "x86_64-linux")
        self.assertEqual(compatibility["summary"]["compatible"], 1)
        self.assertEqual(compatibility["summary"]["incompatible"], 1)
        self.assertEqual(compatibility["packages"][1]["reason"], "evaluation-rejected")
        self.assertEqual(compatibility["context"]["desktopEnvironments"], ["plasma"])
        self.assertEqual(compatibility["context"]["formFactor"], "laptop")
        self.assertGreaterEqual(len(presets), 8)
        self.assertIn("gaming-ready", {item["id"] for item in presets})
        self.assertGreaterEqual(len(settings_catalog), 40)
        self.assertIn("boolean", {item["valueType"] for item in settings_catalog})
        self.assertIn("enum", {item["valueType"] for item in settings_catalog})
        self.assertIn(
            "zramSwap.memoryPercent", {item["path"] for item in settings_catalog}
        )
        services = [item for item in settings_catalog if "service" in item]
        self.assertEqual(len(services), 23)
        self.assertIn(
            "services.openssh.enable", {item["path"] for item in services}
        )
        self.assertEqual(state["packages"], [])
        self.assertEqual(system["configuration"]["mode"], "missing")
        self.assertEqual(adoption["status"], "blocked")
        self.assertFalse(adoption["safeToApply"])
        self.assertTrue(helper["available"])
        self.assertFalse(helper["applyEnabled"])
        self.assertEqual(effective["status"], "passed")
        self.assertTrue(effective["readOnly"])
        self.assertEqual(effective["settings"][0]["value"], "Europe/Kyiv")
        self.assertEqual(effective["settings"][0]["activePriority"], 100)
        self.assertEqual(effective["settings"][0]["assessment"], "single-definition")
        self.assertEqual(home_manager["status"], "detected")
        self.assertEqual(home_manager["users"][0]["name"], "alice")
        self.assertFalse(home_manager["writeEnabled"])
        self.assertFalse(home_manager["activationEnabled"])

        with urlopen(self.base_url + "/", timeout=2) as response:
            html = response.read().decode("utf-8")
            self.assertIn("Nix Control Manager", html)
            self.assertIn('id="homeApplyConfirmation"', html)
            self.assertIn('id="commitHomeApplyButton"', html)
            self.assertIn('id="servicesPage"', html)
            self.assertIn('id="servicesNav"', html)
            self.assertIn("Content-Security-Policy", response.headers)

    def test_managed_save_hides_receipt_and_requires_exact_confirmation(self) -> None:
        root = self.server.config_root
        (root / "ncm").mkdir(parents=True)
        (root / "configuration.nix").write_text(
            "{ ... }: { imports = [ ./ncm ]; }\n", encoding="utf-8"
        )
        state = ManagedState.from_mapping(
            {"schemaVersion": 1, "packages": ["git"], "options": {}}
        )
        plan = plan_managed_state(root, state)
        self.server.helper_adapter.managed_fingerprint = managed_plan_identity(plan)[0]
        payload = state.to_mapping()
        prepared = self.request_json(
            "/api/helper/managed/validate",
            method="POST",
            body=payload,
            token=self.server.token,
        )
        self.assertTrue(prepared["confirmationRequired"])
        self.assertTrue(prepared["managedWriteEnabled"])
        self.assertNotIn("validationReceipt", prepared)
        self.assertIn("ncm/state.json", prepared["combinedDiff"])
        self.assertIn("ncm/packages.nix", prepared["combinedDiff"])

        with self.assertRaises(HTTPError) as rejected:
            self.request_json(
                "/api/helper/managed/apply",
                method="POST",
                body={
                    "intentId": prepared["intentId"],
                    "planFingerprint": prepared["planFingerprint"],
                    "confirmed": False,
                },
                token=self.server.token,
            )
        self.assertEqual(rejected.exception.code, 400)

        prepared = self.request_json(
            "/api/helper/managed/validate",
            method="POST",
            body=payload,
            token=self.server.token,
        )
        applied = self.request_json(
            "/api/helper/managed/apply",
            method="POST",
            body={
                "intentId": prepared["intentId"],
                "planFingerprint": prepared["planFingerprint"],
                "confirmed": True,
            },
            token=self.server.token,
        )
        self.assertEqual(applied["state"], "committed")
        self.assertTrue(applied["authorizedByPolkit"])
        self.assertFalse(applied["switchEnabled"])

    def test_legacy_state_is_normalized_in_memory_without_writing(self) -> None:
        legacy = (
            '{\n'
            '  "schemaVersion": 1,\n'
            '  "nixosRelease": "26.05",\n'
            '  "generatedAt": "2026-08-10T22:12:41Z",\n'
            '  "packages": {"firefox": true, "vlc": false},\n'
            '  "options": {}\n'
            '}\n'
        )
        self.server.state_path.write_text(legacy, encoding="utf-8")

        state = self.request_json("/api/state")
        preview = self.request_json("/api/preview")

        self.assertEqual(state["packages"], ["firefox"])
        self.assertIn("pkgs.firefox", preview["generated"])
        self.assertEqual(self.server.state_path.read_text(encoding="utf-8"), legacy)

    def test_mutation_requires_token(self) -> None:
        with self.assertRaises(HTTPError) as context:
            self.request_json(
                "/api/save", method="POST", body={"schemaVersion": 1, "packages": []}
            )
        self.assertEqual(context.exception.code, 403)
        context.exception.close()

    def test_home_manager_preview_is_detected_user_only_and_never_writes(self) -> None:
        user_state_path = self.server.user_state_path
        output_path = self.server.config_root / "ncm" / "managed-home-alice.nix"
        result = self.request_json(
            "/api/home-manager/preview",
            method="POST",
            token=self.server.token,
            body={
                "username": "alice",
                "integration": "nixos-module",
                "packages": ["vlc", "firefox"],
            },
        )
        self.assertEqual(result["username"], "alice")
        self.assertIn("home.packages", result["generated"])
        self.assertIn("pkgs.firefox", result["generated"])
        self.assertIn("programs.git.enable = true", result["generated"])
        self.assertFalse(result["writeEnabled"])
        self.assertFalse(result["activationEnabled"])
        self.assertFalse(result["flakeInputMutationEnabled"])
        self.assertFalse(user_state_path.exists())
        self.assertFalse(output_path.exists())

        with self.assertRaises(HTTPError) as context:
            self.request_json(
                "/api/home-manager/preview",
                method="POST",
                token=self.server.token,
                body={
                    "username": "bob",
                    "integration": "standalone",
                    "packages": ["firefox"],
                },
            )
        self.assertEqual(context.exception.code, 400)
        context.exception.close()

    def test_home_manager_adoption_plan_and_validation_are_read_only(self) -> None:
        root = self.server.config_root
        root.mkdir()
        configuration = root / "configuration.nix"
        original = (
            "{ ... }:\n{\n  imports = [\n  ];\n"
            "  home-manager.users.alice = ./alice.nix;\n}\n"
        )
        configuration.write_text(original, encoding="utf-8")
        payload = {
            "username": "alice",
            "integration": "nixos-module",
            "packages": ["firefox", "git"],
        }

        plan = self.request_json(
            "/api/home-manager/adoption-plan",
            method="POST",
            token=self.server.token,
            body=payload,
        )
        self.assertEqual(plan["status"], "ready")
        self.assertEqual(len(plan["changes"]), 4)
        self.assertIn("ncm/user-state.json", plan["combinedDiff"])
        self.assertIn("home-manager-alice.nix", plan["combinedDiff"])
        self.assertFalse(plan["safeToApply"])
        self.assertFalse(plan["writeEnabled"])
        self.assertEqual(configuration.read_text(encoding="utf-8"), original)
        self.assertFalse((root / "ncm").exists())

        self.server.home_manager_validator = lambda *args, **kwargs: FakeHomeManagerValidation()
        validation = self.request_json(
            "/api/home-manager/validate-adoption",
            method="POST",
            token=self.server.token,
            body=payload,
        )
        self.assertEqual(validation["status"], "passed")
        self.assertTrue(validation["workingCopyRemoved"])
        self.assertFalse(validation["writeEnabled"])
        self.assertFalse(validation["buildEnabled"])
        self.assertFalse((root / "ncm").exists())

    def test_home_manager_build_preview_requires_exact_fingerprint_and_streams(self) -> None:
        root = self.server.config_root
        root.mkdir()
        configuration = root / "configuration.nix"
        original = (
            "{ ... }:\n{\n  imports = [\n  ];\n"
            "  home-manager.users.alice = ./alice.nix;\n}\n"
        )
        configuration.write_text(original, encoding="utf-8")
        (root / "flake.nix").write_text(
            '{ outputs = _: { nixosConfigurations.desktop = null; }; }\n',
            encoding="utf-8",
        )
        inspection = self.server.home_manager_inspector(
            root,
            standalone_root=self.server.home_manager_root,
            user_state_path=self.server.user_state_path,
        )
        plan = plan_home_manager_adoption(
            root,
            standalone_root=self.server.home_manager_root,
            user_state_path=self.server.user_state_path,
            username="alice",
            integration="nixos-module",
            packages=("firefox", "git"),
            inspection=inspection,
        )
        fingerprint, _ = home_manager_plan_identity(plan, "desktop")

        def executor(command, cwd, cancel_event, line_sink):
            line_sink("stderr", "streamed Home Manager build line")
            output = "/nix/store/" + "d" * 32 + "-home-manager-generation"
            line_sink("stdout", output)
            return 0, (output,)

        self.server.home_manager_build_manager.close()
        def validator(candidate, **kwargs):
            candidate_fingerprint, _ = home_manager_plan_identity(
                candidate, "desktop"
            )
            return SimpleNamespace(
                status="passed",
                flake_target="desktop",
                plan_fingerprint=candidate_fingerprint,
                working_copy_removed=True,
            )

        self.server.home_manager_build_manager = HomeManagerBuildManager(
            config_root=root,
            standalone_root=self.server.home_manager_root,
            user_state_path=self.server.user_state_path,
            flake_target="desktop",
            executor=executor,
            which=lambda name: f"/tools/{name}",
            path_is_dir=lambda _: True,
            inspector=self.server.home_manager_inspector,
            validator=validator,
        )
        payload = {
            "username": "alice",
            "integration": "nixos-module",
            "packages": ["firefox", "git"],
            "planFingerprint": fingerprint,
        }

        with self.assertRaises(HTTPError) as context:
            self.request_json(
                "/api/home-manager/build-preview", method="POST", body=payload
            )
        self.assertEqual(context.exception.code, 403)
        context.exception.close()

        started = self.request_json(
            "/api/home-manager/build-preview",
            method="POST",
            token=self.server.token,
            body=payload,
        )
        job_id = started["jobId"]
        deadline = time.monotonic() + 3
        result = started
        while result["cancellable"] and time.monotonic() < deadline:
            result = self.request_json(
                f"/api/home-manager/build-preview/{job_id}?after={result['nextCursor']}"
            )
            time.sleep(0.01)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["workflow"], "home-manager")
        self.assertFalse(result["configurationWriteEnabled"])
        self.assertFalse(result["homeManagerActivationEnabled"])
        self.assertFalse(result["activationPreviewReady"])
        self.assertEqual(configuration.read_text(encoding="utf-8"), original)
        self.assertFalse((root / "ncm").exists())
        latest = self.request_json("/api/home-manager/build-preview")
        self.assertEqual(latest["jobId"], job_id)
        self.assertEqual(latest["activationPackagePath"], result["outputPaths"][0])

    def test_home_manager_live_apply_requires_exact_one_time_confirmation(self) -> None:
        root = self.server.config_root
        root.mkdir()
        configuration = root / "configuration.nix"
        original = (
            "{ ... }:\n{\n  imports = [\n  ];\n"
            "  home-manager.users.alice = ./alice.nix;\n}\n"
        )
        configuration.write_text(original, encoding="utf-8")
        payload = {
            "username": "alice",
            "integration": "nixos-module",
            "packages": ["firefox", "git"],
        }

        with self.assertRaises(HTTPError) as context:
            self.request_json(
                "/api/helper/home-manager/validate", method="POST", body=payload
            )
        self.assertEqual(context.exception.code, 403)
        context.exception.close()

        prepared = self.request_json(
            "/api/helper/home-manager/validate",
            method="POST",
            token=self.server.token,
            body=payload,
        )
        self.assertTrue(prepared["confirmationRequired"])
        self.assertTrue(prepared["liveWriteEnabled"])
        self.assertNotIn("validationReceipt", prepared)
        self.assertRegex(prepared["planFingerprint"], r"^[0-9a-f]{64}$")
        self.assertEqual(configuration.read_text(encoding="utf-8"), original)

        apply_payload = {
            "intentId": prepared["intentId"],
            "planFingerprint": prepared["planFingerprint"],
            "confirmed": False,
        }
        with self.assertRaises(HTTPError) as context:
            self.request_json(
                "/api/helper/home-manager/apply",
                method="POST",
                token=self.server.token,
                body=apply_payload,
            )
        self.assertEqual(context.exception.code, 400)
        context.exception.close()

        apply_payload["confirmed"] = True
        applied = self.request_json(
            "/api/helper/home-manager/apply",
            method="POST",
            token=self.server.token,
            body=apply_payload,
        )
        self.assertEqual(applied["state"], "committed")
        self.assertTrue(applied["authorizedByPolkit"])
        self.assertFalse(applied["homeManagerActivationEnabled"])
        self.assertFalse(applied["switchEnabled"])

        with self.assertRaises(HTTPError) as context:
            self.request_json(
                "/api/helper/home-manager/apply",
                method="POST",
                token=self.server.token,
                body=apply_payload,
            )
        self.assertEqual(context.exception.code, 400)
        context.exception.close()

    def test_candidate_validation_is_authorized_and_never_enables_activation(self) -> None:
        with self.assertRaises(HTTPError) as context:
            self.request_json("/api/validate-adoption", method="POST")
        self.assertEqual(context.exception.code, 403)
        context.exception.close()

        result = self.request_json(
            "/api/validate-adoption",
            method="POST",
            token=self.server.token,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["readyForApplyProtocol"])
        self.assertFalse(result["activationEnabled"])

    def test_helper_validation_requires_token_and_exposes_no_apply_capability(self) -> None:
        with self.assertRaises(HTTPError) as context:
            self.request_json("/api/helper/validate-adoption", method="POST")
        self.assertEqual(context.exception.code, 403)
        context.exception.close()

        result = self.request_json(
            "/api/helper/validate-adoption",
            method="POST",
            token=self.server.token,
        )
        self.assertEqual(result["source"], "system-helper")
        self.assertEqual(result["status"], "passed")
        self.assertFalse(result["validationReceiptIssued"])
        self.assertFalse(result["applyEnabled"])

    def test_save_writes_validated_files(self) -> None:
        result = self.request_json(
            "/api/save",
            method="POST",
            token=self.server.token,
            body={"schemaVersion": 1, "packages": ["firefox"], "options": {}},
        )
        self.assertTrue(result["saved"])
        self.assertIn("pkgs.firefox", self.server.output_path.read_text(encoding="utf-8"))
        self.assertEqual(
            json.loads(self.server.state_path.read_text(encoding="utf-8"))["packages"],
            ["firefox"],
        )

    def test_read_only_mode_reports_and_blocks_local_save(self) -> None:
        self.server.local_write_enabled = False

        config = self.request_json("/api/config")
        self.assertEqual(config["application"], "nix-control-manager")
        self.assertEqual(config["apiVersion"], 1)
        self.assertEqual(config["version"], "0.1.0-alpha.1")
        self.assertEqual(config["releaseChannel"], "alpha")
        self.assertFalse(config["localWriteEnabled"])
        with self.assertRaises(HTTPError) as context:
            self.request_json(
                "/api/save",
                method="POST",
                token=self.server.token,
                body={"schemaVersion": 1, "packages": ["firefox"], "options": {}},
            )

        self.assertEqual(context.exception.code, 400)
        payload = json.loads(context.exception.read())
        context.exception.close()
        self.assertIn("disabled in read-only mode", payload["error"])
        self.assertFalse(self.server.state_path.exists())
        self.assertFalse(self.server.output_path.exists())

    def test_save_rejects_invalid_typed_setting(self) -> None:
        with self.assertRaises(HTTPError) as context:
            self.request_json(
                "/api/save",
                method="POST",
                token=self.server.token,
                body={
                    "schemaVersion": 1,
                    "packages": [],
                    "options": {"networking.firewall.allowedTCPPorts": [70000]},
                },
            )
        self.assertEqual(context.exception.code, 400)
        payload = json.loads(context.exception.read())
        context.exception.close()
        self.assertIn("at most 65535", payload["error"])

    def test_save_rejects_explicit_dependency_contradiction(self) -> None:
        cases = (
            (
                {
                    "services.pipewire.enable": False,
                    "services.pipewire.pulse.enable": True,
                },
                "requires services.pipewire.enable",
            ),
            (
                {
                    "hardware.bluetooth.enable": False,
                    "services.blueman.enable": True,
                },
                "requires hardware.bluetooth.enable",
            ),
            (
                {"zramSwap.enable": False, "zramSwap.memoryPercent": 50},
                "requires zramSwap.enable",
            ),
        )
        for options, message in cases:
            with self.subTest(options=options), self.assertRaises(HTTPError) as context:
                self.request_json(
                    "/api/save",
                    method="POST",
                    token=self.server.token,
                    body={
                        "schemaVersion": 1,
                        "packages": [],
                        "options": options,
                    },
                )
            self.assertEqual(context.exception.code, 400)
            payload = json.loads(context.exception.read())
            context.exception.close()
            self.assertIn(message, payload["error"])

    def test_build_preview_requires_token_and_streams_a_fixed_job(self) -> None:
        root = self.server.config_root
        root.mkdir(exist_ok=True)
        (root / "configuration.nix").write_text(
            "{ ... }: {\n  imports = [\n    ./ncm\n  ];\n}\n", encoding="utf-8"
        )
        managed = root / "ncm"
        managed.mkdir()
        (managed / "default.nix").write_text(
            "{ ... }: { imports = [ ./packages.nix ]; }\n", encoding="utf-8"
        )
        (managed / "packages.nix").write_text(
            "{ pkgs, ... }: { environment.systemPackages = with pkgs; [ ]; }\n",
            encoding="utf-8",
        )
        (managed / "state.json").write_text(
            '{"schemaVersion":1,"packages":{},"options":{}}', encoding="utf-8"
        )

        def executor(command, cwd, cancel_event, line_sink):
            line_sink("stderr", "streamed build line")
            output = "/nix/store/" + "b" * 32 + "-preview"
            line_sink("stdout", output)
            return 0, (output,)

        self.server.build_manager.close()
        self.server.build_manager = CandidateBuildManager(
            config_root=root,
            executor=executor,
            which=lambda name: f"/tools/{name}",
        )

        with self.assertRaises(HTTPError) as context:
            self.request_json("/api/build-preview", method="POST")
        self.assertEqual(context.exception.code, 403)
        context.exception.close()

        started = self.request_json(
            "/api/build-preview", method="POST", token=self.server.token
        )
        job_id = started["jobId"]
        deadline = time.monotonic() + 3
        result = started
        while result["cancellable"] and time.monotonic() < deadline:
            result = self.request_json(
                f"/api/build-preview/{job_id}?after={result['nextCursor']}"
            )
            time.sleep(0.01)
        self.assertEqual(result["status"], "passed")
        self.assertFalse(result["activationEnabled"])
        self.assertFalse(result["configurationWriteEnabled"])
        latest = self.request_json("/api/build-preview")
        self.assertEqual(latest["jobId"], job_id)
        self.assertEqual(latest["status"], "passed")
        dry = self.request_json(
            "/api/helper/activation-preview",
            method="POST",
            token=self.server.token,
        )
        self.assertEqual(dry["systemPath"], result["outputPaths"][0])
        self.assertTrue(dry["dryActivateExecuted"])
        self.assertFalse(dry["activationEnabled"])
        active = self.request_json(
            "/api/helper/test-activation",
            method="POST",
            body={"testReceipt": dry["testReceipt"]},
            token=self.server.token,
        )
        self.assertEqual(active["status"], "active")
        self.assertFalse(active["switchEnabled"])
        recovered = self.request_json(
            "/api/helper/recover-test-activation",
            method="POST",
            body={"sessionId": active["sessionId"]},
            token=self.server.token,
        )
        self.assertEqual(recovered["status"], "recovered")
        self.assertTrue(recovered["currentSystemRestored"])

        with self.assertRaises(HTTPError) as context:
            self.request_json(
                "/api/helper/commit-tested-system",
                method="POST",
                body={"sessionId": active["sessionId"], "confirmed": False},
                token=self.server.token,
            )
        self.assertEqual(context.exception.code, 400)
        context.exception.close()

        committing = self.request_json(
            "/api/helper/commit-tested-system",
            method="POST",
            body={"sessionId": active["sessionId"], "confirmed": True},
            token=self.server.token,
        )
        self.assertEqual(committing["status"], "committing")
        self.assertEqual(committing["systemPath"], result["outputPaths"][0])
        status = self.request_json(
            "/api/helper/activation-session-status",
            method="POST",
            body={"sessionId": active["sessionId"]},
            token=self.server.token,
        )
        self.assertEqual(status["status"], "committed")
        rollback = self.request_json(
            "/api/helper/rollback-committed-system",
            method="POST",
            body={"sessionId": active["sessionId"], "confirmed": True},
            token=self.server.token,
        )
        self.assertEqual(rollback["status"], "rolling-back")


if __name__ == "__main__":
    unittest.main()
