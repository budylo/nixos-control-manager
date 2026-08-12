from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import re
import secrets
import time
from typing import Any, Mapping, Protocol

from .helper_protocol import (
    ApplyValidatedPlanPayload,
    HelperProtocolError,
    HelperRequest,
    PreviewActivationPayload,
    RecoverTestActivationPayload,
    RecoverTransactionPayload,
    SUPPORTED_OPERATIONS,
    ValidatePlanPayload,
    TestActivationPayload,
    response_mapping,
    validate_empty_payload,
)


APPLY_ACTION_ID = "org.nixos.nix-control-manager.apply-validated-plan"
RECOVER_ACTION_ID = "org.nixos.nix-control-manager.recover-transaction"
PREVIEW_ACTIVATION_ACTION_ID = "org.nixos.nix-control-manager.preview-activation"
TEST_ACTIVATION_ACTION_ID = "org.nixos.nix-control-manager.test-activation"
RECOVER_TEST_ACTIVATION_ACTION_ID = "org.nixos.nix-control-manager.recover-test-activation"
_TARGET_ID = re.compile(r"^[a-z][a-z0-9-]{0,31}$")


@dataclass(frozen=True, slots=True)
class HelperTarget:
    target_id: str
    configuration_root: Path
    allowed_relative_paths: frozenset[str]
    fixture_only: bool = True
    apply_enabled: bool = True
    journal_root: Path | None = None
    flake_target: str | None = None
    test_activation_enabled: bool = False
    test_journal_root: Path | None = None
    test_timeout_seconds: int = 300

    def __post_init__(self) -> None:
        if not _TARGET_ID.fullmatch(self.target_id):
            raise ValueError(f"Invalid helper target identifier: {self.target_id}")
        object.__setattr__(
            self, "configuration_root", self.configuration_root.expanduser().resolve()
        )
        if self.journal_root is not None:
            object.__setattr__(
                self, "journal_root", self.journal_root.expanduser().resolve()
            )
        if self.test_journal_root is not None:
            object.__setattr__(
                self, "test_journal_root", self.test_journal_root.expanduser().resolve()
            )
        if not self.allowed_relative_paths:
            raise ValueError("A helper target requires at least one allowed path")
        if not self.fixture_only and self.apply_enabled:
            raise ValueError("Live helper targets must remain read-only")
        if self.test_activation_enabled and (
            self.fixture_only or self.apply_enabled or self.test_journal_root is None
        ):
            raise ValueError("Test activation requires a non-writing live target and journal")
        if not self.test_activation_enabled and self.test_journal_root is not None:
            raise ValueError("A test journal is valid only when test activation is enabled")
        if not 30 <= self.test_timeout_seconds <= 1800:
            raise ValueError("test_timeout_seconds must be between 30 and 1800")
        for label in self.allowed_relative_paths:
            path = PurePosixPath(label)
            if (
                path.is_absolute()
                or not path.parts
                or any(part in {"", ".", ".."} for part in path.parts)
                or str(path) != label
            ):
                raise ValueError(f"Invalid helper allow-list path: {label}")


@dataclass(frozen=True, slots=True)
class PendingValidatedPlan:
    receipt: str
    peer_uid: int
    payload: ValidatePlanPayload
    expires_at: float
    validation_result: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class PendingTestActivation:
    receipt: str
    peer_uid: int
    payload: PreviewActivationPayload
    expires_at: float


class HelperBackendError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class PeerIdentity:
    uid: int
    pid: int | None = None
    gid: int | None = None

    def __post_init__(self) -> None:
        if isinstance(self.uid, bool) or not isinstance(self.uid, int) or self.uid < 0:
            raise ValueError("peer uid must be a non-negative integer")
        for label, value in (("uid", self.uid), ("pid", self.pid), ("gid", self.gid)):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"peer {label} must be a non-negative integer")


class Authorizer(Protocol):
    def authorize(
        self, action_id: str, peer: PeerIdentity, details: Mapping[str, str]
    ) -> bool: ...


class HelperBackend(Protocol):
    def validate_plan(
        self, target: HelperTarget, plan: ValidatePlanPayload, peer_uid: int
    ) -> Mapping[str, Any]: ...

    def apply_validated_plan(
        self, target: HelperTarget, plan: PendingValidatedPlan, peer_uid: int
    ) -> Mapping[str, Any]: ...

    def recover_transaction(
        self, target: HelperTarget, transaction_id: str, peer_uid: int
    ) -> Mapping[str, Any]: ...

    def preview_activation(
        self, target: HelperTarget, payload: PreviewActivationPayload, peer_uid: int
    ) -> Mapping[str, Any]: ...

    def test_activation(
        self, target: HelperTarget, payload: PreviewActivationPayload, peer_uid: int
    ) -> Mapping[str, Any]: ...

    def recover_test_activation(
        self, target: HelperTarget, session_id: str, peer_uid: int
    ) -> Mapping[str, Any]: ...


@dataclass(slots=True)
class MockPolkitAuthorizer:
    allowed: set[tuple[int, str]] = field(default_factory=set)
    calls: list[tuple[str, int, Mapping[str, str]]] = field(default_factory=list)

    def authorize(
        self, action_id: str, peer: PeerIdentity, details: Mapping[str, str]
    ) -> bool:
        self.calls.append((action_id, peer.uid, dict(details)))
        return (peer.uid, action_id) in self.allowed


@dataclass(slots=True)
class RecordingMockBackend:
    validation_status: str = "passed"
    validate_calls: list[tuple[str, str, int]] = field(default_factory=list)
    apply_calls: list[tuple[str, str, int]] = field(default_factory=list)
    recover_calls: list[tuple[str, str, int]] = field(default_factory=list)
    preview_activation_calls: list[tuple[str, str, str, int]] = field(default_factory=list)
    test_activation_calls: list[tuple[str, str, str, int]] = field(default_factory=list)
    recover_test_activation_calls: list[tuple[str, str, int]] = field(default_factory=list)

    def validate_plan(
        self, target: HelperTarget, plan: ValidatePlanPayload, peer_uid: int
    ) -> Mapping[str, Any]:
        self.validate_calls.append((target.target_id, plan.plan_fingerprint, peer_uid))
        return {
            "status": self.validation_status,
            "fixtureOnly": True,
            "workingCopyRemoved": True,
            "activationEnabled": False,
        }

    def apply_validated_plan(
        self, target: HelperTarget, plan: PendingValidatedPlan, peer_uid: int
    ) -> Mapping[str, Any]:
        self.apply_calls.append(
            (target.target_id, plan.payload.plan_fingerprint, peer_uid)
        )
        return {
            "state": "mock-applied",
            "transactionId": secrets.token_hex(12),
            "fixtureOnly": True,
            "filesWritten": 0,
            "activationEnabled": False,
        }

    def recover_transaction(
        self, target: HelperTarget, transaction_id: str, peer_uid: int
    ) -> Mapping[str, Any]:
        self.recover_calls.append((target.target_id, transaction_id, peer_uid))
        return {
            "state": "mock-recovered",
            "transactionId": transaction_id,
            "fixtureOnly": True,
            "filesWritten": 0,
            "activationEnabled": False,
        }

    def preview_activation(
        self, target: HelperTarget, payload: PreviewActivationPayload, peer_uid: int
    ) -> Mapping[str, Any]:
        self.preview_activation_calls.append(
            (target.target_id, payload.plan_fingerprint, payload.system_path, peer_uid)
        )
        return {
            "status": "passed",
            "systemPath": payload.system_path,
            "stdout": "would restart: example.service\n",
            "stderr": "",
            "exitCode": 0,
            "sourceFilesUnchanged": True,
            "currentSystemUnchanged": True,
            "configurationWriteEnabled": False,
            "activationEnabled": False,
            "testEnabled": False,
            "switchEnabled": False,
        }

    def discard_validated_plan(
        self, target: HelperTarget, plan: ValidatePlanPayload, peer_uid: int
    ) -> None:
        return None

    def test_activation(
        self, target: HelperTarget, payload: PreviewActivationPayload, peer_uid: int
    ) -> Mapping[str, Any]:
        self.test_activation_calls.append(
            (target.target_id, payload.plan_fingerprint, payload.system_path, peer_uid)
        )
        return {
            "status": "active",
            "sessionId": secrets.token_hex(12),
            "systemPath": payload.system_path,
            "previousSystemPath": "/nix/store/" + "a" * 32 + "-previous",
            "planFingerprint": payload.plan_fingerprint,
            "testEnabled": True,
            "switchEnabled": False,
            "configurationWriteEnabled": False,
            "autoRecoveryScheduled": True,
        }

    def recover_test_activation(
        self, target: HelperTarget, session_id: str, peer_uid: int
    ) -> Mapping[str, Any]:
        self.recover_test_activation_calls.append((target.target_id, session_id, peer_uid))
        return {
            "status": "recovered",
            "sessionId": session_id,
            "testEnabled": True,
            "switchEnabled": False,
            "configurationWriteEnabled": False,
            "currentSystemRestored": True,
        }


class HelperDispatcher:
    def __init__(
        self,
        *,
        targets: tuple[HelperTarget, ...],
        authorizer: Authorizer,
        backend: HelperBackend,
        receipt_ttl_seconds: int = 300,
    ) -> None:
        if not 1 <= receipt_ttl_seconds <= 3600:
            raise ValueError("receipt_ttl_seconds must be between 1 and 3600")
        self.targets = {target.target_id: target for target in targets}
        if len(self.targets) != len(targets):
            raise ValueError("Duplicate helper target identifiers")
        self.authorizer = authorizer
        self.backend = backend
        self.receipt_ttl_seconds = receipt_ttl_seconds
        self._pending: dict[str, PendingValidatedPlan] = {}
        self._pending_tests: dict[str, PendingTestActivation] = {}

    @staticmethod
    def _response_id(raw: Any) -> str:
        if isinstance(raw, Mapping):
            value = raw.get("requestId")
            if isinstance(value, str) and 1 <= len(value) <= 64:
                return value
        return "unknown-request"

    def _target(self, target_id: str) -> HelperTarget:
        try:
            return self.targets[target_id]
        except KeyError as error:
            raise HelperProtocolError("unknown-target", f"Unknown targetId: {target_id}") from error

    def _prune_receipts(self) -> None:
        now = time.monotonic()
        for receipt, pending in tuple(self._pending.items()):
            if pending.expires_at <= now:
                del self._pending[receipt]
                target = self.targets.get(pending.payload.target_id)
                discard = getattr(self.backend, "discard_validated_plan", None)
                if target is not None and discard is not None:
                    discard(target, pending.payload, pending.peer_uid)
        for receipt, pending in tuple(self._pending_tests.items()):
            if pending.expires_at <= now:
                del self._pending_tests[receipt]

    def handle(
        self,
        raw: Any,
        *,
        peer_uid: int | None = None,
        peer: PeerIdentity | None = None,
    ) -> dict[str, Any]:
        request_id = self._response_id(raw)
        try:
            if peer is not None and peer_uid is not None:
                raise HelperProtocolError(
                    "invalid-peer", "Provide either peer credentials or peer_uid, not both"
                )
            if peer is None:
                try:
                    peer = PeerIdentity(uid=peer_uid)  # type: ignore[arg-type]
                except (TypeError, ValueError) as error:
                    raise HelperProtocolError(
                        "invalid-peer", "A non-negative peer UID is required"
                    ) from error
            request = HelperRequest.from_mapping(raw)
            request_id = request.request_id
            self._prune_receipts()
            if request.operation == "capabilities":
                validate_empty_payload(request.payload)
                return response_mapping(
                    request_id,
                    status="ok",
                    result={
                        "protocolVersion": 1,
                        "operations": sorted(SUPPORTED_OPERATIONS),
                        "targets": [
                            {
                                "targetId": target.target_id,
                                "allowedRelativePaths": sorted(
                                    target.allowed_relative_paths
                                ),
                                "fixtureOnly": target.fixture_only,
                                "liveTarget": not target.fixture_only,
                                "readOnly": not target.apply_enabled,
                                "applyEnabled": target.apply_enabled,
                                "recoveryEnabled": target.apply_enabled,
                                "dryActivatePreviewEnabled": not target.fixture_only,
                                "testActivationEnabled": target.test_activation_enabled,
                            }
                            for target in self.targets.values()
                        ],
                        "authorizationActions": {
                            "apply-validated-plan": APPLY_ACTION_ID,
                            "recover-transaction": RECOVER_ACTION_ID,
                            "preview-activation": PREVIEW_ACTIVATION_ACTION_ID,
                            "test-activation": TEST_ACTIVATION_ACTION_ID,
                            "recover-test-activation": RECOVER_TEST_ACTIVATION_ACTION_ID,
                        },
                        "arbitraryCommandsAccepted": False,
                        "activationEnabled": False,
                    },
                )
            if request.operation == "validate-plan":
                return self._validate(request_id, request.payload, peer.uid)
            if request.operation == "preview-activation":
                return self._preview_activation(request_id, request.payload, peer)
            if request.operation == "test-activation":
                return self._test_activation(request_id, request.payload, peer)
            if request.operation == "recover-test-activation":
                return self._recover_test_activation(request_id, request.payload, peer)
            if request.operation == "apply-validated-plan":
                return self._apply(request_id, request.payload, peer)
            if request.operation == "recover-transaction":
                return self._recover(request_id, request.payload, peer)
            raise AssertionError(f"Unhandled helper operation: {request.operation}")
        except HelperProtocolError as error:
            return response_mapping(
                request_id,
                status="error",
                error_code=error.code,
                error_message=str(error),
            )
        except HelperBackendError as error:
            return response_mapping(
                request_id,
                status="error",
                error_code=error.code,
                error_message=str(error),
            )
        except Exception:
            return response_mapping(
                request_id,
                status="error",
                error_code="internal-error",
                error_message="The helper could not complete the request safely",
            )

    def _validate(
        self, request_id: str, raw: Any, peer_uid: int
    ) -> dict[str, Any]:
        payload = ValidatePlanPayload.from_mapping(raw)
        target = self._target(payload.target_id)
        for change in payload.changes:
            if change.relative_path not in target.allowed_relative_paths:
                raise HelperProtocolError(
                    "path-not-allowed",
                    f"The helper target does not allow {change.relative_path}",
                )
        validation = dict(self.backend.validate_plan(target, payload, peer_uid))
        if validation.get("status") != "passed":
            return response_mapping(
                request_id,
                status="error",
                error_code="validation-failed",
                error_message="The helper backend did not validate the plan",
                result=validation,
            )
        if not target.apply_enabled:
            return response_mapping(
                request_id,
                status="ok",
                result={
                    "targetId": payload.target_id,
                    "planFingerprint": payload.plan_fingerprint,
                    "validation": validation,
                    "readOnly": True,
                    "applyEnabled": False,
                    "activationEnabled": False,
                },
            )
        receipt = secrets.token_urlsafe(32)
        pending = PendingValidatedPlan(
            receipt=receipt,
            peer_uid=peer_uid,
            payload=payload,
            expires_at=time.monotonic() + self.receipt_ttl_seconds,
            validation_result=validation,
        )
        self._pending[receipt] = pending
        return response_mapping(
            request_id,
            status="ok",
            result={
                "validationReceipt": receipt,
                "expiresInSeconds": self.receipt_ttl_seconds,
                "targetId": payload.target_id,
                "planFingerprint": payload.plan_fingerprint,
                "validation": validation,
                "activationEnabled": False,
            },
        )

    def _apply(
        self, request_id: str, raw: Any, peer: PeerIdentity
    ) -> dict[str, Any]:
        payload = ApplyValidatedPlanPayload.from_mapping(raw)
        target = self._target(payload.target_id)
        if not target.apply_enabled:
            raise HelperProtocolError(
                "operation-disabled", "The target does not permit apply operations"
            )
        pending = self._pending.get(payload.validation_receipt)
        if (
            pending is None
            or pending.peer_uid != peer.uid
            or pending.payload.target_id != payload.target_id
            or pending.payload.plan_fingerprint != payload.plan_fingerprint
        ):
            raise HelperProtocolError(
                "invalid-receipt", "The validation receipt is unknown or does not match"
            )
        details = {
            "targetId": payload.target_id,
            "planFingerprint": payload.plan_fingerprint,
        }
        if not self.authorizer.authorize(APPLY_ACTION_ID, peer, details):
            return response_mapping(
                request_id,
                status="denied",
                error_code="authorization-denied",
                error_message="Polkit authorization was not granted",
            )
        del self._pending[payload.validation_receipt]
        result = self.backend.apply_validated_plan(target, pending, peer.uid)
        return response_mapping(request_id, status="ok", result=result)

    def _preview_activation(
        self, request_id: str, raw: Any, peer: PeerIdentity
    ) -> dict[str, Any]:
        payload = PreviewActivationPayload.from_mapping(raw)
        target = self._target(payload.target_id)
        if target.fixture_only or target.apply_enabled:
            raise HelperProtocolError(
                "operation-disabled",
                "Dry-activation preview is restricted to a read-only live target",
            )
        for change in payload.changes:
            if change.relative_path not in target.allowed_relative_paths:
                raise HelperProtocolError(
                    "path-not-allowed",
                    f"The helper target does not allow {change.relative_path}",
                )
        details = {
            "targetId": payload.target_id,
            "planFingerprint": payload.plan_fingerprint,
            "systemPath": payload.system_path,
        }
        if not self.authorizer.authorize(PREVIEW_ACTIVATION_ACTION_ID, peer, details):
            return response_mapping(
                request_id,
                status="denied",
                error_code="authorization-denied",
                error_message="Polkit authorization was not granted",
            )
        result = dict(self.backend.preview_activation(target, payload, peer.uid))
        if target.test_activation_enabled:
            receipt = secrets.token_urlsafe(32)
            self._pending_tests[receipt] = PendingTestActivation(
                receipt=receipt,
                peer_uid=peer.uid,
                payload=payload,
                expires_at=time.monotonic() + self.receipt_ttl_seconds,
            )
            result.update(
                {
                    "testActivationPrepared": True,
                    "testReceipt": receipt,
                    "testReceiptExpiresInSeconds": self.receipt_ttl_seconds,
                }
            )
        else:
            result["testActivationPrepared"] = False
        return response_mapping(request_id, status="ok", result=result)

    def _test_activation(
        self, request_id: str, raw: Any, peer: PeerIdentity
    ) -> dict[str, Any]:
        payload = TestActivationPayload.from_mapping(raw)
        target = self._target(payload.target_id)
        if not target.test_activation_enabled:
            raise HelperProtocolError(
                "operation-disabled", "The target does not permit test activation"
            )
        pending = self._pending_tests.get(payload.test_receipt)
        if (
            pending is None
            or pending.peer_uid != peer.uid
            or pending.payload.target_id != payload.target_id
            or pending.payload.plan_fingerprint != payload.plan_fingerprint
            or pending.payload.system_path != payload.system_path
        ):
            raise HelperProtocolError(
                "invalid-receipt", "The test receipt is unknown or does not match"
            )
        details = {
            "targetId": payload.target_id,
            "planFingerprint": payload.plan_fingerprint,
            "systemPath": payload.system_path,
        }
        if not self.authorizer.authorize(TEST_ACTIVATION_ACTION_ID, peer, details):
            return response_mapping(
                request_id,
                status="denied",
                error_code="authorization-denied",
                error_message="Polkit authorization was not granted",
            )
        del self._pending_tests[payload.test_receipt]
        result = self.backend.test_activation(target, pending.payload, peer.uid)
        return response_mapping(request_id, status="ok", result=result)

    def _recover_test_activation(
        self, request_id: str, raw: Any, peer: PeerIdentity
    ) -> dict[str, Any]:
        payload = RecoverTestActivationPayload.from_mapping(raw)
        target = self._target(payload.target_id)
        if not target.test_activation_enabled:
            raise HelperProtocolError(
                "operation-disabled", "The target does not permit test recovery"
            )
        details = {"targetId": payload.target_id, "sessionId": payload.session_id}
        if not self.authorizer.authorize(RECOVER_TEST_ACTIVATION_ACTION_ID, peer, details):
            return response_mapping(
                request_id,
                status="denied",
                error_code="authorization-denied",
                error_message="Polkit authorization was not granted",
            )
        result = self.backend.recover_test_activation(
            target, payload.session_id, peer.uid
        )
        return response_mapping(request_id, status="ok", result=result)

    def _recover(
        self, request_id: str, raw: Any, peer: PeerIdentity
    ) -> dict[str, Any]:
        payload = RecoverTransactionPayload.from_mapping(raw)
        target = self._target(payload.target_id)
        if not target.apply_enabled:
            raise HelperProtocolError(
                "operation-disabled", "The target does not permit recovery operations"
            )
        details = {
            "targetId": payload.target_id,
            "transactionId": payload.transaction_id,
        }
        if not self.authorizer.authorize(RECOVER_ACTION_ID, peer, details):
            return response_mapping(
                request_id,
                status="denied",
                error_code="authorization-denied",
                error_message="Polkit authorization was not granted",
            )
        result = self.backend.recover_transaction(
            target, payload.transaction_id, peer.uid
        )
        return response_mapping(request_id, status="ok", result=result)
