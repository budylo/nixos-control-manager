from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
import mimetypes
from pathlib import Path, PurePosixPath
import re
import secrets
import socket
import threading
import time
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit
import webbrowser

from .catalog import (
    load_catalog,
    load_catalog_guidance,
    load_presets,
    load_settings_catalog,
)
from .adoption import plan_adoption
from .candidate import validate_adoption
from .candidate_build import CandidateBuildManager, HomeManagerBuildManager
from .errors import NcmError, ValidationError
from .home_manager_adoption import (
    home_manager_plan_identity,
    plan_home_manager_adoption,
    validate_home_manager_adoption,
)
from .home_manager_generator import (
    build_home_preview,
    candidate_user_state,
    user_module_path,
)
from .home_manager_inspector import (
    HomeManagerInspection,
    inspect_home_manager,
    managed_user_state_path,
)
from .generation_inspector import GenerationInspection, inspect_generations
from .migration import load_migration_preview
from .managed_plan import managed_plan_identity, plan_managed_state
from .model import ManagedState
from .nix_generator import generate_module
from .package_compatibility import (
    PackageCompatibilityInspection,
    inspect_package_compatibility,
)
from .preview import build_preview
from .storage import load_state, save_generated_module, save_state
from .settings_inspector import EffectiveSettingsInspection, inspect_effective_settings
from .version import RELEASE_CHANNEL, RELEASE_VERSION
from .system_inspector import inspect_system
from .ui_helper import HelperUiAdapter, HelperUiError


MAX_REQUEST_BYTES = 1_000_000
_BUILD_JOB_PATH = re.compile(r"^/api/build-preview/([0-9a-f]{24})$")
_BUILD_CANCEL_PATH = re.compile(r"^/api/build-preview/([0-9a-f]{24})/cancel$")
_HOME_BUILD_JOB_PATH = re.compile(
    r"^/api/home-manager/build-preview/([0-9a-f]{24})$"
)
_HOME_BUILD_CANCEL_PATH = re.compile(
    r"^/api/home-manager/build-preview/([0-9a-f]{24})/cancel$"
)


def _load_ui_state(path: Path) -> ManagedState:
    """Load current or legacy state without modifying its source file."""
    if not path.exists():
        return ManagedState.empty()
    return load_migration_preview(path).state


class NcmServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        *,
        state_path: Path,
        user_state_path: Path | None = None,
        output_path: Path,
        config_root: Path,
        home_manager_root: Path | None = None,
        flake_target: str | None = None,
        validation_timeout: int = 120,
        helper_adapter: HelperUiAdapter | None = None,
        build_timeout: int = 3_600,
        build_manager: CandidateBuildManager | None = None,
        home_manager_build_manager: HomeManagerBuildManager | None = None,
        settings_inspector: Callable[
            ..., EffectiveSettingsInspection
        ] = inspect_effective_settings,
        compatibility_inspector: Callable[
            ..., PackageCompatibilityInspection
        ] = inspect_package_compatibility,
        home_manager_inspector: Callable[..., HomeManagerInspection] = inspect_home_manager,
        home_manager_planner: Callable[..., Any] = plan_home_manager_adoption,
        home_manager_validator: Callable[..., Any] = validate_home_manager_adoption,
        generation_inspector: Callable[..., GenerationInspection] = inspect_generations,
        local_write_enabled: bool = True,
    ) -> None:
        super().__init__(server_address, handler)
        self.state_path = state_path
        self.user_state_path = user_state_path or state_path.with_name("user-state.local.json")
        self.output_path = output_path
        self.config_root = config_root
        self.home_manager_root = home_manager_root or Path("~/.config/home-manager")
        self.flake_target = flake_target
        self.validation_timeout = validation_timeout
        self.settings_inspector = settings_inspector
        self.compatibility_inspector = compatibility_inspector
        self.home_manager_inspector = home_manager_inspector
        self.home_manager_planner = home_manager_planner
        self.home_manager_validator = home_manager_validator
        self.generation_inspector = generation_inspector
        self.local_write_enabled = local_write_enabled
        self.helper_adapter = helper_adapter
        self.build_manager = build_manager or CandidateBuildManager(
            config_root=config_root,
            flake_target=flake_target,
            timeout=build_timeout,
        )
        self.home_manager_build_manager = (
            home_manager_build_manager
            or HomeManagerBuildManager(
                config_root=config_root,
                standalone_root=self.home_manager_root,
                user_state_path=self.user_state_path,
                flake_target=flake_target,
                validation_timeout=validation_timeout,
                timeout=build_timeout,
                inspector=home_manager_inspector,
                planner=home_manager_planner,
                validator=home_manager_validator,
            )
        )
        self.token = secrets.token_urlsafe(32)
        self.home_manager_apply_intents: dict[str, dict[str, Any]] = {}
        self.home_manager_apply_intents_lock = threading.Lock()
        self.managed_apply_intents: dict[str, dict[str, Any]] = {}
        self.managed_apply_intents_lock = threading.Lock()

    def create_home_manager_apply_intent(
        self, result: dict[str, Any]
    ) -> tuple[str, int]:
        raw_ttl = result.get("expiresInSeconds")
        ttl = raw_ttl if isinstance(raw_ttl, int) and 1 <= raw_ttl <= 3600 else 300
        now = time.monotonic()
        intent_id = secrets.token_urlsafe(24)
        with self.home_manager_apply_intents_lock:
            self.home_manager_apply_intents = {
                key: value
                for key, value in self.home_manager_apply_intents.items()
                if value["expiresAt"] > now
            }
            if len(self.home_manager_apply_intents) >= 64:
                oldest = min(
                    self.home_manager_apply_intents,
                    key=lambda key: self.home_manager_apply_intents[key]["expiresAt"],
                )
                del self.home_manager_apply_intents[oldest]
            self.home_manager_apply_intents[intent_id] = {
                "expiresAt": now + ttl,
                "planFingerprint": result["planFingerprint"],
                "validationReceipt": result["validationReceipt"],
            }
        return intent_id, ttl

    def consume_home_manager_apply_intent(
        self, intent_id: str, plan_fingerprint: str
    ) -> dict[str, Any]:
        now = time.monotonic()
        with self.home_manager_apply_intents_lock:
            intent = self.home_manager_apply_intents.pop(intent_id, None)
        if intent is None or intent["expiresAt"] <= now:
            raise ValidationError(
                "Home Manager confirmation expired; validate the plan again"
            )
        if not secrets.compare_digest(intent["planFingerprint"], plan_fingerprint):
            raise ValidationError("Home Manager confirmation does not match the plan")
        return intent

    def create_managed_apply_intent(self, result: dict[str, Any]) -> tuple[str, int]:
        raw_ttl = result.get("expiresInSeconds")
        ttl = raw_ttl if isinstance(raw_ttl, int) and 1 <= raw_ttl <= 3600 else 300
        now = time.monotonic()
        intent_id = secrets.token_urlsafe(24)
        with self.managed_apply_intents_lock:
            self.managed_apply_intents = {
                key: value
                for key, value in self.managed_apply_intents.items()
                if value["expiresAt"] > now
            }
            if len(self.managed_apply_intents) >= 64:
                oldest = min(
                    self.managed_apply_intents,
                    key=lambda key: self.managed_apply_intents[key]["expiresAt"],
                )
                del self.managed_apply_intents[oldest]
            self.managed_apply_intents[intent_id] = {
                "expiresAt": now + ttl,
                "planFingerprint": result["planFingerprint"],
                "validationReceipt": result["validationReceipt"],
            }
        return intent_id, ttl

    def consume_managed_apply_intent(
        self, intent_id: str, plan_fingerprint: str
    ) -> dict[str, Any]:
        now = time.monotonic()
        with self.managed_apply_intents_lock:
            intent = self.managed_apply_intents.pop(intent_id, None)
        if intent is None or intent["expiresAt"] <= now:
            raise ValidationError("Managed confirmation expired; validate the state again")
        if not secrets.compare_digest(intent["planFingerprint"], plan_fingerprint):
            raise ValidationError("Managed confirmation does not match the plan")
        return intent

    def server_close(self) -> None:
        self.build_manager.close()
        self.home_manager_build_manager.close()
        super().server_close()


class RequestHandler(BaseHTTPRequestHandler):
    server: NcmServer

    def log_message(self, format: str, *args: object) -> None:
        print(f"[web] {self.address_string()} {format % args}")

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'")
        self.end_headers()
        self.wfile.write(content)

    def _error(self, error: Exception, status: HTTPStatus) -> None:
        self._json({"error": str(error)}, status)

    def _read_json_object(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0]
        if content_type != "application/json":
            raise ValidationError("Content-Type must be application/json")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValidationError("Content-Length is required")
        try:
            length = int(raw_length)
        except ValueError as error:
            raise ValidationError("Invalid Content-Length") from error
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise ValidationError("Request body is too large")
        try:
            raw = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValidationError("Request body is not valid JSON") from error
        if not isinstance(raw, dict):
            raise ValidationError("Request body must be a JSON object")
        return raw

    def _read_state(self) -> ManagedState:
        return ManagedState.from_mapping(self._read_json_object())

    def _home_candidate(self, *, include_fingerprint: bool = False):
        payload = self._read_json_object()
        required = {"username", "integration", "packages"}
        if include_fingerprint:
            required.add("planFingerprint")
        if set(payload) != required:
            raise ValidationError(
                "Home Manager candidate requires " + ", ".join(sorted(required))
            )
        username = payload["username"]
        integration = payload["integration"]
        packages = payload["packages"]
        if not isinstance(username, str) or not isinstance(integration, str):
            raise ValidationError("Home Manager user and integration must be strings")
        if not isinstance(packages, list):
            raise ValidationError("Home Manager packages must be a JSON array")
        inspection = self.server.home_manager_inspector(
            self.server.config_root,
            standalone_root=self.server.home_manager_root,
            user_state_path=self.server.user_state_path,
        )
        if not any(
            user.name == username and user.integration == integration
            for user in inspection.users
        ):
            raise ValidationError(
                "Home Manager candidate is limited to an exactly detected user integration"
            )
        if inspection.user_state.status == "invalid":
            raise ValidationError(
                "Invalid user-state must be repaired before creating a candidate"
            )
        previous = inspection.user_state.state.users.get(username)
        if previous is not None and previous.integration != integration:
            raise ValidationError(
                "Detected integration conflicts with the existing user-state profile"
            )
        state = candidate_user_state(
            inspection.user_state.state,
            username=username,
            integration=integration,
            packages=packages,
        )
        if include_fingerprint:
            fingerprint = payload["planFingerprint"]
            if not isinstance(fingerprint, str) or not re.fullmatch(
                r"[0-9a-f]{64}", fingerprint
            ):
                raise ValidationError(
                    "Home Manager build-preview requires a lowercase SHA-256 planFingerprint"
                )
            return inspection, state, username, integration, packages, fingerprint
        return inspection, state, username, integration, packages

    def _authorized(self) -> bool:
        return secrets.compare_digest(
            self.headers.get("X-NCM-Token", ""), self.server.token
        )

    def _build_cursor(self, query: str) -> int:
        parameters = parse_qs(query, keep_blank_values=True)
        if set(parameters) - {"after"}:
            raise ValidationError("Unknown build-preview query parameter")
        values = parameters.get("after", ["0"])
        if len(values) != 1:
            raise ValidationError("Build-preview cursor must be singular")
        try:
            cursor = int(values[0])
        except ValueError as error:
            raise ValidationError("Build-preview cursor must be an integer") from error
        if cursor < 0:
            raise ValidationError("Build-preview cursor cannot be negative")
        return cursor

    def do_GET(self) -> None:  # noqa: N802
        try:
            target = urlsplit(self.path)
            path = target.path
            build_match = _BUILD_JOB_PATH.fullmatch(path)
            home_build_match = _HOME_BUILD_JOB_PATH.fullmatch(path)
            if path == "/api/config":
                self._json(
                    {
                        "application": "nix-control-manager",
                        "apiVersion": 1,
                        "version": RELEASE_VERSION,
                        "releaseChannel": RELEASE_CHANNEL,
                        "token": self.server.token,
                        "localWriteEnabled": self.server.local_write_enabled,
                    }
                )
            elif path == "/api/state":
                self._json(_load_ui_state(self.server.state_path).to_mapping())
            elif path == "/api/catalog":
                self._json(load_catalog())
            elif path == "/api/catalog-guidance":
                self._json(load_catalog_guidance())
            elif path == "/api/catalog-compatibility":
                self._json(
                    self.server.compatibility_inspector(
                        self.server.config_root,
                        flake_target=self.server.flake_target,
                        timeout=self.server.validation_timeout,
                    ).to_mapping()
                )
            elif path == "/api/settings-catalog":
                self._json(load_settings_catalog())
            elif path == "/api/presets":
                self._json(load_presets())
            elif path == "/api/effective-settings":
                self._json(
                    self.server.settings_inspector(
                        self.server.config_root,
                        output_path=self.server.output_path,
                        flake_target=self.server.flake_target,
                        timeout=self.server.validation_timeout,
                    ).to_mapping()
                )
            elif path == "/api/home-manager":
                self._json(
                    self.server.home_manager_inspector(
                        self.server.config_root,
                        standalone_root=self.server.home_manager_root,
                        user_state_path=self.server.user_state_path,
                    ).to_mapping()
                )
            elif path == "/api/preview":
                state = _load_ui_state(self.server.state_path)
                self._json(build_preview(state, self.server.output_path))
            elif path == "/api/system":
                self._json(inspect_system(self.server.config_root).to_mapping())
            elif path == "/api/generations":
                self._json(self.server.generation_inspector().to_mapping())
            elif path == "/api/adoption":
                self._json(plan_adoption(self.server.config_root).to_mapping())
            elif path == "/api/helper":
                if self.server.helper_adapter is None:
                    self._json(
                        {
                            "available": False,
                            "readOnly": True,
                            "applyEnabled": False,
                            "recoveryEnabled": False,
                            "activationEnabled": False,
                            "dryActivatePreviewEnabled": False,
                            "testActivationEnabled": False,
                            "reason": "System helper is not configured",
                        }
                    )
                else:
                    self._json(self.server.helper_adapter.status())
            elif path == "/api/build-preview":
                self._json(
                    self.server.build_manager.latest(
                        after=self._build_cursor(target.query)
                    )
                )
            elif path == "/api/home-manager/build-preview":
                self._json(
                    self.server.home_manager_build_manager.latest(
                        after=self._build_cursor(target.query)
                    )
                )
            elif home_build_match:
                self._json(
                    self.server.home_manager_build_manager.poll(
                        home_build_match.group(1),
                        after=self._build_cursor(target.query),
                    )
                )
            elif build_match:
                self._json(
                    self.server.build_manager.poll(
                        build_match.group(1),
                        after=self._build_cursor(target.query),
                    )
                )
            else:
                self._serve_static()
        except NcmError as error:
            self._error(error, HTTPStatus.BAD_REQUEST)
        except Exception as error:  # defensive API boundary
            self._error(error, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._error(PermissionError("Invalid request token"), HTTPStatus.FORBIDDEN)
            return
        try:
            target = urlsplit(self.path)
            path = target.path
            cancel_match = _BUILD_CANCEL_PATH.fullmatch(path)
            home_cancel_match = _HOME_BUILD_CANCEL_PATH.fullmatch(path)
            if target.query:
                raise ValidationError("POST API endpoints do not accept query parameters")
            if path == "/api/save" and not self.server.local_write_enabled:
                raise ValidationError(
                    "Local state persistence is disabled in read-only mode"
                )
            if path == "/api/build-preview":
                self._json(self.server.build_manager.start(), HTTPStatus.ACCEPTED)
                return
            if path == "/api/home-manager/build-preview":
                (
                    _,
                    _,
                    username,
                    integration,
                    packages,
                    fingerprint,
                ) = self._home_candidate(include_fingerprint=True)
                self._json(
                    self.server.home_manager_build_manager.start(
                        username=username,
                        integration=integration,
                        packages=packages,
                        plan_fingerprint=fingerprint,
                    ),
                    HTTPStatus.ACCEPTED,
                )
                return
            if path == "/api/home-manager/preview":
                inspection, state, username, integration, _ = self._home_candidate()
                root = (
                    inspection.config_root
                    if integration == "nixos-module"
                    else inspection.standalone_root
                )
                self._json(
                    build_home_preview(
                        state,
                        username=username,
                        output_path=user_module_path(
                            managed_user_state_path(root), username
                        ),
                    )
                )
                return
            if path == "/api/helper/home-manager/validate":
                if self.server.helper_adapter is None:
                    raise HelperUiError("System helper is not configured")
                inspection, _, username, integration, packages = self._home_candidate()
                plan = self.server.home_manager_planner(
                    self.server.config_root,
                    standalone_root=self.server.home_manager_root,
                    user_state_path=self.server.user_state_path,
                    username=username,
                    integration=integration,
                    packages=packages,
                    inspection=inspection,
                )
                if plan.status != "ready" or not plan.safe_to_validate or not plan.changes:
                    raise ValidationError(
                        "A ready Home Manager source plan with changes is required"
                    )
                effective_target = self.server.flake_target
                if (
                    effective_target is None
                    and integration == "nixos-module"
                    and (plan.root / "flake.nix").is_file()
                ):
                    effective_target = socket.gethostname()
                fingerprint, _ = home_manager_plan_identity(plan, effective_target)
                result = self.server.helper_adapter.validate_home_manager(
                    username=username,
                    integration=integration,
                    packages=tuple(packages),
                    expected_plan_fingerprint=fingerprint,
                )
                intent_id, ttl = self.server.create_home_manager_apply_intent(result)
                public = {
                    key: value
                    for key, value in result.items()
                    if key != "validationReceipt"
                }
                self._json(
                    {
                        **public,
                        "intentId": intent_id,
                        "expiresInSeconds": ttl,
                        "confirmationRequired": True,
                    }
                )
                return
            if path == "/api/helper/managed/validate":
                if self.server.helper_adapter is None:
                    raise HelperUiError("System helper is not configured")
                state = self._read_state()
                plan = plan_managed_state(
                    self.server.config_root,
                    state,
                    flake_target=self.server.flake_target,
                )
                if not plan.changes:
                    raise ValidationError("The managed state has no changes to persist")
                expected_fingerprint, _ = managed_plan_identity(plan)
                result = self.server.helper_adapter.validate_managed(state)
                if result.get("planFingerprint") != expected_fingerprint:
                    raise HelperUiError("Managed helper validated a different plan")
                intent_id, ttl = self.server.create_managed_apply_intent(result)
                public = {
                    key: value
                    for key, value in result.items()
                    if key != "validationReceipt"
                }
                self._json(
                    {
                        **public,
                        "intentId": intent_id,
                        "expiresInSeconds": ttl,
                        "confirmationRequired": True,
                        "combinedDiff": plan.combined_diff,
                        "changes": [change.to_mapping() for change in plan.changes],
                    }
                )
                return
            if path == "/api/helper/managed/apply":
                if self.server.helper_adapter is None:
                    raise HelperUiError("System helper is not configured")
                payload = self._read_json_object()
                if set(payload) != {"intentId", "planFingerprint", "confirmed"}:
                    raise ValidationError(
                        "Managed apply requires intentId, planFingerprint, and confirmed"
                    )
                intent_id = payload.get("intentId")
                fingerprint = payload.get("planFingerprint")
                if (
                    not isinstance(intent_id, str)
                    or not 16 <= len(intent_id) <= 128
                    or not isinstance(fingerprint, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
                    or payload.get("confirmed") is not True
                ):
                    raise ValidationError(
                        "An exact, explicitly confirmed managed plan is required"
                    )
                intent = self.server.consume_managed_apply_intent(intent_id, fingerprint)
                self._json(
                    self.server.helper_adapter.apply_managed(
                        plan_fingerprint=fingerprint,
                        validation_receipt=intent["validationReceipt"],
                    )
                )
                return
            if path == "/api/helper/home-manager/apply":
                if self.server.helper_adapter is None:
                    raise HelperUiError("System helper is not configured")
                payload = self._read_json_object()
                if set(payload) != {"intentId", "planFingerprint", "confirmed"}:
                    raise ValidationError(
                        "Home Manager apply requires intentId, planFingerprint, and confirmed"
                    )
                intent_id = payload.get("intentId")
                fingerprint = payload.get("planFingerprint")
                if (
                    not isinstance(intent_id, str)
                    or not 16 <= len(intent_id) <= 128
                    or not isinstance(fingerprint, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
                    or payload.get("confirmed") is not True
                ):
                    raise ValidationError(
                        "An exact, explicitly confirmed Home Manager plan is required"
                    )
                intent = self.server.consume_home_manager_apply_intent(
                    intent_id, fingerprint
                )
                self._json(
                    self.server.helper_adapter.apply_home_manager(
                        plan_fingerprint=fingerprint,
                        validation_receipt=intent["validationReceipt"],
                    )
                )
                return
            if path in {
                "/api/home-manager/adoption-plan",
                "/api/home-manager/validate-adoption",
            }:
                inspection, _, username, integration, packages = self._home_candidate()
                plan = self.server.home_manager_planner(
                    self.server.config_root,
                    standalone_root=self.server.home_manager_root,
                    user_state_path=self.server.user_state_path,
                    username=username,
                    integration=integration,
                    packages=packages,
                    inspection=inspection,
                )
                if path == "/api/home-manager/adoption-plan":
                    self._json(plan.to_mapping())
                else:
                    self._json(
                        self.server.home_manager_validator(
                            plan,
                            flake_target=self.server.flake_target,
                            timeout=self.server.validation_timeout,
                        ).to_mapping()
                    )
                return
            if cancel_match:
                self._json(self.server.build_manager.cancel(cancel_match.group(1)))
                return
            if home_cancel_match:
                self._json(
                    self.server.home_manager_build_manager.cancel(
                        home_cancel_match.group(1)
                    )
                )
                return
            if path == "/api/validate-adoption":
                self._json(
                    validate_adoption(
                        self.server.config_root,
                        flake_target=self.server.flake_target,
                        timeout=self.server.validation_timeout,
                    ).to_mapping()
                )
                return
            if path == "/api/helper/validate-adoption":
                if self.server.helper_adapter is None:
                    raise HelperUiError("System helper is not configured")
                self._json(self.server.helper_adapter.validate_adoption())
                return
            if path == "/api/helper/activation-preview":
                if self.server.helper_adapter is None:
                    raise HelperUiError("System helper is not configured")
                build = self.server.build_manager.latest(after=0)
                outputs = build.get("outputPaths") or []
                fingerprint = build.get("planFingerprint")
                if (
                    build.get("status") != "passed"
                    or len(outputs) != 1
                    or not isinstance(fingerprint, str)
                ):
                    raise ValidationError(
                        "A successful single-output build preview is required"
                    )
                self._json(
                    self.server.helper_adapter.preview_activation(
                        system_path=outputs[0], plan_fingerprint=fingerprint
                    )
                )
                return
            if path == "/api/helper/test-activation":
                if self.server.helper_adapter is None:
                    raise HelperUiError("System helper is not configured")
                payload = self._read_json_object()
                if set(payload) != {"testReceipt"} or not isinstance(
                    payload.get("testReceipt"), str
                ):
                    raise ValidationError("A single testReceipt string is required")
                build = self.server.build_manager.latest(after=0)
                outputs = build.get("outputPaths") or []
                fingerprint = build.get("planFingerprint")
                if (
                    build.get("status") != "passed"
                    or len(outputs) != 1
                    or not isinstance(fingerprint, str)
                ):
                    raise ValidationError(
                        "A successful single-output build preview is required"
                    )
                self._json(
                    self.server.helper_adapter.test_activation(
                        system_path=outputs[0],
                        plan_fingerprint=fingerprint,
                        test_receipt=payload["testReceipt"],
                    )
                )
                return
            if path == "/api/helper/recover-test-activation":
                if self.server.helper_adapter is None:
                    raise HelperUiError("System helper is not configured")
                payload = self._read_json_object()
                if set(payload) != {"sessionId"} or not isinstance(
                    payload.get("sessionId"), str
                ):
                    raise ValidationError("A single sessionId string is required")
                self._json(
                    self.server.helper_adapter.recover_test_activation(
                        session_id=payload["sessionId"]
                    )
                )
                return
            if path == "/api/helper/commit-tested-system":
                if self.server.helper_adapter is None:
                    raise HelperUiError("System helper is not configured")
                payload = self._read_json_object()
                if (
                    set(payload) != {"sessionId", "confirmed"}
                    or payload.get("confirmed") is not True
                    or not isinstance(payload.get("sessionId"), str)
                    or not re.fullmatch(r"[0-9a-f]{24}", payload["sessionId"])
                ):
                    raise ValidationError(
                        "An exact sessionId and explicit confirmation are required"
                    )
                build = self.server.build_manager.latest(after=0)
                outputs = build.get("outputPaths") or []
                fingerprint = build.get("planFingerprint")
                if (
                    build.get("status") != "passed"
                    or len(outputs) != 1
                    or not isinstance(fingerprint, str)
                ):
                    raise ValidationError(
                        "A successful single-output build preview is required"
                    )
                self._json(
                    self.server.helper_adapter.commit_tested_system(
                        system_path=outputs[0],
                        plan_fingerprint=fingerprint,
                        session_id=payload["sessionId"],
                    ),
                    HTTPStatus.ACCEPTED,
                )
                return
            if path == "/api/helper/activation-session-status":
                if self.server.helper_adapter is None:
                    raise HelperUiError("System helper is not configured")
                payload = self._read_json_object()
                if (
                    set(payload) != {"sessionId"}
                    or not isinstance(payload.get("sessionId"), str)
                    or not re.fullmatch(r"[0-9a-f]{24}", payload["sessionId"])
                ):
                    raise ValidationError("A single exact sessionId is required")
                self._json(
                    self.server.helper_adapter.activation_session_status(
                        session_id=payload["sessionId"]
                    )
                )
                return
            if path == "/api/helper/rollback-committed-system":
                if self.server.helper_adapter is None:
                    raise HelperUiError("System helper is not configured")
                payload = self._read_json_object()
                if (
                    set(payload) != {"sessionId", "confirmed"}
                    or payload.get("confirmed") is not True
                    or not isinstance(payload.get("sessionId"), str)
                    or not re.fullmatch(r"[0-9a-f]{24}", payload["sessionId"])
                ):
                    raise ValidationError(
                        "An exact committed sessionId and explicit confirmation are required"
                    )
                self._json(
                    self.server.helper_adapter.rollback_committed_system(
                        session_id=payload["sessionId"]
                    ),
                    HTTPStatus.ACCEPTED,
                )
                return
            state = self._read_state()
            if path == "/api/preview":
                self._json(build_preview(state, self.server.output_path))
            elif path == "/api/save":
                preview = build_preview(state, self.server.output_path)
                save_generated_module(self.server.output_path, preview["generated"])
                save_state(self.server.state_path, state)
                self._json(
                    {
                        **preview,
                        "saved": True,
                        "statePath": str(self.server.state_path),
                        "outputPath": str(self.server.output_path),
                    }
                )
            else:
                self._error(FileNotFoundError("Unknown API endpoint"), HTTPStatus.NOT_FOUND)
        except (NcmError, ValueError) as error:
            status = (
                HTTPStatus.SERVICE_UNAVAILABLE
                if isinstance(error, HelperUiError)
                else HTTPStatus.BAD_REQUEST
            )
            self._error(error, status)
        except Exception as error:  # defensive API boundary
            self._error(error, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _serve_static(self) -> None:
        request_path = self.path.split("?", 1)[0]
        relative = "index.html" if request_path == "/" else request_path.lstrip("/")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or len(pure.parts) != 1:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        resource = files("nix_control_manager").joinpath("web", pure.name)
        try:
            content = resource.read_bytes()
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        mime_type = mimetypes.guess_type(pure.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:",
        )
        self.end_headers()
        self.wfile.write(content)


def serve(
    *,
    state_path: Path,
    user_state_path: Path,
    output_path: Path,
    config_root: Path,
    home_manager_root: Path,
    port: int,
    open_browser: bool,
    flake_target: str | None = None,
    validation_timeout: int = 120,
    build_timeout: int = 3_600,
    helper_socket: Path | None = None,
    helper_target_id: str = "live",
    local_write_enabled: bool = True,
) -> None:
    helper_adapter = (
        HelperUiAdapter(
            socket_path=helper_socket,
            target_id=helper_target_id,
            config_root=config_root,
            flake_target=flake_target,
            timeout=validation_timeout,
        )
        if helper_socket is not None
        else None
    )
    server = NcmServer(
        ("127.0.0.1", port),
        RequestHandler,
        state_path=state_path,
        user_state_path=user_state_path,
        output_path=output_path,
        config_root=config_root,
        home_manager_root=home_manager_root,
        flake_target=flake_target,
        validation_timeout=validation_timeout,
        helper_adapter=helper_adapter,
        build_timeout=build_timeout,
        local_write_enabled=local_write_enabled,
    )
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Nix Control Manager is available at {url}")
    print(f"State:  {state_path}")
    print(f"User state: {user_state_path} (read-only foundation)")
    print(f"Module: {output_path}")
    print(f"Target: {config_root} (read-only inspection)")
    print(
        f"Home Manager: {home_manager_root} "
        "(inspection; source persistence is helper capability-gated)"
    )
    print("Validation: disposable candidate only")
    print("Build preview: unprivileged Nix store build; permanent switch disabled")
    print(
        "Local persistence: "
        + ("enabled" if local_write_enabled else "disabled (read-only mode)")
    )
    print(
        f"System helper: {helper_socket} "
        f"(target {helper_target_id}, capability-gated)"
        if helper_socket is not None
        else "System helper: disabled"
    )
    print("Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.2, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
