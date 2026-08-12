from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
import mimetypes
from pathlib import Path, PurePosixPath
import re
import secrets
import threading
from typing import Any
from urllib.parse import parse_qs, urlsplit
import webbrowser

from .catalog import load_catalog
from .adoption import plan_adoption
from .candidate import validate_adoption
from .candidate_build import CandidateBuildManager
from .errors import NcmError, ValidationError
from .model import ManagedState
from .nix_generator import generate_module
from .preview import build_preview
from .storage import load_state, save_generated_module, save_state
from .system_inspector import inspect_system
from .ui_helper import HelperUiAdapter, HelperUiError


MAX_REQUEST_BYTES = 1_000_000
_BUILD_JOB_PATH = re.compile(r"^/api/build-preview/([0-9a-f]{24})$")
_BUILD_CANCEL_PATH = re.compile(r"^/api/build-preview/([0-9a-f]{24})/cancel$")


class NcmServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        *,
        state_path: Path,
        output_path: Path,
        config_root: Path,
        flake_target: str | None = None,
        validation_timeout: int = 120,
        helper_adapter: HelperUiAdapter | None = None,
        build_timeout: int = 3_600,
        build_manager: CandidateBuildManager | None = None,
    ) -> None:
        super().__init__(server_address, handler)
        self.state_path = state_path
        self.output_path = output_path
        self.config_root = config_root
        self.flake_target = flake_target
        self.validation_timeout = validation_timeout
        self.helper_adapter = helper_adapter
        self.build_manager = build_manager or CandidateBuildManager(
            config_root=config_root,
            flake_target=flake_target,
            timeout=build_timeout,
        )
        self.token = secrets.token_urlsafe(32)

    def server_close(self) -> None:
        self.build_manager.close()
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
            if path == "/api/config":
                self._json({"token": self.server.token})
            elif path == "/api/state":
                self._json(load_state(self.server.state_path).to_mapping())
            elif path == "/api/catalog":
                self._json(load_catalog())
            elif path == "/api/preview":
                state = load_state(self.server.state_path)
                self._json(build_preview(state, self.server.output_path))
            elif path == "/api/system":
                self._json(inspect_system(self.server.config_root).to_mapping())
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
            if target.query:
                raise ValidationError("POST API endpoints do not accept query parameters")
            if path == "/api/build-preview":
                self._json(self.server.build_manager.start(), HTTPStatus.ACCEPTED)
                return
            if cancel_match:
                self._json(self.server.build_manager.cancel(cancel_match.group(1)))
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
    output_path: Path,
    config_root: Path,
    port: int,
    open_browser: bool,
    flake_target: str | None = None,
    validation_timeout: int = 120,
    build_timeout: int = 3_600,
    helper_socket: Path | None = None,
    helper_target_id: str = "live",
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
        output_path=output_path,
        config_root=config_root,
        flake_target=flake_target,
        validation_timeout=validation_timeout,
        helper_adapter=helper_adapter,
        build_timeout=build_timeout,
    )
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Nix Control Manager is available at {url}")
    print(f"State:  {state_path}")
    print(f"Module: {output_path}")
    print(f"Target: {config_root} (read-only inspection)")
    print("Validation: disposable candidate only")
    print("Build preview: unprivileged Nix store build; permanent switch disabled")
    print(
        f"System helper: {helper_socket} (target {helper_target_id}, read-only)"
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
