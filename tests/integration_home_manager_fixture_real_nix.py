"""Run the Home Manager fixture transaction with real Nix evaluation."""

import argparse
import json
from pathlib import Path

from nix_control_manager.home_manager_adoption import (
    plan_home_manager_adoption,
    validate_home_manager_adoption,
)
from nix_control_manager.home_manager_apply_workflow import (
    execute_home_manager_fixture_apply_workflow,
)
from nix_control_manager.transaction import initialize_transaction_fixture


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    args = parser.parse_args()

    initialize_transaction_fixture(args.root)
    (args.root / "home.nix").write_text(
        '{ pkgs, ... }:\n{\n  home.username = "fixture-user";\n}\n',
        encoding="utf-8",
    )
    (args.root / "flake.nix").write_text(
        "{\n"
        "  outputs = { ... }:\n"
        "    let\n"
        "      pkgs = { git = \"git-package-sentinel\"; };\n"
        "      home = import ./home.nix { inherit pkgs; config = { }; };\n"
        "      managed = import (builtins.head home.imports) { inherit pkgs; };\n"
        "      activationPackage = assert managed.home.packages == [ pkgs.git ]; {\n"
        "        drvPath = \"/nix/store/ncm-home-fixture.drv\";\n"
        "      };\n"
        "    in { homeConfigurations.fixture-user = { inherit activationPackage; }; };\n"
        "}\n",
        encoding="utf-8",
    )

    state = args.root.parent / "user-state.json"
    plan = plan_home_manager_adoption(
        args.root,
        standalone_root=args.root,
        user_state_path=state,
        username="fixture-user",
        integration="standalone",
        packages=("git",),
    )
    validation = validate_home_manager_adoption(plan, timeout=120)
    if validation.status != "passed":
        raise RuntimeError(f"Initial Home Manager validation failed: {validation.to_mapping()}")

    result = execute_home_manager_fixture_apply_workflow(
        plan,
        validation,
        journal_root=args.journal,
        timeout=120,
    )
    if result.state != "committed":
        raise RuntimeError(f"Home Manager fixture transaction failed: {result.to_mapping()}")
    if state.exists():
        raise RuntimeError("Fixture workflow unexpectedly persisted user-state")
    if not (args.root / "ncm" / "managed-home-fixture-user.nix").is_file():
        raise RuntimeError("Managed Home Manager module was not committed")

    print(json.dumps(result.to_mapping(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
