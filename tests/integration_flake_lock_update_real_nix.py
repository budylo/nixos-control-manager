#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from nix_control_manager.flake_lock_helper_backend import LiveFlakeLockHelperBackend
from nix_control_manager.flake_lock_update import plan_flake_lock_update, source_manifest
from nix_control_manager.helper_service import (
    FLAKE_LOCK_APPLY_ACTION_ID,
    HelperDispatcher,
    HelperTarget,
    MockPolkitAuthorizer,
)


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="ncm-real-flake-lock-") as temporary:
        base = Path(temporary)
        root = base / "etc" / "nixos"
        root.mkdir(parents=True)
        shutil.copyfile(repository / "flake.lock", root / "flake.lock")
        (root / "flake.nix").write_text(
            """{
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs = { self, nixpkgs }: {
    nixosConfigurations.integration = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [ ({ ... }: {
        system.stateVersion = "26.05";
        boot.loader.grub.devices = [ "nodev" ];
        fileSystems."/" = { device = "none"; fsType = "tmpfs"; };
      }) ];
    };
  };
}
""",
            encoding="utf-8",
        )
        before = (root / "flake.lock").read_bytes()
        candidate_root = base / "candidate"
        shutil.copytree(root, candidate_root)
        subprocess.run(
            [
                "nix",
                "--extra-experimental-features",
                "nix-command flakes",
                "--refresh",
                "flake",
                "update",
                "nixpkgs",
                "--flake",
                f"path:{candidate_root}",
            ],
            check=True,
            timeout=300,
        )
        candidate = (candidate_root / "flake.lock").read_text(encoding="utf-8")
        if candidate.encode("utf-8") == before:
            print("real flake-lock integration: no upstream update available; skipped")
            return 0
        source_fingerprint, _, _ = source_manifest(root)
        plan = plan_flake_lock_update(
            root,
            input_name="nixpkgs",
            source_fingerprint=source_fingerprint,
            candidate=candidate,
        )
        target = HelperTarget(
            target_id="control",
            configuration_root=root,
            allowed_relative_paths=frozenset({"ncm/state.json", "ncm/packages.nix"}),
            fixture_only=False,
            apply_enabled=False,
            flake_target="integration",
            test_activation_enabled=True,
            test_journal_root=base / "test-journal",
            managed_write_enabled=True,
            managed_journal_root=base / "managed-journal",
            permanent_switch_enabled=True,
            flake_lock_write_enabled=True,
            flake_lock_journal_root=base / "flake-journal",
        )
        dispatcher = HelperDispatcher(
            targets=(target,),
            authorizer=MockPolkitAuthorizer(
                allowed={(1000, FLAKE_LOCK_APPLY_ACTION_ID)}
            ),
            backend=LiveFlakeLockHelperBackend(timeout=300),
        )
        validate_request = {
            "schemaVersion": 1,
            "requestId": "real-flake-validate",
            "operation": "validate-flake-lock-update",
            "payload": {
                "targetId": "control",
                "planFingerprint": plan.plan_fingerprint,
                "inputName": "nixpkgs",
                "sourceFingerprint": source_fingerprint,
                "changes": [
                    {
                        "relativePath": "flake.lock",
                        "action": "modify",
                        "previousSha256": plan.change.previous_sha256,
                        "candidateSha256": plan.change.candidate_sha256,
                        "candidate": candidate,
                    }
                ],
            },
        }
        validated = dispatcher.handle(validate_request, peer_uid=1000)
        if validated["status"] != "ok":
            raise RuntimeError(json.dumps(validated, indent=2))
        applied = dispatcher.handle(
            {
                "schemaVersion": 1,
                "requestId": "real-flake-apply01",
                "operation": "apply-validated-flake-lock-update",
                "payload": {
                    "targetId": "control",
                    "planFingerprint": plan.plan_fingerprint,
                    "validationReceipt": validated["result"]["validationReceipt"],
                },
            },
            peer_uid=1000,
        )
        if applied["status"] != "ok" or applied["result"]["state"] != "committed":
            raise RuntimeError(json.dumps(applied, indent=2))
        if (root / "flake.lock").read_text(encoding="utf-8") != candidate:
            raise RuntimeError("The exact candidate lock was not installed")
        print("real flake-lock integration: passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
