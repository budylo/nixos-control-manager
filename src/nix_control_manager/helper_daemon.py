from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import signal
import sys
import threading
from typing import Any, Mapping

from .errors import TransactionError
from .fixture_helper_backend import FixtureWorkflowHelperBackend
from .helper_service import HelperDispatcher, HelperTarget
from .helper_transport import UnixJsonHelperServer
from .live_read_only_backend import LiveReadOnlyHelperBackend, RoutingHelperBackend
from .managed_helper_backend import LiveManagedHelperBackend
from .polkit_authorizer import PolkitAuthorizer
from .transaction import require_transaction_fixture


class HelperConfigurationError(ValueError):
    pass


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HelperConfigurationError(f"{label} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    unknown = set(value) - expected
    missing = expected - set(value)
    if unknown or missing:
        raise HelperConfigurationError(
            f"{label} fields do not match the versioned schema"
        )


def _absolute_path(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise HelperConfigurationError(f"{label} must be a non-empty path string")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise HelperConfigurationError(f"{label} must be absolute")
    return path.resolve()


def _allowed_paths(raw: Any) -> frozenset[str]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= 16:
        raise HelperConfigurationError(
            "allowedRelativePaths must contain between 1 and 16 paths"
        )
    allowed: set[str] = set()
    for value in raw:
        if not isinstance(value, str):
            raise HelperConfigurationError("Allowed paths must be strings")
        relative = PurePosixPath(value)
        if (
            relative.is_absolute()
            or not relative.parts
            or any(part in {"", ".", ".."} for part in relative.parts)
            or str(relative) != value
        ):
            raise HelperConfigurationError(f"Unsafe allowed path: {value}")
        allowed.add(value)
    if len(allowed) != len(raw):
        raise HelperConfigurationError("Duplicate allowed paths are not permitted")
    return frozenset(allowed)


def _flake_target(value: Any) -> str | None:
    if value is not None and not isinstance(value, str):
        raise HelperConfigurationError("flakeTarget must be a string or null")
    return value


def _target_v1(raw: Any) -> HelperTarget:
    mapping = _mapping(raw, "target")
    _exact_keys(
        mapping,
        {
            "targetId",
            "configurationRoot",
            "journalRoot",
            "allowedRelativePaths",
            "fixtureOnly",
            "flakeTarget",
        },
        "target",
    )
    if mapping["fixtureOnly"] is not True:
        raise HelperConfigurationError(
            "This helper build accepts fixtureOnly targets exclusively"
        )
    allowed = _allowed_paths(mapping["allowedRelativePaths"])
    config_root = _absolute_path(mapping["configurationRoot"], "configurationRoot")
    journal_root = _absolute_path(mapping["journalRoot"], "journalRoot")
    if journal_root == config_root or journal_root.is_relative_to(config_root):
        raise HelperConfigurationError(
            "journalRoot must be outside configurationRoot"
        )
    flake_target = _flake_target(mapping["flakeTarget"])
    try:
        require_transaction_fixture(config_root)
        return HelperTarget(
            target_id=mapping["targetId"],
            configuration_root=config_root,
            journal_root=journal_root,
            allowed_relative_paths=frozenset(allowed),
            fixture_only=True,
            apply_enabled=True,
            flake_target=flake_target,
        )
    except (TransactionError, TypeError, ValueError) as error:
        raise HelperConfigurationError(str(error)) from error


def _target_v2(raw: Any) -> HelperTarget:
    mapping = _mapping(raw, "target")
    _exact_keys(
        mapping,
        {
            "targetId",
            "mode",
            "configurationRoot",
            "journalRoot",
            "allowedRelativePaths",
            "flakeTarget",
        },
        "target",
    )
    mode = mapping["mode"]
    if mode not in {"fixture", "live-read-only"}:
        raise HelperConfigurationError(
            "target mode must be fixture or live-read-only"
        )
    config_root = _absolute_path(mapping["configurationRoot"], "configurationRoot")
    allowed = _allowed_paths(mapping["allowedRelativePaths"])
    flake_target = _flake_target(mapping["flakeTarget"])
    try:
        if mode == "fixture":
            journal_root = _absolute_path(mapping["journalRoot"], "journalRoot")
            if journal_root == config_root or journal_root.is_relative_to(config_root):
                raise HelperConfigurationError(
                    "journalRoot must be outside configurationRoot"
                )
            require_transaction_fixture(config_root)
            return HelperTarget(
                target_id=mapping["targetId"],
                configuration_root=config_root,
                journal_root=journal_root,
                allowed_relative_paths=allowed,
                fixture_only=True,
                apply_enabled=True,
                flake_target=flake_target,
            )
        if mapping["journalRoot"] is not None:
            raise HelperConfigurationError(
                "live-read-only targets must set journalRoot to null"
            )
        return HelperTarget(
            target_id=mapping["targetId"],
            configuration_root=config_root,
            journal_root=None,
            allowed_relative_paths=allowed,
            fixture_only=False,
            apply_enabled=False,
            flake_target=flake_target,
        )
    except (TransactionError, TypeError, ValueError) as error:
        raise HelperConfigurationError(str(error)) from error


def _target_v3(raw: Any) -> HelperTarget:
    mapping = _mapping(raw, "target")
    _exact_keys(
        mapping,
        {
            "targetId",
            "mode",
            "configurationRoot",
            "journalRoot",
            "testJournalRoot",
            "testTimeoutSeconds",
            "allowedRelativePaths",
            "flakeTarget",
        },
        "target",
    )
    mode = mapping["mode"]
    if mode not in {"fixture", "live-read-only", "live-test"}:
        raise HelperConfigurationError(
            "target mode must be fixture, live-read-only, or live-test"
        )
    config_root = _absolute_path(mapping["configurationRoot"], "configurationRoot")
    allowed = _allowed_paths(mapping["allowedRelativePaths"])
    flake_target = _flake_target(mapping["flakeTarget"])
    timeout = mapping["testTimeoutSeconds"]
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 30 <= timeout <= 1800:
        raise HelperConfigurationError("testTimeoutSeconds must be between 30 and 1800")
    try:
        if mode == "fixture":
            journal_root = _absolute_path(mapping["journalRoot"], "journalRoot")
            if mapping["testJournalRoot"] is not None:
                raise HelperConfigurationError("fixture targets cannot set testJournalRoot")
            if journal_root == config_root or journal_root.is_relative_to(config_root):
                raise HelperConfigurationError("journalRoot must be outside configurationRoot")
            require_transaction_fixture(config_root)
            return HelperTarget(
                target_id=mapping["targetId"],
                configuration_root=config_root,
                journal_root=journal_root,
                allowed_relative_paths=allowed,
                fixture_only=True,
                apply_enabled=True,
                flake_target=flake_target,
                test_timeout_seconds=timeout,
            )
        if mapping["journalRoot"] is not None:
            raise HelperConfigurationError("live targets must set journalRoot to null")
        test_enabled = mode == "live-test"
        if test_enabled:
            test_journal = _absolute_path(mapping["testJournalRoot"], "testJournalRoot")
            if test_journal == config_root or test_journal.is_relative_to(config_root):
                raise HelperConfigurationError(
                    "testJournalRoot must be outside configurationRoot"
                )
        else:
            if mapping["testJournalRoot"] is not None:
                raise HelperConfigurationError(
                    "live-read-only targets must set testJournalRoot to null"
                )
            test_journal = None
        return HelperTarget(
            target_id=mapping["targetId"],
            configuration_root=config_root,
            journal_root=None,
            allowed_relative_paths=allowed,
            fixture_only=False,
            apply_enabled=False,
            flake_target=flake_target,
            test_activation_enabled=test_enabled,
            test_journal_root=test_journal,
            test_timeout_seconds=timeout,
        )
    except (TransactionError, TypeError, ValueError) as error:
        raise HelperConfigurationError(str(error)) from error


def _target_v4(raw: Any) -> HelperTarget:
    mapping = _mapping(raw, "target")
    _exact_keys(
        mapping,
        {
            "targetId",
            "mode",
            "configurationRoot",
            "journalRoot",
            "testJournalRoot",
            "testTimeoutSeconds",
            "homeManagerRoot",
            "homeManagerJournalRoot",
            "allowedRelativePaths",
            "flakeTarget",
        },
        "target",
    )
    mode = mapping["mode"]
    if mode not in {
        "fixture",
        "live-read-only",
        "live-test",
        "live-home-manager",
    }:
        raise HelperConfigurationError(
            "target mode must be fixture, live-read-only, live-test, or "
            "live-home-manager"
        )
    base = {
        key: mapping[key]
        for key in (
            "targetId",
            "mode",
            "configurationRoot",
            "journalRoot",
            "testJournalRoot",
            "testTimeoutSeconds",
            "allowedRelativePaths",
            "flakeTarget",
        )
    }
    if mode != "live-home-manager":
        if (
            mapping["homeManagerRoot"] is not None
            or mapping["homeManagerJournalRoot"] is not None
        ):
            raise HelperConfigurationError(
                "Only live-home-manager targets may configure Home Manager paths"
            )
        return _target_v3(base)

    if mapping["journalRoot"] is not None or mapping["testJournalRoot"] is not None:
        raise HelperConfigurationError(
            "live-home-manager targets must disable system and test journals"
        )
    timeout = mapping["testTimeoutSeconds"]
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, int)
        or not 30 <= timeout <= 1800
    ):
        raise HelperConfigurationError("testTimeoutSeconds must be between 30 and 1800")
    config_root = _absolute_path(mapping["configurationRoot"], "configurationRoot")
    home_root = _absolute_path(mapping["homeManagerRoot"], "homeManagerRoot")
    raw_home_root = Path(mapping["homeManagerRoot"]).expanduser()
    if raw_home_root.is_symlink():
        raise HelperConfigurationError("homeManagerRoot cannot be a symbolic link")
    home_journal = _absolute_path(
        mapping["homeManagerJournalRoot"], "homeManagerJournalRoot"
    )
    raw_home_journal = Path(mapping["homeManagerJournalRoot"]).expanduser()
    if raw_home_journal.is_symlink():
        raise HelperConfigurationError(
            "homeManagerJournalRoot cannot be a symbolic link"
        )
    if home_root == Path("/") or home_root.is_relative_to(Path("/nix/store")):
        raise HelperConfigurationError("homeManagerRoot is unsafe")
    if home_journal == home_root or home_journal.is_relative_to(home_root):
        raise HelperConfigurationError(
            "homeManagerJournalRoot must be outside homeManagerRoot"
        )
    try:
        return HelperTarget(
            target_id=mapping["targetId"],
            configuration_root=config_root,
            journal_root=None,
            allowed_relative_paths=_allowed_paths(mapping["allowedRelativePaths"]),
            fixture_only=False,
            apply_enabled=False,
            flake_target=_flake_target(mapping["flakeTarget"]),
            test_timeout_seconds=timeout,
            home_manager_apply_enabled=True,
            home_manager_root=home_root,
            home_manager_journal_root=home_journal,
        )
    except (TypeError, ValueError) as error:
        raise HelperConfigurationError(str(error)) from error


def _target_v5(raw: Any) -> HelperTarget:
    mapping = _mapping(raw, "target")
    _exact_keys(
        mapping,
        {
            "targetId",
            "mode",
            "configurationRoot",
            "journalRoot",
            "testJournalRoot",
            "testTimeoutSeconds",
            "homeManagerRoot",
            "homeManagerJournalRoot",
            "managedJournalRoot",
            "allowedRelativePaths",
            "flakeTarget",
        },
        "target",
    )
    if mapping["mode"] != "live-managed":
        base = {key: value for key, value in mapping.items() if key != "managedJournalRoot"}
        if mapping["managedJournalRoot"] is not None:
            raise HelperConfigurationError(
                "Only live-managed targets may configure managedJournalRoot"
            )
        return _target_v4(base)
    if any(
        mapping[key] is not None
        for key in (
            "journalRoot",
            "testJournalRoot",
            "homeManagerRoot",
            "homeManagerJournalRoot",
        )
    ):
        raise HelperConfigurationError(
            "live-managed must disable fixture, test, and Home Manager journals"
        )
    root = _absolute_path(mapping["configurationRoot"], "configurationRoot")
    normalized = str(root).replace("\\", "/")
    if root.as_posix() != "/etc/nixos" and not normalized.endswith("/etc/nixos"):
        raise HelperConfigurationError("live-managed is restricted to /etc/nixos")
    journal = _absolute_path(mapping["managedJournalRoot"], "managedJournalRoot")
    if journal == root or journal.is_relative_to(root):
        raise HelperConfigurationError(
            "managedJournalRoot must be outside configurationRoot"
        )
    allowed = _allowed_paths(mapping["allowedRelativePaths"])
    if allowed != frozenset({"ncm/state.json", "ncm/packages.nix"}):
        raise HelperConfigurationError(
            "live-managed requires the exact NCM-owned two-file allow-list"
        )
    timeout = mapping["testTimeoutSeconds"]
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 30 <= timeout <= 1800:
        raise HelperConfigurationError("testTimeoutSeconds must be between 30 and 1800")
    try:
        return HelperTarget(
            target_id=mapping["targetId"],
            configuration_root=root,
            journal_root=None,
            allowed_relative_paths=allowed,
            fixture_only=False,
            apply_enabled=False,
            flake_target=_flake_target(mapping["flakeTarget"]),
            test_timeout_seconds=timeout,
            managed_write_enabled=True,
            managed_journal_root=journal,
        )
    except (TypeError, ValueError) as error:
        raise HelperConfigurationError(str(error)) from error


def _target_v6(raw: Any) -> HelperTarget:
    mapping = _mapping(raw, "target")
    if mapping.get("mode") != "live-control":
        return _target_v5(raw)
    _exact_keys(
        mapping,
        {
            "targetId",
            "mode",
            "configurationRoot",
            "journalRoot",
            "testJournalRoot",
            "testTimeoutSeconds",
            "homeManagerRoot",
            "homeManagerJournalRoot",
            "managedJournalRoot",
            "allowedRelativePaths",
            "flakeTarget",
        },
        "target",
    )
    if any(
        mapping[key] is not None
        for key in ("journalRoot", "homeManagerRoot", "homeManagerJournalRoot")
    ):
        raise HelperConfigurationError(
            "live-control must disable fixture and Home Manager journals"
        )
    root = _absolute_path(mapping["configurationRoot"], "configurationRoot")
    normalized = str(root).replace("\\", "/")
    if root.as_posix() != "/etc/nixos" and not normalized.endswith("/etc/nixos"):
        raise HelperConfigurationError("live-control is restricted to /etc/nixos")
    test_journal = _absolute_path(mapping["testJournalRoot"], "testJournalRoot")
    managed_journal = _absolute_path(
        mapping["managedJournalRoot"], "managedJournalRoot"
    )
    for label, path in (
        ("testJournalRoot", test_journal),
        ("managedJournalRoot", managed_journal),
    ):
        if path == root or path.is_relative_to(root):
            raise HelperConfigurationError(f"{label} must be outside configurationRoot")
    if test_journal == managed_journal:
        raise HelperConfigurationError("live-control journals must be separate")
    allowed = _allowed_paths(mapping["allowedRelativePaths"])
    if allowed != frozenset({"ncm/state.json", "ncm/packages.nix"}):
        raise HelperConfigurationError(
            "live-control requires the exact NCM-owned two-file allow-list"
        )
    timeout = mapping["testTimeoutSeconds"]
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 30 <= timeout <= 1800:
        raise HelperConfigurationError("testTimeoutSeconds must be between 30 and 1800")
    try:
        return HelperTarget(
            target_id=mapping["targetId"],
            configuration_root=root,
            journal_root=None,
            allowed_relative_paths=allowed,
            fixture_only=False,
            apply_enabled=False,
            flake_target=_flake_target(mapping["flakeTarget"]),
            test_activation_enabled=True,
            test_journal_root=test_journal,
            test_timeout_seconds=timeout,
            managed_write_enabled=True,
            managed_journal_root=managed_journal,
            permanent_switch_enabled=True,
        )
    except (TypeError, ValueError) as error:
        raise HelperConfigurationError(str(error)) from error


@dataclass(frozen=True, slots=True)
class HelperDaemonConfig:
    socket_path: Path
    polkit_executable: Path
    validation_timeout: int
    targets: tuple[HelperTarget, ...]

    @classmethod
    def load(cls, path: Path) -> "HelperDaemonConfig":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise HelperConfigurationError(f"Could not read helper configuration: {error}") from error
        mapping = _mapping(raw, "helper configuration")
        _exact_keys(
            mapping,
            {
                "schemaVersion",
                "socketPath",
                "polkitExecutable",
                "validationTimeout",
                "targets",
            },
            "helper configuration",
        )
        schema_version = mapping["schemaVersion"]
        if schema_version not in {1, 2, 3, 4, 5, 6}:
            raise HelperConfigurationError(
                "Only helper configuration schemaVersion 1 through 6 are supported"
            )
        timeout = mapping["validationTimeout"]
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 900:
            raise HelperConfigurationError("validationTimeout must be between 1 and 900")
        targets_raw = mapping["targets"]
        if not isinstance(targets_raw, list) or not 1 <= len(targets_raw) <= 8:
            raise HelperConfigurationError("targets must contain between 1 and 8 entries")
        target_loader = {
            1: _target_v1,
            2: _target_v2,
            3: _target_v3,
            4: _target_v4,
            5: _target_v5,
            6: _target_v6,
        }[schema_version]
        targets = tuple(target_loader(item) for item in targets_raw)
        if len({target.target_id for target in targets}) != len(targets):
            raise HelperConfigurationError("Duplicate target identifiers are not permitted")
        return cls(
            socket_path=_absolute_path(mapping["socketPath"], "socketPath"),
            polkit_executable=_absolute_path(
                mapping["polkitExecutable"], "polkitExecutable"
            ),
            validation_timeout=timeout,
            targets=targets,
        )


def run_daemon(config_path: Path) -> None:
    if os.name != "posix" or not hasattr(os, "geteuid") or os.geteuid() != 0:
        raise HelperConfigurationError("The system helper must run as root on Linux")
    config = HelperDaemonConfig.load(config_path)
    dispatcher = HelperDispatcher(
        targets=config.targets,
        authorizer=PolkitAuthorizer(config.polkit_executable),
        backend=RoutingHelperBackend(
            fixture_backend=FixtureWorkflowHelperBackend(
                timeout=config.validation_timeout
            ),
            live_backend=LiveReadOnlyHelperBackend(
                timeout=config.validation_timeout
            ),
            managed_backend=LiveManagedHelperBackend(
                timeout=config.validation_timeout
            ),
        ),
    )
    stop = threading.Event()

    def request_stop(signum: int, frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    with UnixJsonHelperServer.from_systemd(config.socket_path, dispatcher) as server:
        server.serve_until(stop)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ncm-helper")
    parser.add_argument("--config", required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        run_daemon(arguments.config)
    except (HelperConfigurationError, RuntimeError, ValueError) as error:
        print(f"ncm-helper: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
