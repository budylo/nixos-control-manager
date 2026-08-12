from __future__ import annotations

import argparse
import json
from pathlib import Path

from nix_control_manager.adoption import plan_adoption
from nix_control_manager.apply_workflow import execute_fixture_apply_workflow
from nix_control_manager.candidate import validate_adoption
from nix_control_manager.transaction import initialize_transaction_fixture


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the full apply workflow against an explicitly marked fixture"
    )
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--journal-root", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--initialize-fixture", action="store_true")
    args = parser.parse_args()

    if args.initialize_fixture:
        initialize_transaction_fixture(args.config_root)

    plan = plan_adoption(args.config_root)
    pre_validation = validate_adoption(args.config_root, timeout=args.timeout)
    if pre_validation.status != "passed":
        print(json.dumps({"phase": "pre-validation", **pre_validation.to_mapping()}, indent=2))
        return 2
    result = execute_fixture_apply_workflow(
        plan,
        pre_validation,
        journal_root=args.journal_root,
        timeout=args.timeout,
    )
    print(json.dumps(result.to_mapping(), ensure_ascii=False, indent=2))
    return 0 if result.state == "committed" else 3


if __name__ == "__main__":
    raise SystemExit(main())
