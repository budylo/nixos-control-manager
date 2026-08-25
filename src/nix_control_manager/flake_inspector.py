from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from importlib.resources import files
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from .system_inspector import inspect_system


Runner = Callable[..., subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]

_FLAKE_TARGET = re.compile(r"[A-Za-z0-9_-]+")
_MAX_LOCK_BYTES = 4_000_000
_MAX_NODES = 512
_MAX_TEXT = 512
_MAX_DIAGNOSTIC_CHARS = 4_000


@dataclass(frozen=True, slots=True)
class FlakeInput:
    name: str
    node: str | None
    follows: tuple[str, ...]
    locked: bool
    input_type: str
    source: str
    ref: str
    revision: str
    last_modified: int | None
    nar_hash: str

    def to_mapping(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "node": self.node,
            "follows": list(self.follows),
            "locked": self.locked,
            "type": self.input_type,
            "source": self.source,
            "ref": self.ref,
            "revision": self.revision,
            "lastModified": self.last_modified,
            "lastModifiedDate": (
                datetime.fromtimestamp(self.last_modified, timezone.utc)
                .date()
                .isoformat()
                if self.last_modified is not None
                else None
            ),
            "narHash": self.nar_hash,
        }


@dataclass(frozen=True, slots=True)
class FlakeInspection:
    status: str
    root: Path
    flake_path: Path
    lock_path: Path
    lock_status: str
    lock_version: int | None
    root_node: str | None
    inputs: tuple[FlakeInput, ...]
    nixos_configurations: tuple[str, ...]
    active_target: str | None
    active_target_status: str
    evaluation_status: str
    warnings: tuple[str, ...] = ()
    duration_ms: int = 0

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "status": self.status,
            "readOnly": True,
            "networkAccessEnabled": False,
            "lockWriteEnabled": False,
            "inputUpdateEnabled": False,
            "root": str(self.root),
            "files": {
                "flake": str(self.flake_path),
                "flakeExists": self.flake_path.is_file(),
                "lock": str(self.lock_path),
                "lockExists": self.lock_path.is_file(),
            },
            "lock": {
                "status": self.lock_status,
                "version": self.lock_version,
                "rootNode": self.root_node,
            },
            "inputs": [item.to_mapping() for item in self.inputs],
            "nixosConfigurations": list(self.nixos_configurations),
            "activeTarget": self.active_target,
            "activeTargetStatus": self.active_target_status,
            "evaluation": {
                "status": self.evaluation_status,
                "offline": True,
                "noWriteLockFile": True,
                "durationMs": self.duration_ms,
            },
            "warnings": list(self.warnings),
        }


def _bounded_text(value: Any) -> str:
    return value[:_MAX_TEXT] if isinstance(value, str) else ""


def _safe_url(value: Any) -> str:
    url = _bounded_text(value)
    if not url:
        return ""
    try:
        parsed = urlsplit(url)
        if not parsed.scheme or not parsed.netloc:
            return url.split("?", 1)[0].split("#", 1)[0]
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port is not None else ""
        return urlunsplit((parsed.scheme, host + port, parsed.path, "", ""))[:_MAX_TEXT]
    except (ValueError, UnicodeError):
        return ""


def _source_label(locked: dict[str, Any]) -> str:
    input_type = _bounded_text(locked.get("type"))
    owner = _bounded_text(locked.get("owner"))
    repo = _bounded_text(locked.get("repo"))
    if input_type in {"github", "gitlab"} and owner and repo:
        return f"{input_type}:{owner}/{repo}"[:_MAX_TEXT]
    if input_type == "path":
        path = _bounded_text(locked.get("path"))
        return f"path:{path}"[:_MAX_TEXT] if path else "path"
    url = _safe_url(locked.get("url"))
    return url or input_type or "unknown"


def _input_from_node(
    name: str, node_name: str, nodes: dict[str, Any], warnings: list[str]
) -> FlakeInput:
    raw = nodes.get(node_name)
    if not isinstance(raw, dict):
        warnings.append(f"Input {name} references missing lock node {node_name}.")
        return FlakeInput(name, node_name, (), False, "unknown", "", "", "", None, "")
    locked_raw = raw.get("locked")
    original_raw = raw.get("original")
    locked = locked_raw if isinstance(locked_raw, dict) else {}
    original = original_raw if isinstance(original_raw, dict) else {}
    last_modified_raw = locked.get("lastModified")
    last_modified = (
        last_modified_raw
        if type(last_modified_raw) is int and 0 <= last_modified_raw <= 4_102_444_800
        else None
    )
    input_type = _bounded_text(locked.get("type") or original.get("type")) or "unknown"
    ref = _bounded_text(original.get("ref") or locked.get("ref"))
    revision = _bounded_text(locked.get("rev"))
    nar_hash = _bounded_text(locked.get("narHash"))
    is_locked = bool(locked) and bool(revision or nar_hash or input_type == "path")
    if not is_locked:
        warnings.append(f"Input {name} has no complete locked source metadata.")
    return FlakeInput(
        name=name,
        node=node_name,
        follows=(),
        locked=is_locked,
        input_type=input_type,
        source=_source_label(locked or original),
        ref=ref,
        revision=revision,
        last_modified=last_modified,
        nar_hash=nar_hash,
    )


def parse_flake_lock(
    path: Path,
) -> tuple[str, int | None, str | None, tuple[FlakeInput, ...], list[str]]:
    """Parse a bounded lock file without evaluating or resolving any input."""
    warnings: list[str] = []
    if not path.is_file():
        return "missing", None, None, (), [
            "flake.lock is missing; offline output inspection was not attempted."
        ]
    try:
        if path.stat().st_size > _MAX_LOCK_BYTES:
            raise ValueError("flake.lock exceeds the read-only inspection limit")
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        return "invalid", None, None, (), [f"flake.lock cannot be read safely: {error}"]
    if not isinstance(raw, dict):
        return "invalid", None, None, (), ["flake.lock must be a JSON object."]
    nodes = raw.get("nodes")
    root_name = raw.get("root")
    version = raw.get("version")
    if (
        not isinstance(nodes, dict)
        or not isinstance(root_name, str)
        or root_name not in nodes
        or type(version) is not int
        or version < 1
        or len(nodes) > _MAX_NODES
    ):
        return "invalid", None, None, (), ["flake.lock has an invalid root, version, or node table."]
    root = nodes[root_name]
    root_inputs = root.get("inputs", {}) if isinstance(root, dict) else None
    if not isinstance(root_inputs, dict):
        return "invalid", None, None, (), ["flake.lock root inputs are invalid."]
    inputs: list[FlakeInput] = []
    for name, reference in sorted(root_inputs.items()):
        if not isinstance(name, str) or not name or len(name) > 128:
            warnings.append("flake.lock contains an invalid direct input name.")
            continue
        if isinstance(reference, str) and reference:
            inputs.append(_input_from_node(name, reference, nodes, warnings))
        elif (
            isinstance(reference, list)
            and reference
            and all(isinstance(part, str) and part for part in reference)
        ):
            inputs.append(FlakeInput(name, None, tuple(reference), False, "follows", "", "", "", None, ""))
        else:
            warnings.append(f"Input {name} has an invalid lock reference.")
    return ("attention" if warnings else "valid"), version, root_name, tuple(inputs), warnings


def _trim_diagnostic(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip()
    return value if len(value) <= _MAX_DIAGNOSTIC_CHARS else value[:_MAX_DIAGNOSTIC_CHARS] + "\n… diagnostic truncated …"


def _parse_evaluation(value: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not isinstance(value, dict) or set(value) != {"inputs", "nixosConfigurations"}:
        raise ValueError("Nix returned an invalid flake inspection document")
    parsed: list[tuple[str, ...]] = []
    for key in ("inputs", "nixosConfigurations"):
        raw = value[key]
        if (
            not isinstance(raw, list)
            or len(raw) > _MAX_NODES
            or any(not isinstance(item, str) or not item or len(item) > 128 for item in raw)
            or len(raw) != len(set(raw))
        ):
            raise ValueError(f"Nix returned invalid {key}")
        parsed.append(tuple(raw))
    return parsed[0], parsed[1]


def inspect_flake(
    config_root: Path = Path("/etc/nixos"),
    *,
    flake_target: str | None = None,
    timeout: int = 120,
    runner: Runner = subprocess.run,
    which: Which = shutil.which,
) -> FlakeInspection:
    started = time.monotonic()
    system = inspect_system(config_root)
    root = system.config_root
    flake_path = root / "flake.nix"
    lock_path = root / "flake.lock"
    raw_target = flake_target or system.hostname
    target = raw_target if isinstance(raw_target, str) and len(raw_target) <= 128 else None
    common = {
        "root": root,
        "flake_path": flake_path,
        "lock_path": lock_path,
        "nixos_configurations": (),
        "active_target": target or None,
        "duration_ms": 0,
    }
    if not flake_path.is_file():
        return FlakeInspection(
            status="absent", lock_status="not-applicable", lock_version=None,
            root_node=None, inputs=(), active_target_status="not-applicable",
            evaluation_status="not-run", warnings=("No flake.nix entrypoint was found.",),
            **common,
        )
    lock_status, lock_version, root_node, inputs, warnings = parse_flake_lock(lock_path)
    if lock_status in {"missing", "invalid"}:
        return FlakeInspection(
            status="incomplete" if lock_status == "missing" else "invalid",
            lock_status=lock_status, lock_version=lock_version, root_node=root_node,
            inputs=inputs, active_target_status="unverified", evaluation_status="not-run",
            warnings=tuple(warnings), **common,
        )
    if timeout < 1:
        warnings.append("Inspection timeout must be positive.")
        return FlakeInspection(
            status="detected", lock_status=lock_status, lock_version=lock_version,
            root_node=root_node, inputs=inputs, active_target_status="unverified",
            evaluation_status="blocked", warnings=tuple(warnings), **common,
        )
    if not target or not _FLAKE_TARGET.fullmatch(target):
        warnings.append("The configured nixosConfigurations target is not a safe attribute name.")
        target_status = "invalid"
    else:
        target_status = "unverified"
    nix = which("nix")
    if not nix:
        warnings.append("The nix command is unavailable; outputs were not evaluated.")
        return FlakeInspection(
            status="detected", lock_status=lock_status, lock_version=lock_version,
            root_node=root_node, inputs=inputs, active_target_status=target_status,
            evaluation_status="unavailable", warnings=tuple(warnings), **common,
        )
    expression = files("nix_control_manager").joinpath("data/inspect_flake.nix")
    command = (
        nix, "--extra-experimental-features", "nix-command flakes", "--offline",
        "eval", "--json", "--impure", "--no-write-lock-file", "--option",
        "allow-import-from-derivation", "false", "--file", str(expression),
    )
    environment = os.environ.copy()
    environment["NCM_INSPECT_CONFIG_ROOT"] = str(root)
    try:
        completed = runner(
            list(command), cwd=root, capture_output=True, text=True, timeout=timeout,
            check=False, env=environment,
        )
    except subprocess.TimeoutExpired:
        warnings.append(f"Offline flake inspection exceeded {timeout} seconds.")
        return FlakeInspection(
            status="detected", lock_status=lock_status, lock_version=lock_version,
            root_node=root_node, inputs=inputs, active_target_status=target_status,
            evaluation_status="timed-out", warnings=tuple(warnings),
            **{**common, "duration_ms": round((time.monotonic() - started) * 1000)},
        )
    except OSError as error:
        warnings.append(f"The Nix evaluator could not be started: {error}")
        return FlakeInspection(
            status="detected", lock_status=lock_status, lock_version=lock_version,
            root_node=root_node, inputs=inputs, active_target_status=target_status,
            evaluation_status="failed", warnings=tuple(warnings),
            **{**common, "duration_ms": round((time.monotonic() - started) * 1000)},
        )
    duration = round((time.monotonic() - started) * 1000)
    if completed.returncode != 0:
        diagnostic = _trim_diagnostic(completed.stderr or completed.stdout)
        warnings.append("Offline Nix evaluation failed." + (f"\n{diagnostic}" if diagnostic else ""))
        return FlakeInspection(
            status="detected", lock_status=lock_status, lock_version=lock_version,
            root_node=root_node, inputs=inputs, active_target_status=target_status,
            evaluation_status="failed", warnings=tuple(warnings),
            **{**common, "duration_ms": duration},
        )
    try:
        evaluated_inputs, configurations = _parse_evaluation(json.loads(completed.stdout))
    except (json.JSONDecodeError, ValueError) as error:
        warnings.append(str(error))
        return FlakeInspection(
            status="detected", lock_status=lock_status, lock_version=lock_version,
            root_node=root_node, inputs=inputs, active_target_status=target_status,
            evaluation_status="failed", warnings=tuple(warnings),
            **{**common, "duration_ms": duration},
        )
    locked_names = {item.name for item in inputs}
    evaluated_names = set(evaluated_inputs)
    if locked_names != evaluated_names:
        warnings.append("Evaluated direct inputs and flake.lock root inputs do not match exactly.")
    if target_status != "invalid":
        target_status = "selected" if target in configurations else "missing"
        if target_status == "missing":
            warnings.append(f"Active target {target!r} is not present in nixosConfigurations.")
    return FlakeInspection(
        status="detected", lock_status=lock_status, lock_version=lock_version,
        root_node=root_node, inputs=inputs, nixos_configurations=configurations,
        active_target=target or None, active_target_status=target_status,
        evaluation_status="passed", warnings=tuple(warnings), duration_ms=duration,
        root=root, flake_path=flake_path, lock_path=lock_path,
    )
