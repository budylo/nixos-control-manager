from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
from typing import Mapping, Sequence

from .helper_service import (
    APPLY_ACTION_ID,
    COMMIT_TESTED_SYSTEM_ACTION_ID,
    HOME_MANAGER_APPLY_ACTION_ID,
    HOME_MANAGER_RECOVER_ACTION_ID,
    MANAGED_APPLY_ACTION_ID,
    MANAGED_RECOVER_ACTION_ID,
    PREVIEW_ACTIVATION_ACTION_ID,
    RECOVER_TEST_ACTIVATION_ACTION_ID,
    RECOVER_ACTION_ID,
    ROLLBACK_COMMITTED_SYSTEM_ACTION_ID,
    TEST_ACTIVATION_ACTION_ID,
    PeerIdentity,
)


_DETAIL_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9.-]{0,63}$")
_DETAIL_VALUE = re.compile(r"^[A-Za-z0-9._@:/-]{1,256}$")
_ACTIONS = frozenset(
    {
        APPLY_ACTION_ID,
        COMMIT_TESTED_SYSTEM_ACTION_ID,
        HOME_MANAGER_APPLY_ACTION_ID,
        HOME_MANAGER_RECOVER_ACTION_ID,
        MANAGED_APPLY_ACTION_ID,
        MANAGED_RECOVER_ACTION_ID,
        PREVIEW_ACTIVATION_ACTION_ID,
        RECOVER_ACTION_ID,
        TEST_ACTIVATION_ACTION_ID,
        RECOVER_TEST_ACTIVATION_ACTION_ID,
        ROLLBACK_COMMITTED_SYSTEM_ACTION_ID,
    }
)


class PolkitAuthorizer:
    """Authorize a kernel-identified socket peer with race-safe pkcheck input."""

    def __init__(
        self,
        pkcheck_path: Path,
        *,
        proc_root: Path = Path("/proc"),
        timeout: int = 300,
        runner=subprocess.run,
    ) -> None:
        executable = pkcheck_path.expanduser().resolve()
        if (
            not executable.is_file()
            or not executable.is_absolute()
            or (os.name == "posix" and not os.access(executable, os.X_OK))
        ):
            raise ValueError(f"pkcheck executable is unavailable: {executable}")
        if timeout < 1 or timeout > 900:
            raise ValueError("Polkit timeout must be between 1 and 900 seconds")
        self.pkcheck_path = executable
        self.proc_root = proc_root.expanduser().resolve()
        self.timeout = timeout
        self.runner = runner

    def _process_subject(self, peer: PeerIdentity) -> str | None:
        if peer.pid is None:
            return None
        process_root = self.proc_root / str(peer.pid)
        try:
            stat_line = (process_root / "stat").read_text(encoding="utf-8").strip()
            status_lines = (process_root / "status").read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        closing = stat_line.rfind(")")
        if closing < 0 or not stat_line.startswith(f"{peer.pid} ("):
            return None
        fields: Sequence[str] = stat_line[closing + 1 :].split()
        if len(fields) <= 19 or not fields[19].isdigit():
            return None
        uid_line = next((line for line in status_lines if line.startswith("Uid:")), None)
        if uid_line is None:
            return None
        uid_fields = uid_line.split()
        if len(uid_fields) < 2 or not uid_fields[1].isdigit():
            return None
        real_uid = int(uid_fields[1])
        if real_uid != peer.uid:
            return None
        return f"{peer.pid},{fields[19]},{real_uid}"

    def authorize(
        self, action_id: str, peer: PeerIdentity, details: Mapping[str, str]
    ) -> bool:
        if action_id not in _ACTIONS:
            return False
        subject = self._process_subject(peer)
        if subject is None:
            return False
        command = [
            str(self.pkcheck_path),
            "--action-id",
            action_id,
            "--process",
            subject,
            "--allow-user-interaction",
        ]
        for key, value in sorted(details.items()):
            if not _DETAIL_KEY.fullmatch(key) or not _DETAIL_VALUE.fullmatch(value):
                return False
            command.extend(("--detail", key, value))
        try:
            completed = self.runner(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return completed.returncode == 0
