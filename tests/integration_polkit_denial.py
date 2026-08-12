"""Manual Linux integration: the real pkcheck fails closed without installed policy."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

from nix_control_manager.helper_service import APPLY_ACTION_ID, PeerIdentity
from nix_control_manager.polkit_authorizer import PolkitAuthorizer


def main() -> int:
    executable = shutil.which("pkcheck")
    if executable is None:
        raise RuntimeError("pkcheck is unavailable")
    peer = PeerIdentity(pid=os.getpid(), uid=os.getuid(), gid=os.getgid())
    authorized = PolkitAuthorizer(Path(executable), timeout=10).authorize(
        APPLY_ACTION_ID,
        peer,
        {"targetId": "fixture", "planFingerprint": "0" * 64},
    )
    print(
        json.dumps(
            {
                "pkcheck": executable,
                "peerPid": peer.pid,
                "peerUid": peer.uid,
                "authorized": authorized,
                "expected": "denied because the policy/service is not installed",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 2 if authorized else 0


if __name__ == "__main__":
    raise SystemExit(main())
