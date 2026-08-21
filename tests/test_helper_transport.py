import hashlib
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest

from nix_control_manager.adoption import plan_adoption
from nix_control_manager.candidate import plan_identity
from nix_control_manager.fixture_helper_backend import FixtureWorkflowHelperBackend
from nix_control_manager.helper_service import (
    APPLY_ACTION_ID,
    HelperDispatcher,
    HelperTarget,
    MockPolkitAuthorizer,
    RecordingMockBackend,
)
from nix_control_manager.helper_transport import UnixJsonHelperServer, send_unix_request
from nix_control_manager.transaction import initialize_transaction_fixture


class TransportResilienceTests(unittest.TestCase):
    def test_disconnected_client_does_not_terminate_helper(self) -> None:
        class AbandonedConnection:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def sendall(self, encoded):
                raise BrokenPipeError("caller disconnected")

        class Listener:
            def accept(self):
                return AbandonedConnection(), None

        class Dispatcher:
            def handle(self, request, *, peer):
                return {"status": "ok", "requestId": request["requestId"]}

        server = object.__new__(UnixJsonHelperServer)
        server._socket = Listener()
        server.dispatcher = Dispatcher()
        server._peer_identity = lambda connection: object()
        server._read_frame = lambda connection: (
            b'{"requestId":"abandoned-client"}'
        )

        self.assertTrue(server.handle_once())


@unittest.skipUnless(
    os.name == "posix" and hasattr(socket, "SO_PEERCRED"),
    "Linux SO_PEERCRED is required",
)
class UnixHelperTransportTests(unittest.TestCase):
    @staticmethod
    def _passing_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "/nix/store/fake.drv\n", "")

    @staticmethod
    def _fake_which(name: str) -> str:
        return f"/tools/{name}"

    @staticmethod
    def _request(operation: str, payload: dict, request_id: str) -> dict:
        return {
            "schemaVersion": 1,
            "requestId": request_id,
            "operation": operation,
            "payload": payload,
        }

    def test_transport_uses_kernel_peer_uid_and_leaves_target_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            target_root = directory / "never-written-target"
            socket_path = directory / "helper.sock"
            backend = RecordingMockBackend()
            dispatcher = HelperDispatcher(
                targets=(
                    HelperTarget(
                        target_id="fixture",
                        configuration_root=target_root,
                        allowed_relative_paths=frozenset({"ncm/state.json"}),
                    ),
                ),
                authorizer=MockPolkitAuthorizer(),
                backend=backend,
            )
            stop = threading.Event()
            with UnixJsonHelperServer(socket_path, dispatcher) as server:
                thread = threading.Thread(
                    target=server.serve_until, args=(stop,), daemon=True
                )
                thread.start()
                candidate = "{}\n"
                response = send_unix_request(
                    socket_path,
                    {
                        "schemaVersion": 1,
                        "requestId": "transport-001",
                        "operation": "validate-plan",
                        "payload": {
                            "targetId": "fixture",
                            "planFingerprint": "2" * 64,
                            "changes": [
                                {
                                    "relativePath": "ncm/state.json",
                                    "action": "modify",
                                    "previousSha256": "1" * 64,
                                    "candidateSha256": hashlib.sha256(
                                        candidate.encode("utf-8")
                                    ).hexdigest(),
                                    "candidate": candidate,
                                }
                            ],
                        },
                    },
                )
                stop.set()
                thread.join(timeout=2)

                self.assertEqual(response["status"], "ok")
                self.assertEqual(backend.validate_calls[0][2], os.getuid())
                self.assertEqual(socket_path.stat().st_mode & 0o777, 0o600)
                self.assertFalse(target_root.exists())
            self.assertFalse(socket_path.exists())

    def test_inherited_socket_is_closed_but_never_unlinked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            socket_path = directory / "systemd-owned.sock"
            inherited = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            inherited.bind(str(socket_path))
            inherited.listen(2)
            dispatcher = HelperDispatcher(
                targets=(
                    HelperTarget(
                        target_id="fixture",
                        configuration_root=directory / "target",
                        allowed_relative_paths=frozenset({"ncm/state.json"}),
                    ),
                ),
                authorizer=MockPolkitAuthorizer(),
                backend=RecordingMockBackend(),
            )

            with UnixJsonHelperServer(
                socket_path, dispatcher, inherited_socket=inherited
            ):
                self.assertTrue(socket_path.exists())

            self.assertTrue(socket_path.exists())
            socket_path.unlink()

    def test_from_systemd_adopts_fd_three_and_clears_activation_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            socket_path = directory / "activated.sock"
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(str(socket_path))
            listener.listen(2)
            pid = os.fork()
            if pid == 0:
                try:
                    descriptor = listener.fileno()
                    if descriptor != 3:
                        os.dup2(descriptor, 3)
                        listener.close()
                    else:
                        listener.detach()
                    os.environ["LISTEN_PID"] = str(os.getpid())
                    os.environ["LISTEN_FDS"] = "1"
                    os.environ["LISTEN_FDNAMES"] = "helper"
                    dispatcher = HelperDispatcher(
                        targets=(
                            HelperTarget(
                                target_id="fixture",
                                configuration_root=directory / "target",
                                allowed_relative_paths=frozenset({"ncm/state.json"}),
                            ),
                        ),
                        authorizer=MockPolkitAuthorizer(),
                        backend=RecordingMockBackend(),
                    )
                    with UnixJsonHelperServer.from_systemd(
                        socket_path, dispatcher
                    ) as server:
                        if any(
                            name in os.environ
                            for name in ("LISTEN_PID", "LISTEN_FDS", "LISTEN_FDNAMES")
                        ):
                            os._exit(4)
                        if not server.handle_once():
                            os._exit(5)
                    os._exit(0)
                except Exception:
                    os._exit(6)

            listener.close()
            response = send_unix_request(
                socket_path,
                self._request("capabilities", {}, "activation-check"),
            )
            _, status = os.waitpid(pid, 0)

            self.assertEqual(response["status"], "ok")
            self.assertEqual(os.waitstatus_to_exitcode(status), 0)
            self.assertTrue(socket_path.exists())
            socket_path.unlink()

    def test_transport_runs_the_complete_fixture_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            root = directory / "configuration-root"
            journal = directory / "journals"
            socket_path = directory / "helper.sock"
            initialize_transaction_fixture(root)
            (root / "configuration.nix").write_text(
                "{ ... }:\n\n{\n  imports = [\n"
                "    ./hardware-configuration.nix\n  ];\n}\n",
                encoding="utf-8",
            )
            (root / "hardware-configuration.nix").write_text(
                "{ ... }: { }\n", encoding="utf-8"
            )
            plan = plan_adoption(root)
            fingerprint, _ = plan_identity(plan, None)
            authorizer = MockPolkitAuthorizer(
                allowed={(os.getuid(), APPLY_ACTION_ID)}
            )
            dispatcher = HelperDispatcher(
                targets=(
                    HelperTarget(
                        target_id="fixture",
                        configuration_root=root,
                        journal_root=journal,
                        allowed_relative_paths=frozenset(
                            change.relative_path for change in plan.changes
                        ),
                    ),
                ),
                authorizer=authorizer,
                backend=FixtureWorkflowHelperBackend(
                    runner=self._passing_runner,
                    which=self._fake_which,
                ),
            )
            stop = threading.Event()
            with UnixJsonHelperServer(socket_path, dispatcher) as server:
                thread = threading.Thread(
                    target=server.serve_until, args=(stop,), daemon=True
                )
                thread.start()
                validated = send_unix_request(
                    socket_path,
                    self._request(
                        "validate-plan",
                        {
                            "targetId": "fixture",
                            "planFingerprint": fingerprint,
                            "changes": [
                                {
                                    "relativePath": change.relative_path,
                                    "action": change.action,
                                    "previousSha256": change.previous_sha256,
                                    "candidateSha256": change.candidate_sha256,
                                    "candidate": change.candidate,
                                }
                                for change in plan.changes
                            ],
                        },
                        "transport-validate",
                    ),
                )
                self.assertEqual(validated["status"], "ok")
                applied = send_unix_request(
                    socket_path,
                    self._request(
                        "apply-validated-plan",
                        {
                            "targetId": "fixture",
                            "planFingerprint": fingerprint,
                            "validationReceipt": validated["result"][
                                "validationReceipt"
                            ],
                        },
                        "transport-apply",
                    ),
                )
                stop.set()
                thread.join(timeout=2)

                self.assertEqual(applied["status"], "ok")
                self.assertEqual(applied["result"]["state"], "committed")
                self.assertEqual(
                    applied["result"]["filesWritten"], len(plan.changes)
                )
                self.assertEqual(plan_adoption(root).status, "no-changes")
                self.assertEqual(authorizer.calls[0][1], os.getuid())
                self.assertEqual(len(list(journal.glob("*/manifest.json"))), 1)


if __name__ == "__main__":
    unittest.main()
