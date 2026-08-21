from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import stat
import struct
import threading
from typing import Any

from .helper_protocol import MAX_REQUEST_BYTES, response_mapping
from .helper_service import HelperDispatcher, PeerIdentity


class UnixJsonHelperServer:
    """Linux test transport. The future production socket will be systemd-owned."""

    def __init__(
        self,
        socket_path: Path,
        dispatcher: HelperDispatcher,
        *,
        inherited_socket: socket.socket | None = None,
    ) -> None:
        if not hasattr(socket, "AF_UNIX") or not hasattr(socket, "SO_PEERCRED"):
            raise RuntimeError("Unix peer credentials are unavailable on this platform")
        self.socket_path = socket_path.expanduser().resolve()
        self.dispatcher = dispatcher
        self._owns_socket_path = inherited_socket is None
        if inherited_socket is None:
            if self.socket_path.exists() or self.socket_path.is_symlink():
                raise FileExistsError(
                    f"Refusing to replace existing socket path: {self.socket_path}"
                )
            self.socket_path.parent.mkdir(parents=True, exist_ok=True)
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.bind(str(self.socket_path))
            self.socket_path.chmod(0o600)
            self._socket.listen(8)
        else:
            if inherited_socket.family != socket.AF_UNIX:
                raise RuntimeError("The inherited helper socket is not AF_UNIX")
            if inherited_socket.type & socket.SOCK_STREAM != socket.SOCK_STREAM:
                raise RuntimeError("The inherited helper socket is not SOCK_STREAM")
            if inherited_socket.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) != 1:
                raise RuntimeError("The inherited helper socket is not listening")
            inherited_path = inherited_socket.getsockname()
            if not isinstance(inherited_path, str) or Path(inherited_path).resolve() != self.socket_path:
                raise RuntimeError("The inherited helper socket path does not match configuration")
            self._socket = inherited_socket
        self._socket.settimeout(0.2)
        self._socket_inode = self.socket_path.stat().st_ino

    @classmethod
    def from_systemd(
        cls, socket_path: Path, dispatcher: HelperDispatcher
    ) -> "UnixJsonHelperServer":
        listen_pid = os.environ.get("LISTEN_PID")
        listen_fds = os.environ.get("LISTEN_FDS")
        if listen_pid != str(os.getpid()) or listen_fds != "1":
            raise RuntimeError("Exactly one systemd socket descriptor is required")
        inherited = socket.socket(fileno=3)
        try:
            server = cls(socket_path, dispatcher, inherited_socket=inherited)
        except Exception:
            inherited.close()
            raise
        for variable in ("LISTEN_PID", "LISTEN_FDS", "LISTEN_FDNAMES"):
            os.environ.pop(variable, None)
        return server

    def close(self) -> None:
        self._socket.close()
        try:
            metadata = self.socket_path.lstat()
            if (
                self._owns_socket_path
                and stat.S_ISSOCK(metadata.st_mode)
                and metadata.st_ino == self._socket_inode
            ):
                self.socket_path.unlink()
        except FileNotFoundError:
            pass

    def __enter__(self) -> "UnixJsonHelperServer":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @staticmethod
    def _peer_identity(connection: socket.socket) -> PeerIdentity:
        size = struct.calcsize("3i")
        credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, size)
        pid, uid, gid = struct.unpack("3i", credentials)
        return PeerIdentity(pid=pid, uid=uid, gid=gid)

    @staticmethod
    def _read_frame(connection: socket.socket) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = connection.recv(min(65_536, MAX_REQUEST_BYTES + 1 - total))
            if not chunk:
                break
            newline = chunk.find(b"\n")
            if newline >= 0:
                chunks.append(chunk[:newline])
                total += newline
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_REQUEST_BYTES:
                raise ValueError("request-too-large")
        return b"".join(chunks)

    def handle_once(self) -> bool:
        try:
            connection, _ = self._socket.accept()
        except TimeoutError:
            return False
        with connection:
            try:
                peer = self._peer_identity(connection)
                frame = self._read_frame(connection)
                if not frame:
                    raise ValueError("empty-request")
                request = json.loads(frame.decode("utf-8"))
                response = self.dispatcher.handle(request, peer=peer)
            except UnicodeDecodeError:
                response = response_mapping(
                    "unknown-request",
                    status="error",
                    error_code="invalid-json",
                    error_message="Request must be UTF-8 JSON",
                )
            except json.JSONDecodeError:
                response = response_mapping(
                    "unknown-request",
                    status="error",
                    error_code="invalid-json",
                    error_message="Request is not valid JSON",
                )
            except ValueError as error:
                code = "request-too-large" if str(error) == "request-too-large" else "invalid-request"
                response = response_mapping(
                    "unknown-request",
                    status="error",
                    error_code=code,
                    error_message="The request frame is invalid",
                )
            encoded = (json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8")
            try:
                connection.sendall(encoded)
            except OSError:
                # The privileged operation may have completed after its local
                # caller disconnected (for example while user units reload).
                # The signed journal remains authoritative; one abandoned
                # response must never terminate the system helper daemon.
                pass
        return True

    def serve_until(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            self.handle_once()


def send_unix_request(
    socket_path: Path,
    request: dict[str, Any],
    *,
    timeout: float = 5.0,
) -> dict[str, Any]:
    encoded = (json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_REQUEST_BYTES:
        raise ValueError("Request exceeds the helper protocol limit")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        connection.connect(str(socket_path))
        connection.sendall(encoded)
        chunks: list[bytes] = []
        while True:
            chunk = connection.recv(65_536)
            if not chunk:
                break
            chunks.append(chunk)
            if b"\n" in chunk:
                break
    raw = b"".join(chunks).split(b"\n", 1)[0]
    return json.loads(raw.decode("utf-8"))
