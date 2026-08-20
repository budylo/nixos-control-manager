from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import secrets
from typing import Any, Callable, Mapping

from .errors import NcmError
from .helper_client import (
    build_activation_session_request,
    build_activation_preview_request,
    build_commit_tested_system_request,
    build_home_manager_validate_request,
    build_managed_validate_request,
    build_test_activation_request,
    build_test_recovery_request,
    build_validate_request,
)
from .helper_transport import send_unix_request
from .model import ManagedState


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
            "permanentSwitchEnabled": False,
            "rollbackGenerationEnabled": False,
            "homeManagerApplyEnabled": False,
            "homeManagerLiveWriteEnabled": False,
            "managedWriteEnabled": False,
            "managedRecoveryEnabled": False,
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
            operations = set(result.get("operations") or [])
            permanent_switch_enabled = (
                target.get("fixtureOnly") is False
                and target.get("testActivationEnabled") is True
                and target.get("managedWriteEnabled") is True
                and target.get("managedRecoveryEnabled") is True
                and target.get("permanentSwitchEnabled") is True
                and target.get("rollbackGenerationEnabled") is True
                and set(target.get("allowedRelativePaths") or [])
                == {"ncm/state.json", "ncm/packages.nix"}
                and {
                    "preview-activation",
                    "test-activation",
                    "recover-test-activation",
                    "commit-tested-system",
                    "rollback-committed-system",
                    "activation-session-status",
                }.issubset(operations)
            )
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
                "permanentSwitchEnabled": permanent_switch_enabled,
                "rollbackGenerationEnabled": permanent_switch_enabled,
                "homeManagerApplyEnabled": (
                    target.get("fixtureOnly") is False
                    and target.get("homeManagerApplyEnabled") is True
                    and target.get("homeManagerLiveWriteEnabled") is True
                    and "validate-home-manager-plan" in (result.get("operations") or [])
                    and "apply-validated-home-manager-plan"
                    in (result.get("operations") or [])
                ),
                "homeManagerLiveWriteEnabled": (
                    target.get("fixtureOnly") is False
                    and target.get("homeManagerApplyEnabled") is True
                    and target.get("homeManagerLiveWriteEnabled") is True
                    and "validate-home-manager-plan" in (result.get("operations") or [])
                    and "apply-validated-home-manager-plan"
                    in (result.get("operations") or [])
                ),
                "managedWriteEnabled": (
                    target.get("fixtureOnly") is False
                    and target.get("managedWriteEnabled") is True
                    and target.get("managedRecoveryEnabled") is True
                    and set(target.get("allowedRelativePaths") or [])
                    == {"ncm/state.json", "ncm/packages.nix"}
                    and "validate-managed-plan" in (result.get("operations") or [])
                    and "apply-validated-managed-plan"
                    in (result.get("operations") or [])
                ),
                "managedRecoveryEnabled": (
                    target.get("fixtureOnly") is False
                    and target.get("managedRecoveryEnabled") is True
                    and "recover-managed-transaction"
                    in (result.get("operations") or [])
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

    def validate_home_manager(
        self,
        *,
        username: str,
        integration: str,
        packages: tuple[str, ...],
        expected_plan_fingerprint: str,
    ) -> dict[str, Any]:
        status = self.status()
        if status.get("homeManagerApplyEnabled") is not True:
            raise HelperUiError(
                "System helper does not permit live Home Manager source writes"
            )
        try:
            request = build_home_manager_validate_request(
                self.config_root,
                target_id=self.target_id,
                username=username,
                integration=integration,
                packages=packages,
                flake_target=self.flake_target,
            )
            if request["payload"]["planFingerprint"] != expected_plan_fingerprint:
                raise HelperUiError(
                    "The displayed Home Manager plan differs from the helper plan"
                )
            response = self._send(request)
        except (OSError, TimeoutError, ValueError) as error:
            raise HelperUiError(str(error)) from error
        if response.get("status") != "ok":
            error = _mapping(response.get("error"), "error")
            raise HelperUiError(
                str(error.get("message") or "Home Manager helper validation failed")
            )
        result = _mapping(response.get("result"), "Home Manager validation result")
        validation = _mapping(result.get("validation"), "Home Manager validation details")
        receipt = result.get("validationReceipt")
        if (
            result.get("targetId") != self.target_id
            or result.get("planFingerprint") != expected_plan_fingerprint
            or result.get("username") != username
            or result.get("integration") != integration
            or result.get("fixtureOnly") is not False
            or result.get("liveWriteEnabled") is not True
            or result.get("activationEnabled") is not False
            or validation.get("status") != "passed"
            or validation.get("workingCopyRemoved") is not True
            or not isinstance(receipt, str)
            or len(receipt) < 32
        ):
            raise HelperUiError(
                "Home Manager validation crossed the bounded live-write boundary"
            )
        return {
            "source": "system-helper",
            "status": "passed",
            "targetId": self.target_id,
            "username": username,
            "integration": integration,
            "planFingerprint": expected_plan_fingerprint,
            "validationReceipt": receipt,
            "expiresInSeconds": result.get("expiresInSeconds"),
            "checks": list(validation.get("checks") or []),
            "warnings": list(validation.get("warnings") or []),
            "workingCopyRemoved": True,
            "fixtureOnly": False,
            "liveWriteEnabled": True,
            "activationEnabled": False,
            "homeManagerActivationEnabled": False,
        }

    def validate_managed(self, state: ManagedState) -> dict[str, Any]:
        status = self.status()
        if status.get("managedWriteEnabled") is not True:
            raise HelperUiError(
                "System helper does not permit bounded managed source writes"
            )
        try:
            request = build_managed_validate_request(
                self.config_root,
                state,
                target_id=self.target_id,
                flake_target=self.flake_target,
            )
            response = self._send(request)
        except (OSError, TimeoutError, ValueError) as error:
            raise HelperUiError(str(error)) from error
        if response.get("status") != "ok":
            error = _mapping(response.get("error"), "error")
            raise HelperUiError(
                str(error.get("message") or "Managed helper validation failed")
            )
        result = _mapping(response.get("result"), "managed validation result")
        validation = _mapping(result.get("validation"), "managed validation details")
        receipt = result.get("validationReceipt")
        if (
            result.get("targetId") != self.target_id
            or result.get("fixtureOnly") is not False
            or result.get("managedWriteEnabled") is not True
            or result.get("activationEnabled") is not False
            or validation.get("status") != "passed"
            or validation.get("workingCopyRemoved") is not True
            or set(validation.get("writeScope") or [])
            != {"ncm/state.json", "ncm/packages.nix"}
            or not isinstance(receipt, str)
            or len(receipt) < 32
        ):
            raise HelperUiError("Managed validation crossed the bounded write boundary")
        return {
            "source": "system-helper",
            "status": "passed",
            "targetId": self.target_id,
            "planFingerprint": result.get("planFingerprint"),
            "validationReceipt": receipt,
            "expiresInSeconds": result.get("expiresInSeconds"),
            "checks": list(validation.get("checks") or []),
            "warnings": list(validation.get("warnings") or []),
            "workingCopyRemoved": True,
            "fixtureOnly": False,
            "managedWriteEnabled": True,
            "writeScope": list(validation.get("writeScope") or []),
            "activationEnabled": False,
        }

    def apply_managed(
        self, *, plan_fingerprint: str, validation_receipt: str
    ) -> dict[str, Any]:
        status = self.status()
        if status.get("managedWriteEnabled") is not True:
            raise HelperUiError(
                "System helper does not permit bounded managed source writes"
            )
        try:
            response = self._send(
                self._request(
                    "apply-validated-managed-plan",
                    {
                        "targetId": self.target_id,
                        "planFingerprint": plan_fingerprint,
                        "validationReceipt": validation_receipt,
                    },
                )
            )
        except (OSError, TimeoutError, ValueError) as error:
            raise HelperUiError(str(error)) from error
        if response.get("status") != "ok":
            error = _mapping(response.get("error"), "error")
            raise HelperUiError(str(error.get("message") or "Managed persistence failed"))
        result = _mapping(response.get("result"), "managed apply result")
        transaction = _mapping(result.get("transaction"), "managed transaction")
        if (
            result.get("state") != "committed"
            or result.get("fixtureOnly") is not False
            or result.get("managedWriteEnabled") is not True
            or result.get("activationEnabled") is not False
            or result.get("switchEnabled") is not False
            or transaction.get("state") != "committed"
            or transaction.get("fixtureOnly") is not False
            or not isinstance(result.get("filesWritten"), int)
            or not 1 <= result.get("filesWritten") <= 2
            or set(transaction.get("changedFiles") or [])
            - {"ncm/state.json", "ncm/packages.nix"}
        ):
            raise HelperUiError("Managed apply crossed the bounded write boundary")
        return {
            **dict(result),
            "transaction": dict(transaction),
            "source": "system-helper",
            "authorizedByPolkit": True,
            "switchEnabled": False,
        }

    def apply_home_manager(
        self, *, plan_fingerprint: str, validation_receipt: str
    ) -> dict[str, Any]:
        status = self.status()
        if status.get("homeManagerApplyEnabled") is not True:
            raise HelperUiError(
                "System helper does not permit live Home Manager source writes"
            )
        try:
            response = self._send(
                self._request(
                    "apply-validated-home-manager-plan",
                    {
                        "targetId": self.target_id,
                        "planFingerprint": plan_fingerprint,
                        "validationReceipt": validation_receipt,
                    },
                )
            )
        except (OSError, TimeoutError, ValueError) as error:
            raise HelperUiError(str(error)) from error
        if response.get("status") != "ok":
            error = _mapping(response.get("error"), "error")
            raise HelperUiError(
                str(error.get("message") or "Home Manager source persistence failed")
            )
        result = _mapping(response.get("result"), "Home Manager apply result")
        transaction = _mapping(result.get("transaction"), "Home Manager transaction")
        if (
            result.get("state") != "committed"
            or result.get("fixtureOnly") is not False
            or result.get("writeEnabled") is not True
            or result.get("liveWriteEnabled") is not True
            or result.get("activationEnabled") is not False
            or result.get("buildEnabled") is not False
            or transaction.get("state") != "committed"
            or transaction.get("fixtureOnly") is not False
            or transaction.get("activationEnabled") is not False
            or not isinstance(result.get("filesWritten"), int)
            or result.get("filesWritten") < 1
            or not isinstance(transaction.get("transactionId"), str)
            or not re.fullmatch(r"[0-9a-f]{24}", transaction["transactionId"])
        ):
            raise HelperUiError(
                "Home Manager apply result crossed the bounded live-write boundary"
            )
        return {
            **dict(result),
            "transaction": dict(transaction),
            "source": "system-helper",
            "authorizedByPolkit": True,
            "homeManagerActivationEnabled": False,
            "switchEnabled": False,
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

    def commit_tested_system(
        self,
        *,
        system_path: str,
        plan_fingerprint: str,
        session_id: str,
    ) -> dict[str, Any]:
        status = self.status()
        if status.get("permanentSwitchEnabled") is not True:
            raise HelperUiError("System helper does not permit permanent switching")
        try:
            request = build_commit_tested_system_request(
                self.config_root,
                target_id=self.target_id,
                flake_target=self.flake_target,
                system_path=system_path,
                expected_fingerprint=plan_fingerprint,
                session_id=session_id,
            )
            response = self._send(request)
        except (OSError, TimeoutError, ValueError) as error:
            raise HelperUiError(str(error)) from error
        if response.get("status") != "ok":
            error = _mapping(response.get("error"), "error")
            raise HelperUiError(str(error.get("message") or "Permanent switch failed"))
        result = _mapping(response.get("result"), "permanent switch result")
        if (
            result.get("status") != "committing"
            or result.get("sessionId") != session_id
            or result.get("systemPath") != system_path
            or result.get("planFingerprint") != plan_fingerprint
            or result.get("switchEnabled") is not True
            or result.get("rollbackEnabled") is not True
            or result.get("arbitraryCommandsAccepted") is not False
        ):
            raise HelperUiError("Permanent switch result crossed the exact-session boundary")
        return {**dict(result), "source": "system-helper", "authorizedByPolkit": True}

    def activation_session_status(self, *, session_id: str) -> dict[str, Any]:
        status = self.status()
        if status.get("permanentSwitchEnabled") is not True:
            raise HelperUiError("System helper does not expose permanent activation state")
        try:
            response = self._send(
                build_activation_session_request(
                    "activation-session-status",
                    target_id=self.target_id,
                    session_id=session_id,
                )
            )
        except (OSError, TimeoutError, ValueError) as error:
            raise HelperUiError(str(error)) from error
        if response.get("status") != "ok":
            error = _mapping(response.get("error"), "error")
            raise HelperUiError(str(error.get("message") or "Activation status failed"))
        result = _mapping(response.get("result"), "activation session status")
        if (
            result.get("sessionId") != session_id
            or result.get("status") not in {
                "commit-prepared",
                "committing",
                "committed",
                "commit-failed",
                "recovered",
                "recovery-required",
                "rollback-prepared",
                "rolling-back",
                "rolled-back",
                "rollback-required",
            }
            or result.get("switchEnabled") is not True
            or result.get("arbitraryCommandsAccepted") is not False
        ):
            raise HelperUiError("Helper returned an invalid activation session state")
        return {**dict(result), "source": "system-helper"}

    def rollback_committed_system(self, *, session_id: str) -> dict[str, Any]:
        status = self.status()
        if status.get("rollbackGenerationEnabled") is not True:
            raise HelperUiError("System helper does not permit generation rollback")
        try:
            response = self._send(
                build_activation_session_request(
                    "rollback-committed-system",
                    target_id=self.target_id,
                    session_id=session_id,
                )
            )
        except (OSError, TimeoutError, ValueError) as error:
            raise HelperUiError(str(error)) from error
        if response.get("status") != "ok":
            error = _mapping(response.get("error"), "error")
            raise HelperUiError(str(error.get("message") or "Generation rollback failed"))
        result = _mapping(response.get("result"), "generation rollback result")
        if (
            result.get("status") != "rolling-back"
            or result.get("sessionId") != session_id
            or result.get("switchEnabled") is not True
            or result.get("rollbackEnabled") is not True
            or result.get("arbitraryCommandsAccepted") is not False
        ):
            raise HelperUiError("Rollback result crossed the exact-session boundary")
        return {**dict(result), "source": "system-helper", "authorizedByPolkit": True}
