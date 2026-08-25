import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from nix_control_manager.flake_inspector import inspect_flake


class FlakeInspectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_lock(self, *, follows: bool = False) -> None:
        inputs = {"nixpkgs": "nixpkgs"}
        if follows:
            inputs["home-manager"] = "home-manager"
        nodes = {
            "root": {"inputs": inputs},
            "nixpkgs": {
                "locked": {
                    "lastModified": 1_787_000_000,
                    "narHash": "sha256-example",
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
        }
        if follows:
            nodes["home-manager"] = {
                "inputs": {"nixpkgs": ["nixpkgs"]},
                "locked": {
                    "lastModified": 1_787_100_000,
                    "narHash": "sha256-home",
                    "owner": "nix-community",
                    "repo": "home-manager",
                    "rev": "b" * 40,
                    "type": "github",
                },
                "original": {
                    "owner": "nix-community",
                    "repo": "home-manager",
                    "type": "github",
                },
            }
        (self.root / "flake.lock").write_text(
            json.dumps({"nodes": nodes, "root": "root", "version": 7}),
            encoding="utf-8",
        )

    def test_missing_flake_is_a_non_mutating_absent_state(self) -> None:
        result = inspect_flake(self.root, which=lambda _: None)
        mapping = result.to_mapping()

        self.assertEqual(result.status, "absent")
        self.assertEqual(result.evaluation_status, "not-run")
        self.assertTrue(mapping["readOnly"])
        self.assertFalse(mapping["networkAccessEnabled"])
        self.assertFalse(mapping["lockWriteEnabled"])
        self.assertFalse(mapping["inputUpdateEnabled"])

    def test_missing_or_invalid_lock_never_starts_nix(self) -> None:
        (self.root / "flake.nix").write_text("{ outputs = _: { }; }\n", encoding="utf-8")
        calls = []

        missing = inspect_flake(
            self.root,
            runner=lambda *args, **kwargs: calls.append(args),
            which=lambda _: "/run/current-system/sw/bin/nix",
        )
        (self.root / "flake.lock").write_text("not-json", encoding="utf-8")
        invalid = inspect_flake(
            self.root,
            runner=lambda *args, **kwargs: calls.append(args),
            which=lambda _: "/run/current-system/sw/bin/nix",
        )

        self.assertEqual(missing.status, "incomplete")
        self.assertEqual(invalid.status, "invalid")
        self.assertEqual(calls, [])

    def test_parses_locked_inputs_and_offline_outputs(self) -> None:
        (self.root / "flake.nix").write_text("{ outputs = _: { }; }\n", encoding="utf-8")
        self.write_lock(follows=True)
        commands = []

        def runner(command, **kwargs):
            commands.append((command, kwargs))
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "inputs": ["home-manager", "nixpkgs"],
                        "nixosConfigurations": ["desktop", "laptop"],
                    }
                ),
                stderr="",
            )

        result = inspect_flake(
            self.root,
            flake_target="desktop",
            runner=runner,
            which=lambda _: "/run/current-system/sw/bin/nix",
        )
        mapping = result.to_mapping()

        self.assertEqual(result.status, "detected")
        self.assertEqual(result.lock_status, "valid")
        self.assertEqual(result.evaluation_status, "passed")
        self.assertEqual(result.active_target_status, "selected")
        self.assertEqual(result.nixos_configurations, ("desktop", "laptop"))
        self.assertEqual([item.name for item in result.inputs], ["home-manager", "nixpkgs"])
        self.assertEqual(result.inputs[0].source, "github:nix-community/home-manager")
        self.assertEqual(result.inputs[1].ref, "nixos-unstable")
        self.assertEqual(mapping["inputs"][1]["lastModifiedDate"], "2026-08-17")
        command, kwargs = commands[0]
        self.assertIn("--offline", command)
        self.assertIn("--no-write-lock-file", command)
        self.assertEqual(kwargs["cwd"], self.root.resolve())
        self.assertEqual(kwargs["env"]["NCM_INSPECT_CONFIG_ROOT"], str(self.root.resolve()))

    def test_reports_missing_target_and_scrubs_url_credentials(self) -> None:
        (self.root / "flake.nix").write_text("{ outputs = _: { }; }\n", encoding="utf-8")
        lock = {
            "nodes": {
                "root": {"inputs": {"private": "private"}},
                "private": {
                    "locked": {
                        "type": "git",
                        "url": "https://user:secret@example.test/repo.git?token=hidden",
                        "rev": "c" * 40,
                        "narHash": "sha256-private",
                    },
                    "original": {"type": "git"},
                },
            },
            "root": "root",
            "version": 7,
        }
        (self.root / "flake.lock").write_text(json.dumps(lock), encoding="utf-8")

        result = inspect_flake(
            self.root,
            flake_target="missing-host",
            runner=lambda command, **kwargs: subprocess.CompletedProcess(
                command,
                0,
                stdout='{"inputs":["private"],"nixosConfigurations":["desktop"]}',
                stderr="",
            ),
            which=lambda _: "/bin/nix",
        )

        self.assertEqual(result.active_target_status, "missing")
        self.assertEqual(result.inputs[0].source, "https://example.test/repo.git")
        self.assertNotIn("secret", json.dumps(result.to_mapping()))
        self.assertTrue(result.warnings)

    def test_unsafe_target_is_never_reported_as_selected(self) -> None:
        (self.root / "flake.nix").write_text("{ outputs = _: { }; }\n", encoding="utf-8")
        self.write_lock()

        result = inspect_flake(
            self.root,
            flake_target="bad.target",
            runner=lambda command, **kwargs: subprocess.CompletedProcess(
                command,
                0,
                stdout='{"inputs":["nixpkgs"],"nixosConfigurations":["bad.target"]}',
                stderr="",
            ),
            which=lambda _: "/bin/nix",
        )

        self.assertEqual(result.evaluation_status, "passed")
        self.assertEqual(result.active_target_status, "invalid")


if __name__ == "__main__":
    unittest.main()
