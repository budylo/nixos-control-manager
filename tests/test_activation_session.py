import os
from pathlib import Path
import tempfile
import unittest

from nix_control_manager.activation_session import (
    ActivationSession,
    ActivationSessionError,
    ActivationSessionStore,
)


def session(session_id: str = "a" * 24, state: str = "prepared") -> ActivationSession:
    return ActivationSession(
        session_id=session_id,
        state=state,
        target_id="live-test",
        peer_uid=1000,
        plan_fingerprint="b" * 64,
        candidate_system_path="/nix/store/" + "c" * 32 + "-candidate",
        previous_system_path="/nix/store/" + "d" * 32 + "-previous",
        created_at=100,
        recovery_deadline=400,
    )


class ActivationSessionTests(unittest.TestCase):
    def test_schema_is_exact_and_store_paths_are_typed(self) -> None:
        original = session()
        self.assertEqual(
            ActivationSession.from_mapping(original.to_mapping()), original
        )
        extra = original.to_mapping()
        extra["command"] = "switch"
        with self.assertRaisesRegex(ActivationSessionError, "schema"):
            ActivationSession.from_mapping(extra)
        invalid = original.to_mapping()
        invalid["candidateSystemPath"] = "/tmp/candidate"
        with self.assertRaisesRegex(ActivationSessionError, "store paths"):
            ActivationSession.from_mapping(invalid)

    @unittest.skipUnless(os.name == "posix", "POSIX ownership and locking required")
    def test_root_private_journal_is_atomic_and_tracks_unfinished_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "journal"
            root.mkdir(mode=0o700)
            root.chmod(0o700)
            store = ActivationSessionStore(root)
            prepared = session()
            with store.lock():
                store.write(prepared, create=True)
                self.assertEqual(store.load(prepared.session_id), prepared)
                self.assertEqual(store.unfinished(), (prepared,))
                recovered = session(state="recovered")
                store.write(recovered)
                self.assertEqual(store.unfinished(), ())
            self.assertEqual((root / f"{prepared.session_id}.json").stat().st_mode & 0o777, 0o600)

    @unittest.skipUnless(os.name == "posix", "POSIX ownership and locking required")
    def test_journal_rejects_group_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "journal"
            root.mkdir(mode=0o770)
            root.chmod(0o770)
            with self.assertRaisesRegex(ActivationSessionError, "group/world"):
                ActivationSessionStore(root).write(session(), create=True)


if __name__ == "__main__":
    unittest.main()
