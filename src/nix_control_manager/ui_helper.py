from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import secrets
from typing import Any, Callable, Mapping

from .errors import NcmError
from .helper_client import (
    build_activation_preview_request,
    build_test_activation_request,
    build_test_recovery_request,
    build_validate_request,
)
from .helper_transport import send_unix_request


Sender = Callable[..., dict[str, Any]]
_TARGET_ID = re.compile(r"^[a-z][a-z0-9-]{0,31}$")


class HelperUiError(NcmError):
    """A system-helper failure safe to show in the local UI."""


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HelperUiError(f"System helper returned an invalid {label}")
    return value


@dataclass(frozen=True, slots=True)
class HelperUiAdapter:
    socket_path: Path
    target_id: str
    config_root: Path
    flake_target: str | None = None
    timeout: float = 180.0
    sender: Sender = send_unix_request

    def __post_init__(self) -> None:
        if not _TARGET_ID.fullmatch(self.target_id):
            raise ValueError("helper target identifier has an invalid format")
        if self.timeout <= 0 or self.timeout > 900:
            raise ValueError("helper timeout must be between 0 and 900 seconds")
        object.__setattr__(self, "socket_path", self.socket_path.expanduser().resolve())
        object.__setattr__(self, "config_root", self.config_root.expanduser().resolve())

    @staticmethod
    def _request(operation: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "requestId": f"ui-{secrets.token_hex(8)}",
            "operation": operation,
            "payload": dict(payload),
        }

    def _send(self, request: dict[str, Any]) -> dict[str, Any]:
        response = self.sender(self.socket_path, request, timeout=self.timeout)
        result = dict(_mapping(response, "response"))
        if result.get("schemaVersion") != 1:
            raise HelperUiError("System helper uses an unsupported protocol version")
        if result.get("requestId") != request["requestId"]:
            raise HelperUiError("System helper response does not match the request")
        return result

    def status(self) -> dict[str, Any]:
        base = {
            "available": False,
            "socketPath": str(self.socket_path),
            "targetId": self.target_id,
            "readOnly": True,
            "applyEnabled": False,
            "recoveryEnabled": False,
            "activationEnabled": False,
            "dryActivatePreviewEnabled": False,
            "testActivationEnabled": False,
        }
        try:
            response = self._send(self._request("capabilities", {}))
            if response.get("status") != "ok":
                error = _mapping(response.get("error"), "error")
                return {**base, "reason": str(error.get("message") or "Helper rejected capabilities")}
            result = _mapping(response.get("result"), "capabilities")
            targets = result.get("targets")
            if not isinstance(targets, list):
                raise HelperUiError("System helper returned an invalid target list")
            target = next(
                (
                    item
                    for item in targets
                    if isinstance(item, Mapping)
                    and item.get("targetId") == self.target_id
                ),
                None,
            )
            if target is None:
                return {**base, "reason": "Configured live target is not advertised by the helper"}
            safe = (
                target.get("liveTarget") is True
                and target.get("readOnly") is True
                and target.get("applyEnabled") is False
                and target.get("recoveryEnabled") is False
                and result.get("activationEnabled") is False
                and result.get("arbitraryCommandsAccepted") is False
                and result.get("protocolVersion") == 1
            )
            if not safe:
                return {**base, "reason": "Helper target does not satisfy the read-only UI boundary"}
            return {
                **base,
                "available": True,
                "protocolVersion": result.get("protocolVersion"),
                "allowedRelativePaths": list(target.get("allowedRelativePaths") or []),
                "dryActivatePreviewEnabled": (
                    target.get("dryActivatePreviewEnabled") is True
                    and "preview-activation" in (result.get("operations") or [])
                ),
                "testActivationEnabled": (
                    target.get("testActivationEnabled") is True
                    and "test-activation" in (result.get("operations") or [])
                    and "recover-test-activation" in (result.get("operations") or [])
                ),
                "reason": None,
            }
        except (OSError, TimeoutError, ValueError, AttributeError, HelperUiError) as error:
            return {**base, "reason": str(error)}

    def validate_adoption(self) -> dict[str, Any]:
        status = self.status()
        if not status["available"]:
            raise HelperUiError(status.get("reason") or "System helper is unavailable")
        try:
            request = build_validate_request(
                self.config_root,
                target_id=self.target_id,
                flake_target=self.flake_target,
            )
            response = self._send(request)
        except (OSError, TimeoutError, ValueError) as error:
            raise HelperUiError(str(error)) from error

        result_raw = response.get("result")
        result = _mapping(result_raw, "validation result") if result_raw is not None else None
        if response.get("status") == "ok":
            if result is None:
                raise HelperUiError("System helper returned no validation result")
            if "validationReceipt" in result:
                raise HelperUiError("Read-only helper unexpectedly issued a validation receipt")
            if (
                result.get("readOnly") is not True
                or result.get("applyEnabled") is not False
                or result.get("activationEnabled") is not False
                or result.get("planFingerprint")
                != request["payload"]["planFingerprint"]
            ):
                raise HelperUiError("Validation result crossed the read-only UI boundary")
            validation = _mapping(result.get("validation"), "validation details")
        elif response.get("status") == "error" and result is not None:
            validation = result
        else:
            error = _mapping(response.get("error"), "error")
            raise HelperUiError(str(error.get("message") or "System helper validation failed"))

        if (
            validation.get("liveTarget") is not True
            or validation.get("readOnly") is not True
            or validation.get("applyEnabled") is not False
            or validation.get("activationEnabled") is not False
        ):
            raise HelperUiError("Helper validation details are not live-read-only")
        error = response.get("error")
        return {
            "source": "system-helper",
            "status": validation.get("status", "failed"),
            "checks": list(validation.get("checks") or []),
            "warnings": list(validation.get("warnings") or []),
            "planFingerprint": (
                result.get("planFingerprint") if response.get("status") == "ok" else None
            ),
            "workingCopyRemoved": validation.get("workingCopyRemoved") is True,
            "readOnly": True,
            "applyEnabled": False,
            "recoveryEnabled": False,
            "activationEnabled": False,
            "validationReceiptIssued": False,
            "transportStatus": response.get("status"),
            "error": dict(error) if isinstance(error, Mapping) else None,
        }

    def preview_activation(
        self, *, system_path: str, plan_fingerprint: str
    ) -> dict[str, Any]:
        status = self.status()
        if not status["available"]:
            raise HelperUiError(status.get("reason") or "System helper is unavailable")
        if status.get("dryActivatePreviewEnabled") is not True:
            raise HelperUiError("System helper does not advertise dry-activation preview")
        try:
            request = build_activation_preview_request(
                self.config_root,
                target_id=self.target_id,
                flake_target=self.flake_target,
                system_path=system_path,
                expected_fingerprint=plan_fingerprint,
            )
            response = self._send(request)
        except (OSError, TimeoutError, ValueError) as error:
            raise HelperUiError(str(error)) from error
        if response.get("status") != "ok":
            error = _mapping(response.get("error"), "error")
            raise HelperUiError(str(error.get("message") or "Dry-activation preview failed"))
        result = _mapping(response.get("result"), "dry-activation result")
        if (
            result.get("status") != "passed"
            or result.get("systemPath") != system_path
            or result.get("planFingerprint") != plan_fingerprint
            or result.get("configurationWriteEnabled") is not False
            or result.get("activationEnabled") is not False
            or result.get("testEnabled") is not False
            or result.get("switchEnabled") is not False
            or result.get("sourceFilesUnchanged") is not True
            or result.get("currentSystemUnchanged") is not True
        ):
            raise HelperUiError("Dry-activation result crossed the read-only UI boundary")
        return {
            **dict(result),
            "source": "system-helper",
            "authorizedByPolkit": True,
            "dryActivateExecuted": True,
        }

    def test_activation(
        self,
        *,
        system_path: str,
        plan_fingerprint: str,
        test_receipt: str,
    ) -> dict[str, Any]:
        status = self.status()
        if status.get("testActivationEnabled") is not True:
            raise HelperUiError("System helper does not permit test activation")
        try:
            response = self._send(
                build_test_activation_request(
                    target_id=self.target_id,
                    system_path=system_path,
                    plan_fingerprint=plan_fingerprint,
                    test_receipt=test_receipt,
                )
            )
        except (OSError, TimeoutError, ValueError) as error:
            raise HelperUiError(str(error)) from error
        if response.get("status") != "ok":
            error = _mapping(response.get("error"), "error")
            raise HelperUiError(str(error.get("message") or "Test activation failed"))
        result = _mapping(response.get("result"), "test activation result")
        if (
            result.get("status") != "active"
            or result.get("systemPath") != system_path
            or result.get("planFingerprint") != plan_fingerprint
            or result.get("testEnabled") is not True
            or result.get("switchEnabled") is not False
            or result.get("configurationWriteEnabled") is not False
            or result.get("autoRecoveryScheduled") is not True
            or not isinstance(result.get("sessionId"), str)
        ):
            raise HelperUiError("Test activation result crossed the bounded-test boundary")
        return {**dict(result), "source": "system-helper", "authorizedByPolkit": True}

    def recover_test_activation(self, *, session_id: str) -> dict[str, Any]:
        status = self.status()
        if status.get("testActivationEnabled") is not True:
            raise HelperUiError("System helper does not permit test recovery")
        try:
            response = self._send(
                build_test_recovery_request(
                    target_id=self.target_id, session_id=session_id
                )
            )
        except (OSError, TimeoutError, ValueError) as error:
            raise HelperUiError(str(error)) from error
        if response.get("status") != "ok":
            error = _mapping(response.get("error"), "error")
            raise HelperUiError(str(error.get("message") or "Test recovery failed"))
        result = _mapping(response.get("result"), "test recovery result")
        if (
            result.get("status") != "recovered"
            or result.get("sessionId") != session_id
            or result.get("currentSystemRestored") is not True
            or result.get("switchEnabled") is not False
            or result.get("configurationWriteEnabled") is not False
        ):
            raise HelperUiError("Test recovery result crossed the bounded-test boundary")
        return {**dict(result), "source": "system-helper", "authorizedByPolkit": True}
