from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import PurePosixPath
import re
from typing import Any, Mapping


PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 2_000_000
MAX_CANDIDATE_BYTES = 1_000_000
MAX_CHANGES = 16
MAX_HOME_MANAGER_PACKAGES = 500
SUPPORTED_OPERATIONS = frozenset(
    {
        "capabilities",
        "validate-plan",
        "preview-activation",
        "test-activation",
        "recover-test-activation",
        "apply-validated-plan",
        "recover-transaction",
        "validate-home-manager-plan",
        "apply-validated-home-manager-plan",
        "recover-home-manager-transaction",
    }
)
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_TARGET_ID = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RECEIPT = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
_TRANSACTION_ID = re.compile(r"^[0-9a-f]{24}$")
_STORE_PATH = re.compile(r"^/nix/store/[0-9a-z]{32}-[^/\s]+$")
_USER_NAME = re.compile(r"^[a-z_][a-z0-9_.@-]{0,63}$")
_ATTRIBUTE_PATH = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_'-]*(?:\.[A-Za-z_][A-Za-z0-9_'-]*)*$"
)


class HelperProtocolError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HelperProtocolError("invalid-request", f"{label} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    unknown = set(value) - expected
    missing = expected - set(value)
    if unknown:
        raise HelperProtocolError(
            "invalid-request", f"{label} contains unknown fields: {', '.join(sorted(unknown))}"
        )
    if missing:
        raise HelperProtocolError(
            "invalid-request", f"{label} is missing fields: {', '.join(sorted(missing))}"
        )


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise HelperProtocolError("invalid-request", f"{label} must be a string")
    return value


def _target_id(value: Any) -> str:
    target = _string(value, "targetId")
    if not _TARGET_ID.fullmatch(target):
        raise HelperProtocolError("invalid-target", "targetId has an invalid format")
    return target


def _sha256(value: Any, label: str) -> str:
    digest = _string(value, label)
    if not _SHA256.fullmatch(digest):
        raise HelperProtocolError("invalid-digest", f"{label} must be lowercase SHA-256")
    return digest


@dataclass(frozen=True, slots=True)
class HelperRequest:
    request_id: str
    operation: str
    payload: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, raw: Any) -> "HelperRequest":
        mapping = _mapping(raw, "request")
        _exact_keys(
            mapping,
            {"schemaVersion", "requestId", "operation", "payload"},
            "request",
        )
        if mapping["schemaVersion"] != PROTOCOL_VERSION:
            raise HelperProtocolError(
                "unsupported-version", f"Only schemaVersion {PROTOCOL_VERSION} is supported"
            )
        request_id = _string(mapping["requestId"], "requestId")
        if not _REQUEST_ID.fullmatch(request_id):
            raise HelperProtocolError("invalid-request", "requestId has an invalid format")
        operation = _string(mapping["operation"], "operation")
        if operation not in SUPPORTED_OPERATIONS:
            raise HelperProtocolError("unsupported-operation", f"Unsupported operation: {operation}")
        return cls(
            request_id=request_id,
            operation=operation,
            payload=_mapping(mapping["payload"], "payload"),
        )


@dataclass(frozen=True, slots=True)
class CandidateFile:
    relative_path: str
    action: str
    previous_sha256: str | None
    candidate_sha256: str
    candidate: str

    @classmethod
    def from_mapping(cls, raw: Any) -> "CandidateFile":
        mapping = _mapping(raw, "change")
        _exact_keys(
            mapping,
            {"relativePath", "action", "previousSha256", "candidateSha256", "candidate"},
            "change",
        )
        relative_path = _string(mapping["relativePath"], "relativePath")
        path = PurePosixPath(relative_path)
        if (
            path.is_absolute()
            or not path.parts
            or any(part in {"", ".", ".."} for part in path.parts)
            or str(path) != relative_path
        ):
            raise HelperProtocolError("path-not-allowed", f"Unsafe relative path: {relative_path}")
        action = _string(mapping["action"], "action")
        if action not in {"create", "modify"}:
            raise HelperProtocolError("invalid-request", f"Unsupported file action: {action}")
        previous_raw = mapping["previousSha256"]
        if action == "create":
            if previous_raw is not None:
                raise HelperProtocolError(
                    "invalid-digest", "A create action must have null previousSha256"
                )
            previous = None
        else:
            previous = _sha256(previous_raw, "previousSha256")
        candidate = _string(mapping["candidate"], "candidate")
        if "\x00" in candidate:
            raise HelperProtocolError("invalid-request", "Candidate content cannot contain NUL")
        encoded = candidate.encode("utf-8")
        if len(encoded) > MAX_CANDIDATE_BYTES:
            raise HelperProtocolError("request-too-large", "Candidate file is too large")
        candidate_sha256 = _sha256(mapping["candidateSha256"], "candidateSha256")
        if hashlib.sha256(encoded).hexdigest() != candidate_sha256:
            raise HelperProtocolError("invalid-digest", f"Candidate digest mismatch: {relative_path}")
        return cls(
            relative_path=relative_path,
            action=action,
            previous_sha256=previous,
            candidate_sha256=candidate_sha256,
            candidate=candidate,
        )

    def to_mapping(self, *, include_candidate: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "relativePath": self.relative_path,
            "action": self.action,
            "previousSha256": self.previous_sha256,
            "candidateSha256": self.candidate_sha256,
        }
        if include_candidate:
            result["candidate"] = self.candidate
        return result


@dataclass(frozen=True, slots=True)
class ValidatePlanPayload:
    target_id: str
    plan_fingerprint: str
    changes: tuple[CandidateFile, ...]

    @classmethod
    def from_mapping(cls, raw: Any) -> "ValidatePlanPayload":
        mapping = _mapping(raw, "validate-plan payload")
        _exact_keys(mapping, {"targetId", "planFingerprint", "changes"}, "validate-plan payload")
        changes_raw = mapping["changes"]
        if not isinstance(changes_raw, list) or not 1 <= len(changes_raw) <= MAX_CHANGES:
            raise HelperProtocolError(
                "invalid-request", f"changes must contain between 1 and {MAX_CHANGES} items"
            )
        changes = tuple(CandidateFile.from_mapping(item) for item in changes_raw)
        paths = [change.relative_path for change in changes]
        if len(paths) != len(set(paths)):
            raise HelperProtocolError("invalid-request", "Duplicate change paths are not allowed")
        return cls(
            target_id=_target_id(mapping["targetId"]),
            plan_fingerprint=_sha256(mapping["planFingerprint"], "planFingerprint"),
            changes=changes,
        )


@dataclass(frozen=True, slots=True)
class ValidateHomeManagerPlanPayload:
    target_id: str
    plan_fingerprint: str
    username: str
    integration: str
    packages: tuple[str, ...]
    changes: tuple[CandidateFile, ...]

    @classmethod
    def from_mapping(cls, raw: Any) -> "ValidateHomeManagerPlanPayload":
        mapping = _mapping(raw, "validate-home-manager-plan payload")
        _exact_keys(
            mapping,
            {
                "targetId",
                "planFingerprint",
                "username",
                "integration",
                "packages",
                "changes",
            },
            "validate-home-manager-plan payload",
        )
        username = _string(mapping["username"], "username")
        if not _USER_NAME.fullmatch(username):
            raise HelperProtocolError("invalid-user", "username has an invalid format")
        integration = _string(mapping["integration"], "integration")
        if integration not in {"nixos-module", "standalone"}:
            raise HelperProtocolError(
                "invalid-integration",
                "integration must be nixos-module or standalone",
            )
        packages_raw = mapping["packages"]
        if not isinstance(packages_raw, list) or len(packages_raw) > MAX_HOME_MANAGER_PACKAGES:
            raise HelperProtocolError(
                "invalid-request",
                f"packages must be an array with at most {MAX_HOME_MANAGER_PACKAGES} items",
            )
        packages: list[str] = []
        for value in packages_raw:
            package = _string(value, "package")
            if not _ATTRIBUTE_PATH.fullmatch(package):
                raise HelperProtocolError(
                    "invalid-package", f"Invalid Home Manager package path: {package!r}"
                )
            packages.append(package)
        if len(packages) != len(set(packages)):
            raise HelperProtocolError("invalid-request", "Duplicate packages are not allowed")

        validated = ValidatePlanPayload.from_mapping(
            {
                "targetId": mapping["targetId"],
                "planFingerprint": mapping["planFingerprint"],
                "changes": mapping["changes"],
            }
        )
        return cls(
            target_id=validated.target_id,
            plan_fingerprint=validated.plan_fingerprint,
            username=username,
            integration=integration,
            packages=tuple(sorted(packages)),
            changes=validated.changes,
        )


@dataclass(frozen=True, slots=True)
class PreviewActivationPayload:
    target_id: str
    plan_fingerprint: str
    changes: tuple[CandidateFile, ...]
    system_path: str

    @classmethod
    def from_mapping(cls, raw: Any) -> "PreviewActivationPayload":
        mapping = _mapping(raw, "preview-activation payload")
        _exact_keys(
            mapping,
            {"targetId", "planFingerprint", "changes", "systemPath"},
            "preview-activation payload",
        )
        validated = ValidatePlanPayload.from_mapping(
            {
                "targetId": mapping["targetId"],
                "planFingerprint": mapping["planFingerprint"],
                "changes": mapping["changes"],
            }
        )
        system_path = _string(mapping["systemPath"], "systemPath")
        if not _STORE_PATH.fullmatch(system_path):
            raise HelperProtocolError(
                "invalid-store-path", "systemPath must be one top-level Nix store path"
            )
        return cls(
            target_id=validated.target_id,
            plan_fingerprint=validated.plan_fingerprint,
            changes=validated.changes,
            system_path=system_path,
        )

    def validation_payload(self) -> ValidatePlanPayload:
        return ValidatePlanPayload(
            target_id=self.target_id,
            plan_fingerprint=self.plan_fingerprint,
            changes=self.changes,
        )


@dataclass(frozen=True, slots=True)
class TestActivationPayload:
    target_id: str
    plan_fingerprint: str
    system_path: str
    test_receipt: str

    @classmethod
    def from_mapping(cls, raw: Any) -> "TestActivationPayload":
        mapping = _mapping(raw, "test-activation payload")
        _exact_keys(
            mapping,
            {"targetId", "planFingerprint", "systemPath", "testReceipt"},
            "test-activation payload",
        )
        system_path = _string(mapping["systemPath"], "systemPath")
        if not _STORE_PATH.fullmatch(system_path):
            raise HelperProtocolError(
                "invalid-store-path", "systemPath must be one top-level Nix store path"
            )
        receipt = _string(mapping["testReceipt"], "testReceipt")
        if not _RECEIPT.fullmatch(receipt):
            raise HelperProtocolError("invalid-receipt", "testReceipt has an invalid format")
        return cls(
            target_id=_target_id(mapping["targetId"]),
            plan_fingerprint=_sha256(mapping["planFingerprint"], "planFingerprint"),
            system_path=system_path,
            test_receipt=receipt,
        )


@dataclass(frozen=True, slots=True)
class RecoverTestActivationPayload:
    target_id: str
    session_id: str

    @classmethod
    def from_mapping(cls, raw: Any) -> "RecoverTestActivationPayload":
        mapping = _mapping(raw, "recover-test-activation payload")
        _exact_keys(
            mapping, {"targetId", "sessionId"}, "recover-test-activation payload"
        )
        session_id = _string(mapping["sessionId"], "sessionId")
        if not _TRANSACTION_ID.fullmatch(session_id):
            raise HelperProtocolError("invalid-request", "sessionId has an invalid format")
        return cls(target_id=_target_id(mapping["targetId"]), session_id=session_id)


@dataclass(frozen=True, slots=True)
class ApplyValidatedPlanPayload:
    target_id: str
    plan_fingerprint: str
    validation_receipt: str

    @classmethod
    def from_mapping(cls, raw: Any) -> "ApplyValidatedPlanPayload":
        mapping = _mapping(raw, "apply-validated-plan payload")
        _exact_keys(
            mapping,
            {"targetId", "planFingerprint", "validationReceipt"},
            "apply-validated-plan payload",
        )
        receipt = _string(mapping["validationReceipt"], "validationReceipt")
        if not _RECEIPT.fullmatch(receipt):
            raise HelperProtocolError("invalid-receipt", "validationReceipt has an invalid format")
        return cls(
            target_id=_target_id(mapping["targetId"]),
            plan_fingerprint=_sha256(mapping["planFingerprint"], "planFingerprint"),
            validation_receipt=receipt,
        )


@dataclass(frozen=True, slots=True)
class ApplyValidatedHomeManagerPlanPayload:
    target_id: str
    plan_fingerprint: str
    validation_receipt: str

    @classmethod
    def from_mapping(cls, raw: Any) -> "ApplyValidatedHomeManagerPlanPayload":
        mapping = _mapping(raw, "apply-validated-home-manager-plan payload")
        _exact_keys(
            mapping,
            {"targetId", "planFingerprint", "validationReceipt"},
            "apply-validated-home-manager-plan payload",
        )
        receipt = _string(mapping["validationReceipt"], "validationReceipt")
        if not _RECEIPT.fullmatch(receipt):
            raise HelperProtocolError("invalid-receipt", "validationReceipt has an invalid format")
        return cls(
            target_id=_target_id(mapping["targetId"]),
            plan_fingerprint=_sha256(mapping["planFingerprint"], "planFingerprint"),
            validation_receipt=receipt,
        )


@dataclass(frozen=True, slots=True)
class RecoverTransactionPayload:
    target_id: str
    transaction_id: str

    @classmethod
    def from_mapping(cls, raw: Any) -> "RecoverTransactionPayload":
        mapping = _mapping(raw, "recover-transaction payload")
        _exact_keys(
            mapping, {"targetId", "transactionId"}, "recover-transaction payload"
        )
        transaction_id = _string(mapping["transactionId"], "transactionId")
        if not _TRANSACTION_ID.fullmatch(transaction_id):
            raise HelperProtocolError("invalid-request", "transactionId has an invalid format")
        return cls(target_id=_target_id(mapping["targetId"]), transaction_id=transaction_id)


@dataclass(frozen=True, slots=True)
class RecoverHomeManagerTransactionPayload:
    target_id: str
    transaction_id: str

    @classmethod
    def from_mapping(cls, raw: Any) -> "RecoverHomeManagerTransactionPayload":
        mapping = _mapping(raw, "recover-home-manager-transaction payload")
        _exact_keys(
            mapping,
            {"targetId", "transactionId"},
            "recover-home-manager-transaction payload",
        )
        transaction_id = _string(mapping["transactionId"], "transactionId")
        if not _TRANSACTION_ID.fullmatch(transaction_id):
            raise HelperProtocolError("invalid-request", "transactionId has an invalid format")
        return cls(target_id=_target_id(mapping["targetId"]), transaction_id=transaction_id)


def validate_empty_payload(raw: Any) -> None:
    mapping = _mapping(raw, "capabilities payload")
    _exact_keys(mapping, set(), "capabilities payload")


def response_mapping(
    request_id: str,
    *,
    status: str,
    result: Mapping[str, Any] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": PROTOCOL_VERSION,
        "requestId": request_id,
        "status": status,
        "result": dict(result) if result is not None else None,
        "error": (
            {"code": error_code, "message": error_message}
            if error_code and error_message
            else None
        ),
    }
