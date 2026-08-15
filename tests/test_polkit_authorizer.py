from pathlib import Path
import subprocess
import tempfile
import unittest

from nix_control_manager.helper_service import (
    APPLY_ACTION_ID,
    HOME_MANAGER_APPLY_ACTION_ID,
    HOME_MANAGER_RECOVER_ACTION_ID,
    PeerIdentity,
)
from nix_control_manager.polkit_authorizer import PolkitAuthorizer


class PolkitAuthorizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.executable = root / "pkcheck"
        self.executable.write_text("test executable\n", encoding="utf-8")
        self.executable.chmod(0o755)
        self.proc = root / "proc"
        process = self.proc / "4321"
        process.mkdir(parents=True)
        fields = ["S", *("0" for _ in range(18)), "987654", "0"]
        (process / "stat").write_text(
            f"4321 (client with spaces) {' '.join(fields)}\n", encoding="utf-8"
        )
        (process / "status").write_text(
            "Name:\tclient\nUid:\t1000\t1000\t1000\t1000\n", encoding="utf-8"
        )
        self.commands: list[list[str]] = []

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def passing_runner(self, command, **kwargs):
        self.commands.append(list(command))
        return subprocess.CompletedProcess(command, 0, "", "")

    def test_uses_pid_start_time_and_kernel_uid_without_a_shell(self) -> None:
        authorizer = PolkitAuthorizer(
            self.executable, proc_root=self.proc, runner=self.passing_runner
        )

        authorized = authorizer.authorize(
            APPLY_ACTION_ID,
            PeerIdentity(pid=4321, uid=1000, gid=100),
            {"targetId": "fixture", "planFingerprint": "a" * 64},
        )

        self.assertTrue(authorized)
        command = self.commands[0]
        self.assertEqual(command[0], str(self.executable.resolve()))
        self.assertEqual(command[command.index("--process") + 1], "4321,987654,1000")
        self.assertIn("--allow-user-interaction", command)
        self.assertNotIn("--enable-internal-agent", command)

    def test_denies_uid_mismatch_missing_pid_and_unknown_action(self) -> None:
        authorizer = PolkitAuthorizer(
            self.executable, proc_root=self.proc, runner=self.passing_runner
        )

        self.assertFalse(
            authorizer.authorize(
                APPLY_ACTION_ID, PeerIdentity(pid=4321, uid=1001), {"targetId": "fixture"}
            )
        )
        self.assertFalse(
            authorizer.authorize(
                APPLY_ACTION_ID, PeerIdentity(uid=1000), {"targetId": "fixture"}
            )
        )
        self.assertFalse(
            authorizer.authorize(
                "org.example.unknown",
                PeerIdentity(pid=4321, uid=1000),
                {"targetId": "fixture"},
            )
        )
        self.assertEqual(self.commands, [])

    def test_accepts_separate_home_manager_actions_and_user_detail(self) -> None:
        authorizer = PolkitAuthorizer(
            self.executable, proc_root=self.proc, runner=self.passing_runner
        )

        for action in (
            HOME_MANAGER_APPLY_ACTION_ID,
            HOME_MANAGER_RECOVER_ACTION_ID,
        ):
            self.assertTrue(
                authorizer.authorize(
                    action,
                    PeerIdentity(pid=4321, uid=1000),
                    {"targetId": "fixture", "username": "alice@laptop"},
                )
            )
        self.assertEqual(len(self.commands), 2)

    def test_denies_invalid_details_and_pkcheck_failure(self) -> None:
        authorizer = PolkitAuthorizer(
            self.executable, proc_root=self.proc, runner=self.passing_runner
        )
        self.assertFalse(
            authorizer.authorize(
                APPLY_ACTION_ID,
                PeerIdentity(pid=4321, uid=1000),
                {"bad key": "fixture"},
            )
        )
        self.assertEqual(self.commands, [])

        def denied_runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 2, "", "no agent")

        denied = PolkitAuthorizer(
            self.executable, proc_root=self.proc, runner=denied_runner
        )
        self.assertFalse(
            denied.authorize(
                APPLY_ACTION_ID,
                PeerIdentity(pid=4321, uid=1000),
                {"targetId": "fixture"},
            )
        )


if __name__ == "__main__":
    unittest.main()
