from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import struct

from nix_control_manager.helper_client import build_activation_preview_request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--system-path", required=True)
    parser.add_argument("--plan-fingerprint", required=True)
    arguments = parser.parse_args()

    request = build_activation_preview_request(
        arguments.config_root,
        target_id=arguments.target,
        flake_target=None,
        system_path=arguments.system_path,
        expected_fingerprint=arguments.plan_fingerprint,
    )
    frame = (json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8")

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(arguments.socket))
        connection.sendall(frame)
        # Close with a reset so the helper's eventual response cannot be
        # delivered after the caller has abandoned the request.
        connection.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_LINGER,
            struct.pack("ii", 1, 0),
        )


if __name__ == "__main__":
    main()
