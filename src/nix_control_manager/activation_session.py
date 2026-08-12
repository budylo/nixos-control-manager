from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import time
from typing import Any, Callable, Iterator, Mapping


_SESSION_ID = re.compile(r"^[0-9a-f]{24}$")
_STORE_PATH = re.compile(r"^/nix/store/[0-9a-z]{32}-[^/\s]+$")
_STATES = frozenset(
    {
        "prepared",
        "activating",
        "active",
        "recovering",
        "recovered",
        "activation-failed",
        "recovery-required",
    }
)


class ActivationSessionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ActivationSession:
    session_id: str
    state: str
    target_id: str
    peer_uid: int
    plan_fingerprint: str
    candidate_system_path: str
    previous_system_path: str
    created_at: int
    recovery_deadline: int
    activation_exit_code: int | None = None
    recovery_exit_code: int | None = None

    def __post_init__(self) -> None:
        if not _SESSION_ID.fullmatch(self.session_id):
            raise ActivationSessionError("Invalid activation session identifier")
        if self.state not in _STATES:
            raise ActivationSessionError("Invalid activation session state")
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", self.target_id):
            raise ActivationSessionError("Invalid activation target identifier")
        if isinstance(self.peer_uid, bool) or not isinstance(self.peer_uid, int) or self.peer_uid < 0:
            raise ActivationSessionError("Invalid activation session UID")
        if not re.fullmatch(r"[0-9a-f]{64}", self.plan_fingerprint):
            raise ActivationSessionError("Invalid activation plan fingerprint")
        for path in (self.candidate_system_path, self.previous_system_path):
            if not _STORE_PATH.fullmatch(path):
                raise ActivationSessionError("Activation sessions require exact Nix store paths")
        for value in (self.created_at, self.recovery_deadline):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ActivationSessionError("Invalid activation session timestamp")
        for value in (self.activation_exit_code, self.recovery_exit_code):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise ActivationSessionError("Invalid activation command exit code")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "sessionId": self.session_id,
            "state": self.state,
            "targetId": self.target_id,
            "peerUid": self.peer_uid,
            "planFingerprint": self.plan_fingerprint,
            "candidateSystemPath": self.candidate_system_path,
            "previousSystemPath": self.previous_system_path,
            "createdAt": self.created_at,
            "recoveryDeadline": self.recovery_deadline,
            "activationExitCode": self.activation_exit_code,
            "recoveryExitCode": self.recovery_exit_code,
        }

    @classmethod
    def from_mapping(cls, raw: Any) -> "ActivationSession":
        if not isinstance(raw, Mapping):
            raise ActivationSessionError("Activation journal entry must be an object")
        expected = {
            "schemaVersion",
            "sessionId",
            "state",
            "targetId",
            "peerUid",
            "planFingerprint",
            "candidateSystemPath",
            "previousSystemPath",
            "createdAt",
            "recoveryDeadline",
            "activationExitCode",
            "recoveryExitCode",
        }
        if set(raw) != expected or raw.get("schemaVersion") != 1:
            raise ActivationSessionError("Activation journal schema mismatch")
        try:
            return cls(
                session_id=raw["sessionId"],
                state=raw["state"],
                target_id=raw["targetId"],
                peer_uid=raw["peerUid"],
                plan_fingerprint=raw["planFingerprint"],
                candidate_system_path=raw["candidateSystemPath"],
                previous_system_path=raw["previousSystemPath"],
                created_at=raw["createdAt"],
                recovery_deadline=raw["recoveryDeadline"],
                activation_exit_code=raw["activationExitCode"],
                recovery_exit_code=raw["recoveryExitCode"],
            )
        except (KeyError, TypeError) as error:
            raise ActivationSessionError("Activation journal contains invalid values") from error


class ActivationSessionStore:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def _require_secure_root(self) -> None:
        try:
            info = self.root.lstat()
        except OSError as error:
            raise ActivationSessionError(f"Activation journal is unavailable: {error}") from error
        if not stat.S_ISDIR(info.st_mode) or self.root.is_symlink():
            raise ActivationSessionError("Activation journal must be a real directory")
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise ActivationSessionError("Activation journal must not be group/world accessible")
        if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
            raise ActivationSessionError("Activation journal owner does not match the helper")

    def path(self, session_id: str) -> Path:
        if not _SESSION_ID.fullmatch(session_id):
            raise ActivationSessionError("Invalid activation session identifier")
        return self.root / f"{session_id}.json"

    @contextmanager
    def lock(self) -> Iterator[None]:
        self._require_secure_root()
        if os.name != "posix":
            raise ActivationSessionError("Activation journals require POSIX file locking")
        import fcntl

        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self.root / ".lock", flags, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def load(self, session_id: str) -> ActivationSession:
        self._require_secure_root()
        path = self.path(session_id)
        try:
            if path.is_symlink() or not path.is_file():
                raise ActivationSessionError("Activation session does not exist")
            return ActivationSession.from_mapping(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as error:
            raise ActivationSessionError("Activation journal is not valid JSON") from error
        except OSError as error:
            raise ActivationSessionError(f"Could not read activation journal: {error}") from error

    def unfinished(self) -> tuple[ActivationSession, ...]:
        self._require_secure_root()
        sessions: list[ActivationSession] = []
        for path in sorted(self.root.glob("*.json")):
            if path.is_symlink() or not _SESSION_ID.fullmatch(path.stem):
                raise ActivationSessionError("Activation journal contains an unsafe entry")
            session = self.load(path.stem)
            if session.state != "recovered":
                sessions.append(session)
        return tuple(sessions)

    def write(self, session: ActivationSession, *, create: bool = False) -> None:
        self._require_secure_root()
        destination = self.path(session.session_id)
        if create and (destination.exists() or destination.is_symlink()):
            raise ActivationSessionError("Activation session already exists")
        temporary = self.root / f".{session.session_id}.{secrets.token_hex(6)}.tmp"
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o600)
        try:
            content = (json.dumps(session.to_mapping(), sort_keys=True, indent=2) + "\n").encode()
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.close(descriptor)
            descriptor = -1
            os.replace(temporary, destination)
            directory = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


Runner = Callable[..., subprocess.CompletedProcess[str]]


def recover_activation_session(
    journal_root: Path,
    session_id: str,
    *,
    runner: Runner = subprocess.run,
    timeout: int = 300,
) -> dict[str, Any]:
    store = ActivationSessionStore(journal_root)
    with store.lock():
        session = store.load(session_id)
        if session.state == "recovered":
            return {**session.to_mapping(), "currentSystemRestored": True, "idempotent": True}
        if session.state not in {
            "prepared",
            "activating",
            "active",
            "activation-failed",
            "recovery-required",
            "recovering",
        }:
            raise ActivationSessionError(f"Session cannot be recovered from {session.state}")
        previous = Path(session.previous_system_path)
        switch = previous / "bin" / "switch-to-configuration"
        if previous.is_symlink() or not previous.is_dir() or not switch.is_file() or not os.access(switch, os.X_OK):
            raise ActivationSessionError("Previous NixOS system closure is unavailable")
        recovering = replace(session, state="recovering")
        store.write(recovering)
        try:
            completed = runner(
                [str(switch), "test"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=os.environ.copy(),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            store.write(replace(recovering, state="recovery-required"))
            raise ActivationSessionError(f"Recovery command failed: {error}") from error
        current_link = Path("/run/current-system")
        current = str(current_link.resolve()) if current_link.exists() else None
        restored = completed.returncode == 0 and current == session.previous_system_path
        final = replace(
            recovering,
            state="recovered" if restored else "recovery-required",
            recovery_exit_code=completed.returncode,
        )
        store.write(final)
        result = {
            **final.to_mapping(),
            "status": final.state,
            "command": [str(switch), "test"],
            "stdout": (completed.stdout or "")[:64_000],
            "stderr": (completed.stderr or "")[:64_000],
            "currentSystemRestored": restored,
            "testEnabled": True,
            "switchEnabled": False,
            "configurationWriteEnabled": False,
        }
        if not restored:
            raise ActivationSessionError(
                "Automatic recovery did not restore the previous runtime system"
            )
        return result


def recovery_main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="ncm-test-recover")
    parser.add_argument("--journal-root", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--timeout", type=int, default=300)
    arguments = parser.parse_args(argv)
    if os.name != "posix" or not hasattr(os, "geteuid") or os.geteuid() != 0:
        print("ncm-test-recover: root on POSIX is required", file=sys.stderr)
        return 1
    try:
        result = recover_activation_session(
            arguments.journal_root,
            arguments.session_id,
            timeout=arguments.timeout,
        )
    except (ActivationSessionError, ValueError) as error:
        print(f"ncm-test-recover: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0
