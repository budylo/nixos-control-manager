import os
from dataclasses import replace
from pathlib import Path
import subprocess
import tempfile
import unittest

from nix_control_manager.activation_session import (
    ActivationSession,
    ActivationSessionError,
    ActivationSessionStore,
    transition_activation_session,
)


@unittest.skipUnless(os.name == "posix", "POSIX ownership and locking required")
@unittest.skipUnless(
    os.environ.get("NCM_TEST_CANDIDATE_SYSTEM")
    and os.environ.get("NCM_TEST_PREVIOUS_SYSTEM"),
    "Nix store transition fixtures are required",
)
class ActivationTransitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.journal = self.root / "journal"
        self.journal.mkdir(mode=0o700)
        self.journal.chmod(0o700)
        self.current = self.root / "current-system"
        self.profile = self.root / "system-profile"
        self.candidate = os.environ["NCM_TEST_CANDIDATE_SYSTEM"]
        self.previous = os.environ["NCM_TEST_PREVIOUS_SYSTEM"]
        self.current.symlink_to(self.candidate)
        self.profile.symlink_to(self.previous)
        self.session = ActivationSession(
            session_id="a" * 24,
            state="commit-prepared",
            target_id="control",
            peer_uid=os.geteuid(),
            plan_fingerprint="b" * 64,
            candidate_system_path=self.candidate,
            previous_system_path=self.previous,
            created_at=100,
            recovery_deadline=400,
        )
        self.store = ActivationSessionStore(self.journal)
        with self.store.lock():
            self.store.write(self.session, create=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _replace_link(link: Path, destination: str) -> None:
        link.unlink(missing_ok=True)
        link.symlink_to(destination)

    def runner(self, command, **_kwargs):
        if command[0] == "/tools/systemctl":
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[0] == "/tools/nix-env":
            self._replace_link(self.profile, command[-1])
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[-1] == "switch":
            destination = str(Path(command[0]).parents[1])
            self._replace_link(self.current, destination)
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(f"Unexpected command: {command}")

    @staticmethod
    def which(name: str) -> str | None:
        return f"/tools/{name}" if name in {"systemctl", "nix-env"} else None

    def test_commit_then_rollback_reaches_only_journaled_store_paths(self) -> None:
        committed = transition_activation_session(
            self.journal,
            self.session.session_id,
            mode="commit",
            runner=self.runner,
            which=self.which,
            current_link=self.current,
            profile_link=self.profile,
        )
        self.assertEqual(committed["status"], "committed")
        self.assertEqual(str(self.current.resolve()), self.candidate)
        self.assertEqual(str(self.profile.resolve()), self.candidate)

        with self.store.lock():
            current = self.store.load(self.session.session_id)
            self.store.write(replace(current, state="rollback-prepared"))
        rolled_back = transition_activation_session(
            self.journal,
            self.session.session_id,
            mode="rollback",
            runner=self.runner,
            which=self.which,
            current_link=self.current,
            profile_link=self.profile,
        )
        self.assertEqual(rolled_back["status"], "rolled-back")
        self.assertEqual(str(self.current.resolve()), self.previous)
        self.assertEqual(str(self.profile.resolve()), self.previous)

    def test_failed_commit_compensates_to_previous_system(self) -> None:
        candidate_failed = False

        def failing_runner(command, **kwargs):
            nonlocal candidate_failed
            if command[-1] == "switch" and str(command[0]).startswith(self.candidate):
                candidate_failed = True
                return subprocess.CompletedProcess(command, 1, "", "candidate failed")
            return self.runner(command, **kwargs)

        with self.assertRaisesRegex(ActivationSessionError, "compensation succeeded"):
            transition_activation_session(
                self.journal,
                self.session.session_id,
                mode="commit",
                runner=failing_runner,
                which=self.which,
                current_link=self.current,
                profile_link=self.profile,
            )
        self.assertTrue(candidate_failed)
        with self.store.lock():
            recovered = self.store.load(self.session.session_id)
        self.assertEqual(recovered.state, "recovered")
        self.assertEqual(str(self.current.resolve()), self.previous)
        self.assertEqual(str(self.profile.resolve()), self.previous)


if __name__ == "__main__":
    unittest.main()
