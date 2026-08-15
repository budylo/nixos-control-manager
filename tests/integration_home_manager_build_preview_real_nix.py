"""Build a disposable standalone Home Manager activationPackage with real Nix."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time

from nix_control_manager.candidate_build import HomeManagerBuildManager
from nix_control_manager.home_manager_adoption import (
    plan_home_manager_adoption,
    validate_home_manager_adoption,
)


ACTIVE = {"queued", "preparing", "running", "cancelling", "cleaning"}


def source_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(path for path in root.rglob("*") if path.is_file())
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--lock-file", type=Path, required=True)
    parser.add_argument("--system", required=True)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "home.nix").write_text(
        '{ pkgs, ... }:\n{\n  home.username = "fixture-user";\n}\n',
        encoding="utf-8",
    )
    (root / "flake.nix").write_text(
        f'''{{
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs = {{ self, nixpkgs }}:
    let
      pkgs = nixpkgs.legacyPackages."{args.system}";
      home = import ./home.nix {{ inherit pkgs; config = {{ }}; }};
      managed = import (builtins.head home.imports) {{ inherit pkgs; }};
      activationPackage = assert managed.home.packages == [ pkgs.git ];
        pkgs.runCommand "ncm-home-build-preview" {{ }} ''
          mkdir -p "$out"
          echo preview > "$out/marker"
        '';
    in {{ homeConfigurations.fixture-user = {{ inherit activationPackage; }}; }};
}}
''',
        encoding="utf-8",
    )
    shutil.copyfile(args.lock_file.resolve(), root / "flake.lock")

    state = root.parent / "user-state.json"
    plan = plan_home_manager_adoption(
        root,
        standalone_root=root,
        user_state_path=state,
        username="fixture-user",
        integration="standalone",
        packages=("git",),
    )
    validation = validate_home_manager_adoption(plan, timeout=120)
    if validation.status != "passed" or not validation.plan_fingerprint:
        raise RuntimeError(f"Initial validation failed: {validation.to_mapping()}")

    before = source_hashes(root)
    result_link = Path.cwd() / "result"
    result_link_before = result_link.exists() or result_link.is_symlink()
    manager = HomeManagerBuildManager(
        config_root=root,
        standalone_root=root,
        user_state_path=state,
        timeout=args.timeout,
    )
    result = manager.start(
        username="fixture-user",
        integration="standalone",
        packages=("git",),
        plan_fingerprint=validation.plan_fingerprint,
    )
    deadline = time.monotonic() + args.timeout + 30
    try:
        while result["status"] in ACTIVE:
            if time.monotonic() >= deadline:
                manager.cancel(result["jobId"])
                raise RuntimeError("Home Manager build-preview exceeded its deadline")
            time.sleep(0.1)
            result = manager.poll(result["jobId"])
    finally:
        manager.close()

    after = source_hashes(root)
    summary = {
        "status": result["status"],
        "activationPackagePath": result.get("activationPackagePath"),
        "workingCopyRemoved": result.get("workingCopyRemoved"),
        "sourceFilesUnchanged": before == after,
        "configurationWriteEnabled": result.get("configurationWriteEnabled"),
        "homeManagerActivationEnabled": result.get("homeManagerActivationEnabled"),
        "switchEnabled": result.get("switchEnabled"),
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))

    assert result["status"] == "passed", result
    assert result["workingCopyRemoved"] is True
    assert result["configurationWriteEnabled"] is False
    assert result["homeManagerActivationEnabled"] is False
    assert result["activationPreviewReady"] is False
    assert result["switchEnabled"] is False
    assert result["flakeInputMutationEnabled"] is False
    assert result["lockFileWriteEnabled"] is False
    assert result["activationPackagePath"] == result["outputPaths"][0]
    assert (Path(result["activationPackagePath"]) / "marker").read_text().strip() == "preview"
    assert before == after
    assert not state.exists()
    assert result_link_before or not (result_link.exists() or result_link.is_symlink())
    assert "--no-link" in result["command"]
    assert "--no-write-lock-file" in result["command"]
    assert "switch" not in result["command"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
