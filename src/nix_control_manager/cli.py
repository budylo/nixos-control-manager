from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from .errors import NcmError
from .adoption import plan_adoption
from .candidate import validate_adoption
from .home_manager_inspector import inspect_home_manager
from .model import ManagedState
from .migration import load_migration_preview
from .nix_generator import generate_module
from .preview import build_preview
from .storage import load_state, save_generated_module, save_state
from .system_inspector import inspect_system


def _path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ncm", description="Manage a generated NixOS module safely"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="create an empty managed state")
    init.add_argument("--state", type=_path, default=_path("state.local.json"))

    preview = subparsers.add_parser("preview", help="preview generated Nix changes")
    preview.add_argument("--state", type=_path, default=_path("state.local.json"))
    preview.add_argument("--output", type=_path, default=_path("managed.local.nix"))

    generate = subparsers.add_parser("generate", help="write the generated Nix module")
    generate.add_argument("--state", type=_path, default=_path("state.local.json"))
    generate.add_argument("--output", type=_path, default=_path("managed.local.nix"))

    detect = subparsers.add_parser(
        "detect", help="inspect a NixOS configuration without changing it"
    )
    detect.add_argument(
        "--config-root",
        type=_path,
        default=_path(os.environ.get("NCM_CONFIG_ROOT", "/etc/nixos")),
    )
    detect.add_argument("--json", action="store_true", dest="as_json")

    detect_home = subparsers.add_parser(
        "detect-home-manager",
        help="inspect Home Manager integration and user state without changing them",
    )
    detect_home.add_argument(
        "--config-root",
        type=_path,
        default=_path(os.environ.get("NCM_CONFIG_ROOT", "/etc/nixos")),
    )
    detect_home.add_argument(
        "--standalone-root",
        type=_path,
        default=_path(os.environ.get("NCM_HOME_MANAGER_ROOT", "~/.config/home-manager")),
    )
    detect_home.add_argument(
        "--user-state", type=_path, default=_path("user-state.local.json")
    )
    detect_home.add_argument("--json", action="store_true", dest="as_json")

    migrate = subparsers.add_parser(
        "migrate-state", help="preview or write a normalized managed state"
    )
    migrate.add_argument("--state", type=_path, required=True)
    migrate.add_argument(
        "--output",
        type=_path,
        help="write normalized state here; without this option no files are changed",
    )

    adoption = subparsers.add_parser(
        "plan-adoption", help="show an exact read-only adoption or migration plan"
    )
    adoption.add_argument(
        "--config-root",
        type=_path,
        default=_path(os.environ.get("NCM_CONFIG_ROOT", "/etc/nixos")),
    )
    adoption.add_argument("--json", action="store_true", dest="as_json")

    validate = subparsers.add_parser(
        "validate-adoption",
        help="evaluate an adoption plan in a disposable copy without building it",
    )
    validate.add_argument(
        "--config-root",
        type=_path,
        default=_path(os.environ.get("NCM_CONFIG_ROOT", "/etc/nixos")),
    )
    validate.add_argument(
        "--flake-target",
        help="nixosConfigurations host name; defaults to the detected hostname",
    )
    validate.add_argument("--timeout", type=int, default=120)
    validate.add_argument("--json", action="store_true", dest="as_json")

    serve = subparsers.add_parser("serve", help="start the local graphical interface")
    serve.add_argument("--state", type=_path, default=_path("state.local.json"))
    serve.add_argument(
        "--user-state", type=_path, default=_path("user-state.local.json")
    )
    serve.add_argument("--output", type=_path, default=_path("managed.local.nix"))
    serve.add_argument(
        "--config-root",
        type=_path,
        default=_path(os.environ.get("NCM_CONFIG_ROOT", "/etc/nixos")),
    )
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--flake-target")
    serve.add_argument(
        "--home-manager-root",
        type=_path,
        default=_path(os.environ.get("NCM_HOME_MANAGER_ROOT", "~/.config/home-manager")),
    )
    serve.add_argument("--validation-timeout", type=int, default=120)
    serve.add_argument(
        "--build-timeout",
        type=int,
        default=3600,
        help="maximum seconds for one unprivileged candidate build preview",
    )
    serve.add_argument(
        "--helper-socket",
        type=_path,
        default=_path(
            os.environ.get(
                "NCM_HELPER_SOCKET", "/run/nix-control-manager/helper.sock"
            )
        ),
        help="Unix socket for optional live-read-only system-helper validation",
    )
    serve.add_argument(
        "--helper-target",
        default=os.environ.get("NCM_HELPER_TARGET", "live"),
        help="configured live-read-only helper target identifier",
    )
    serve.add_argument("--open", action="store_true", dest="open_browser")
    return parser


def run(args: argparse.Namespace) -> int:
    if args.command == "init":
        if args.state.exists():
            raise NcmError(f"Refusing to overwrite existing state: {args.state}")
        save_state(args.state, ManagedState.empty())
        print(f"Created {args.state}")
        return 0

    if args.command == "preview":
        state = load_state(args.state)
        preview = build_preview(state, args.output)
        print(preview["diff"] or "No changes.")
        return 0

    if args.command == "generate":
        state = load_state(args.state)
        generated = generate_module(state)
        save_generated_module(args.output, generated)
        print(f"Generated {args.output}")
        return 0

    if args.command == "detect":
        inspection = inspect_system(args.config_root)
        if args.as_json:
            print(json.dumps(inspection.to_mapping(), ensure_ascii=False, indent=2))
        else:
            platform_info = inspection.to_mapping()["platform"]
            system_name = platform_info["name"] or "Unknown system"
            release = f" {platform_info['release']}" if platform_info["release"] else ""
            print(f"System:        {system_name}{release} ({platform_info['hostname']})")
            print(
                f"Configuration: {inspection.configuration_mode} at {inspection.config_root}"
            )
            print(f"Managed module: {inspection.managed_status}")
            print(f"Managed state:  {inspection.state_status}")
            for warning in inspection.warnings:
                print(f"Warning: {warning}")
        return 0

    if args.command == "migrate-state":
        migration = load_migration_preview(args.state)
        if args.output:
            save_state(args.output, migration.state)
            print(f"Wrote normalized state to {args.output}")
        else:
            print(
                json.dumps(
                    migration.to_mapping(), ensure_ascii=False, indent=2, sort_keys=True
                )
            )
        return 0

    if args.command == "detect-home-manager":
        inspection = inspect_home_manager(
            args.config_root,
            standalone_root=args.standalone_root,
            user_state_path=args.user_state,
        )
        if args.as_json:
            print(json.dumps(inspection.to_mapping(), ensure_ascii=False, indent=2))
        else:
            integrations = ", ".join(inspection.integrations) or "none"
            print(f"Status:       {inspection.status}")
            print(f"Integrations: {integrations}")
            print(f"Users:        {len(inspection.users)}")
            print(f"User state:   {inspection.user_state.status} at {inspection.user_state.path}")
            for user in inspection.users:
                print(f"  {user.name}: {user.integration} ({user.source})")
            for warning in inspection.warnings:
                print(f"Warning: {warning}")
            print("Writes:       disabled")
            print("Activation:   disabled")
        return 0

    if args.command == "plan-adoption":
        plan = plan_adoption(args.config_root)
        if args.as_json:
            print(json.dumps(plan.to_mapping(), ensure_ascii=False, indent=2))
        else:
            print(f"Status: {plan.status}")
            print(f"Safe to apply: {'yes' if plan.safe_to_apply else 'no'}")
            for change in plan.changes:
                print(f"{change.action.upper():6} {change.relative_path} — {change.reason}")
            if plan.combined_diff:
                print("\n" + plan.combined_diff, end="")
            for warning in plan.warnings:
                print(f"Warning: {warning}")
        return 0

    if args.command == "validate-adoption":
        result = validate_adoption(
            args.config_root,
            flake_target=args.flake_target,
            timeout=args.timeout,
        )
        if args.as_json:
            print(json.dumps(result.to_mapping(), ensure_ascii=False, indent=2))
        else:
            print(f"Status: {result.status}")
            print(f"Mode:   {result.configuration_mode}")
            if result.flake_target:
                print(f"Target: {result.flake_target}")
            for check in result.checks:
                duration = f"{check.duration_ms} ms"
                print(f"{check.status.upper():9} {check.name} ({duration})")
                if check.status != "passed":
                    if check.stdout:
                        print(check.stdout.rstrip())
                    if check.stderr:
                        print(check.stderr.rstrip(), file=sys.stderr)
            for warning in result.warnings:
                print(f"Warning: {warning}")
            print("Activation: disabled")
        return 0 if result.status == "passed" else 2

    if args.command == "serve":
        if not 1 <= args.port <= 65535:
            raise NcmError("Port must be between 1 and 65535")
        if args.validation_timeout < 1:
            raise NcmError("Validation timeout must be at least one second")
        if args.build_timeout < 1:
            raise NcmError("Build timeout must be at least one second")
        from .server import serve

        serve(
            state_path=args.state,
            user_state_path=args.user_state,
            output_path=args.output,
            config_root=args.config_root,
            home_manager_root=args.home_manager_root,
            port=args.port,
            open_browser=args.open_browser,
            flake_target=args.flake_target,
            validation_timeout=args.validation_timeout,
            build_timeout=args.build_timeout,
            helper_socket=args.helper_socket,
            helper_target_id=args.helper_target,
        )
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (NcmError, KeyboardInterrupt) as error:
        if isinstance(error, KeyboardInterrupt):
            print("\nStopped.", file=sys.stderr)
        else:
            print(f"Error: {error}", file=sys.stderr)
        return 1
