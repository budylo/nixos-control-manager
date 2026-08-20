from __future__ import annotations

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import time
from typing import Any, Mapping

from .activation_session import (
    ActivationSession,
    ActivationSessionError,
    ActivationSessionStore,
)

from .candidate import (
    Runner,
    Which,
    effective_flake_target,
    plan_identity,
    validate_adoption,
)
from .helper_backend_common import match_local_adoption_plan
from .helper_protocol import (
    CommitTestedSystemPayload,
    PreviewActivationPayload,
    ValidateHomeManagerPlanPayload,
    ValidatePlanPayload,
)
from .helper_service import (
    HelperBackendError,
    HelperTarget,
    PendingValidatedHomeManagerPlan,
    PendingValidatedManagedPlan,
    PendingValidatedPlan,
)


class LiveReadOnlyHelperBackend:
    """Validate an exact live-target plan without issuing any write capability."""

    def __init__(
        self,
        *,
        timeout: int = 120,
        runner: Runner = subprocess.run,
        which: Which = shutil.which,
    ) -> None:
        if timeout < 1:
            raise ValueError("timeout must be at least one second")
        self.timeout = timeout
        self.runner = runner
        self.which = which

    def validate_plan(
        self, target: HelperTarget, plan: ValidatePlanPayload, peer_uid: int
    ) -> Mapping[str, Any]:
        try:
            match_local_adoption_plan(target, plan, require_fixture=False)
            validation = validate_adoption(
                target.configuration_root,
                flake_target=target.flake_target,
                timeout=self.timeout,
                runner=self.runner,
                which=self.which,
            )
            if (
                validation.status == "passed"
                and validation.plan_fingerprint != plan.plan_fingerprint
            ):
                raise HelperBackendError(
                    "validation-failed",
                    "The validated fingerprint does not match the submitted plan",
                )
        except HelperBackendError:
            raise
        except (OSError, ValueError) as error:
            raise HelperBackendError("validation-failed", str(error)) from error
        result: dict[str, Any] = {
            "status": validation.status,
            "warnings": list(validation.warnings),
            "workingCopyRemoved": validation.working_copy_removed,
            "fixtureOnly": False,
            "liveTarget": True,
            "readOnly": True,
            "applyEnabled": False,
            "activationEnabled": False,
        }
        if validation.status == "passed":
            result["planFingerprint"] = validation.plan_fingerprint
            result["checks"] = [
                {
                    "name": check.name,
                    "status": check.status,
                    "exitCode": check.exit_code,
                    "durationMs": check.duration_ms,
                }
                for check in validation.checks
            ]
        else:
            result["checks"] = [check.to_mapping() for check in validation.checks]
        return result

    def apply_validated_plan(
        self, target: HelperTarget, plan: PendingValidatedPlan, peer_uid: int
    ) -> Mapping[str, Any]:
        raise HelperBackendError(
            "operation-disabled", "Live-target writes are not implemented"
        )

    def recover_transaction(
        self, target: HelperTarget, transaction_id: str, peer_uid: int
    ) -> Mapping[str, Any]:
        raise HelperBackendError(
            "operation-disabled", "Live-target recovery is not implemented"
        )

    def discard_validated_plan(
        self, target: HelperTarget, plan: ValidatePlanPayload, peer_uid: int
    ) -> None:
        return None

    @staticmethod
    def _configuration_digest(root: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(root.rglob("*"), key=lambda item: str(item.relative_to(root))):
            relative = str(path.relative_to(root)).encode("utf-8")
            digest.update(relative + b"\0")
            if path.is_symlink():
                digest.update(b"link\0" + os.readlink(path).encode("utf-8") + b"\0")
            elif path.is_file():
                digest.update(b"file\0" + path.read_bytes() + b"\0")
            elif path.is_dir():
                digest.update(b"dir\0")
            else:
                digest.update(b"other\0")
        return digest.hexdigest()

    def preview_activation(
        self,
        target: HelperTarget,
        payload: PreviewActivationPayload,
        peer_uid: int,
    ) -> Mapping[str, Any]:
        """Run only the verified NixOS dry-activation entrypoint as root."""
        if (
            target.fixture_only
            or target.apply_enabled
            or target.home_manager_apply_enabled
        ):
            raise HelperBackendError(
                "read-only-target-required", "A read-only live target is required"
            )
        switch = self._verified_candidate(target, payload)

        source_before = self._configuration_digest(target.configuration_root)
        current_link = Path("/run/current-system")
        current_before = str(current_link.resolve()) if current_link.exists() else None
        command = [str(switch), "dry-activate"]
        started = time.monotonic()
        try:
            completed = self.runner(
                command,
                cwd=target.configuration_root,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                env=os.environ.copy(),
            )
        except subprocess.TimeoutExpired as error:
            raise HelperBackendError(
                "dry-activate-timed-out",
                f"Dry-activation preview exceeded {self.timeout} seconds",
            ) from error
        except OSError as error:
            raise HelperBackendError("dry-activate-failed", str(error)) from error
        source_after = self._configuration_digest(target.configuration_root)
        current_after = str(current_link.resolve()) if current_link.exists() else None
        if source_before != source_after or current_before != current_after:
            raise HelperBackendError(
                "safety-boundary-violated",
                "Dry-activation preview unexpectedly changed protected system state",
            )
        limit = 64_000
        result = {
            "status": "passed" if completed.returncode == 0 else "failed",
            "systemPath": payload.system_path,
            "planFingerprint": payload.plan_fingerprint,
            "command": command,
            "exitCode": completed.returncode,
            "durationMs": round((time.monotonic() - started) * 1000),
            "stdout": (completed.stdout or "")[:limit],
            "stderr": (completed.stderr or "")[:limit],
            "sourceFilesUnchanged": True,
            "currentSystemUnchanged": True,
            "configurationWriteEnabled": False,
            "activationEnabled": False,
            "testEnabled": False,
            "switchEnabled": False,
            "reportIncomplete": True,
        }
        if completed.returncode != 0:
            raise HelperBackendError(
                "dry-activate-failed",
                f"NixOS dry-activation exited with status {completed.returncode}",
            )
        return result

    def _verified_candidate(
        self, target: HelperTarget, payload: PreviewActivationPayload
    ) -> Path:
        plan = match_local_adoption_plan(
            target, payload.validation_payload(), require_fixture=False
        )
        validation = validate_adoption(
            target.configuration_root,
            flake_target=target.flake_target,
            timeout=self.timeout,
            runner=self.runner,
            which=self.which,
        )
        if validation.status != "passed" or not validation.checks:
            detail = ""
            if validation.checks:
                failed = validation.checks[-1]
                diagnostic = (failed.stderr or failed.stdout).strip()
                if diagnostic:
                    if len(diagnostic) > 6000:
                        diagnostic = diagnostic[:3000] + "\n…\n" + diagnostic[-3000:]
                    detail = f": {diagnostic}"
            raise HelperBackendError(
                "validation-failed",
                f"The exact candidate no longer passes validation{detail}",
            )
        if validation.plan_fingerprint != payload.plan_fingerprint:
            raise HelperBackendError(
                "plan-mismatch", "The adoption plan changed during validation"
            )
        drv_lines = [
            line.strip()
            for line in validation.checks[-1].stdout.splitlines()
            if re.fullmatch(r"/nix/store/[0-9a-z]{32}-[^/\s]+\.drv", line.strip())
        ]
        if len(drv_lines) != 1:
            raise HelperBackendError(
                "output-mismatch", "Validation did not identify one system derivation"
            )
        nix_store = self.which("nix-store")
        if not nix_store:
            raise HelperBackendError("nix-unavailable", "nix-store is unavailable")
        try:
            queried = self.runner(
                [nix_store, "--query", "--outputs", drv_lines[0]],
                cwd=target.configuration_root,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                env=os.environ.copy(),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise HelperBackendError("output-query-failed", str(error)) from error
        outputs = [line.strip() for line in queried.stdout.splitlines() if line.strip()]
        if queried.returncode != 0 or outputs != [payload.system_path]:
            actual = outputs[0] if len(outputs) == 1 else "no single output"
            raise HelperBackendError(
                "output-mismatch",
                "The supplied system path is not the exact validated candidate output "
                f"(expected {payload.system_path}, evaluated {actual}, "
                f"derivation {drv_lines[0]})",
            )
        system_path = Path(payload.system_path)
        switch = system_path / "bin" / "switch-to-configuration"
        if (
            system_path.is_symlink()
            or not system_path.is_dir()
            or not switch.is_file()
            or not os.access(switch, os.X_OK)
        ):
            raise HelperBackendError(
                "invalid-system-closure", "The verified NixOS system closure is unavailable"
            )
        fingerprint, _ = plan_identity(plan, effective_flake_target(plan, target.flake_target))
        if fingerprint != payload.plan_fingerprint:
            raise HelperBackendError("plan-mismatch", "The adoption plan changed during preview")
        return switch

    def _system_tool(self, name: str) -> str:
        path = self.which(name)
        if not path or not Path(path).is_file() or not os.access(path, os.X_OK):
            raise HelperBackendError("system-tool-unavailable", f"{name} is unavailable")
        return path

    def test_activation(
        self,
        target: HelperTarget,
        payload: PreviewActivationPayload,
        peer_uid: int,
    ) -> Mapping[str, Any]:
        if not target.test_activation_enabled or target.test_journal_root is None:
            raise HelperBackendError("operation-disabled", "Test activation is disabled")
        switch = self._verified_candidate(target, payload)
        current_link = Path("/run/current-system")
        profile_link = Path("/nix/var/nix/profiles/system")
        if not current_link.exists() or not profile_link.exists():
            raise HelperBackendError(
                "current-system-unavailable", "The runtime system or boot profile is absent"
            )
        # `test` must never mutate the system profile.  It is therefore the
        # durable recovery anchor even in VM/container environments where the
        # runtime link can point at an instrumentation wrapper.
        previous = str(profile_link.resolve())
        if not re.fullmatch(r"/nix/store/[0-9a-z]{32}-[^/\s]+", previous):
            raise HelperBackendError(
                "current-system-invalid", "The current NixOS system is not one store closure"
            )
        previous_switch = Path(previous) / "bin" / "switch-to-configuration"
        if not previous_switch.is_file() or not os.access(previous_switch, os.X_OK):
            raise HelperBackendError("current-system-invalid", "Recovery entrypoint is unavailable")
        systemd_run = self._system_tool("systemd-run")
        recover = self._system_tool("ncm-test-recover")
        session_id = secrets.token_hex(12)
        created_at = int(time.time())
        session = ActivationSession(
            session_id=session_id,
            state="prepared",
            target_id=target.target_id,
            peer_uid=peer_uid,
            plan_fingerprint=payload.plan_fingerprint,
            candidate_system_path=payload.system_path,
            previous_system_path=previous,
            created_at=created_at,
            recovery_deadline=created_at + target.test_timeout_seconds,
        )
        store = ActivationSessionStore(target.test_journal_root)
        try:
            with store.lock():
                unfinished = store.unfinished()
                if unfinished:
                    raise ActivationSessionError(
                        f"Activation session {unfinished[0].session_id} requires recovery first"
                    )
                store.write(session, create=True)
        except ActivationSessionError as error:
            raise HelperBackendError("activation-journal-failed", str(error)) from error

        rollback_unit = f"ncm-test-rollback-{session_id}"
        schedule = [
            systemd_run,
            "--quiet",
            f"--unit={rollback_unit}",
            f"--on-active={target.test_timeout_seconds}s",
            "--timer-property=AccuracySec=1s",
            "--property=Type=oneshot",
            recover,
            "--journal-root",
            str(target.test_journal_root),
            "--session-id",
            session_id,
            "--timeout",
            str(self.timeout),
        ]
        started = time.monotonic()
        try:
            scheduled = self.runner(
                schedule,
                cwd=target.configuration_root,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                env=os.environ.copy(),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise HelperBackendError("auto-recovery-schedule-failed", str(error)) from error
        if scheduled.returncode != 0:
            try:
                with store.lock():
                    store.write(replace(session, state="recovered"))
            except ActivationSessionError:
                pass
            raise HelperBackendError(
                "auto-recovery-schedule-failed",
                "The automatic recovery timer could not be scheduled",
            )
        activating = replace(session, state="activating")
        try:
            with store.lock():
                store.write(activating)
        except ActivationSessionError as error:
            raise HelperBackendError("activation-journal-failed", str(error)) from error
        activation_unit = f"ncm-test-activate-{session_id}"
        command = [
            systemd_run,
            "--quiet",
            "--wait",
            "--collect",
            "--pipe",
            f"--unit={activation_unit}",
            str(switch),
            "test",
        ]
        try:
            completed = self.runner(
                command,
                cwd=target.configuration_root,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                env=os.environ.copy(),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            try:
                with store.lock():
                    store.write(replace(activating, state="activation-failed"))
            except ActivationSessionError:
                pass
            raise HelperBackendError("test-activation-failed", str(error)) from error
        current = str(current_link.resolve()) if current_link.exists() else None
        succeeded = completed.returncode == 0 and current == payload.system_path
        final = replace(
            activating,
            state="active" if succeeded else "activation-failed",
            activation_exit_code=completed.returncode,
        )
        try:
            with store.lock():
                store.write(final)
        except ActivationSessionError as error:
            raise HelperBackendError("activation-journal-failed", str(error)) from error
        if not succeeded:
            raise HelperBackendError(
                "test-activation-failed",
                "Test activation failed; the scheduled recovery remains armed",
            )
        return {
            "status": "active",
            "sessionId": session_id,
            "systemPath": payload.system_path,
            "previousSystemPath": previous,
            "planFingerprint": payload.plan_fingerprint,
            "command": [str(switch), "test"],
            "exitCode": completed.returncode,
            "durationMs": round((time.monotonic() - started) * 1000),
            "stdout": (completed.stdout or "")[:64_000],
            "stderr": (completed.stderr or "")[:64_000],
            "recoveryDeadline": session.recovery_deadline,
            "autoRecoveryUnit": rollback_unit,
            "autoRecoveryScheduled": True,
            "configurationWriteEnabled": False,
            "testEnabled": True,
            "switchEnabled": False,
            "bootGenerationChanged": False,
        }

    def recover_test_activation(
        self, target: HelperTarget, session_id: str, peer_uid: int
    ) -> Mapping[str, Any]:
        if not target.test_activation_enabled or target.test_journal_root is None:
            raise HelperBackendError("operation-disabled", "Test recovery is disabled")
        store = ActivationSessionStore(target.test_journal_root)
        try:
            with store.lock():
                session = store.load(session_id)
                if session.target_id != target.target_id or session.peer_uid != peer_uid:
                    raise ActivationSessionError("Activation session does not match this user")
                if session.state == "recovered":
                    return {
                        **session.to_mapping(),
                        "status": "recovered",
                        "currentSystemRestored": True,
                        "idempotent": True,
                        "testEnabled": True,
                        "switchEnabled": False,
                        "configurationWriteEnabled": False,
                    }
        except ActivationSessionError as error:
            raise HelperBackendError("test-recovery-failed", str(error)) from error
        systemd_run = self._system_tool("systemd-run")
        recover = self._system_tool("ncm-test-recover")
        command = [
            systemd_run,
            "--quiet",
            "--wait",
            "--collect",
            "--pipe",
            f"--unit=ncm-test-recover-now-{session_id}",
            recover,
            "--journal-root",
            str(target.test_journal_root),
            "--session-id",
            session_id,
            "--timeout",
            str(self.timeout),
        ]
        try:
            completed = self.runner(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                env=os.environ.copy(),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise HelperBackendError("test-recovery-failed", str(error)) from error
        try:
            with store.lock():
                recovered = store.load(session_id)
        except ActivationSessionError as error:
            raise HelperBackendError("test-recovery-failed", str(error)) from error
        if completed.returncode != 0 or recovered.state != "recovered":
            raise HelperBackendError(
                "test-recovery-failed", "The previous runtime system was not restored"
            )
        return {
            **recovered.to_mapping(),
            "status": "recovered",
            "command": [recover, "--journal-root", str(target.test_journal_root), "--session-id", session_id],
            "stdout": (completed.stdout or "")[:64_000],
            "stderr": (completed.stderr or "")[:64_000],
            "currentSystemRestored": True,
            "testEnabled": True,
            "switchEnabled": False,
            "configurationWriteEnabled": False,
        }

    def _schedule_system_transition(
        self,
        target: HelperTarget,
        session: ActivationSession,
        *,
        mode: str,
    ) -> Mapping[str, Any]:
        if target.test_journal_root is None:
            raise HelperBackendError("operation-disabled", "Activation journal is disabled")
        systemd_run = self._system_tool("systemd-run")
        transition = self._system_tool("ncm-system-transition")
        transition_path = os.environ.get("PATH")
        if not transition_path:
            raise HelperBackendError(
                "system-tool-unavailable", "The helper PATH is unavailable"
            )
        unit = f"ncm-system-{mode}-{session.session_id}"
        command = [
            systemd_run,
            "--quiet",
            "--no-block",
            "--collect",
            f"--unit={unit}",
            "--property=Type=oneshot",
            f"--setenv=PATH={transition_path}",
            transition,
            "--journal-root",
            str(target.test_journal_root),
            "--session-id",
            session.session_id,
            "--mode",
            mode,
            "--timeout",
            str(self.timeout),
        ]
        try:
            scheduled = self.runner(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                env=os.environ.copy(),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise HelperBackendError("transition-schedule-failed", str(error)) from error
        if scheduled.returncode != 0:
            raise HelperBackendError(
                "transition-schedule-failed",
                f"The exact system {mode} unit could not be scheduled",
            )
        return {
            **session.to_mapping(),
            "status": "committing" if mode == "commit" else "rolling-back",
            "systemPath": (
                session.candidate_system_path
                if mode == "commit"
                else session.previous_system_path
            ),
            "transitionUnit": unit,
            "switchEnabled": True,
            "rollbackEnabled": True,
            "arbitraryCommandsAccepted": False,
        }

    def commit_tested_system(
        self,
        target: HelperTarget,
        payload: CommitTestedSystemPayload,
        peer_uid: int,
    ) -> Mapping[str, Any]:
        if (
            not target.permanent_switch_enabled
            or not target.test_activation_enabled
            or target.test_journal_root is None
        ):
            raise HelperBackendError("operation-disabled", "Permanent switch is disabled")
        self._verified_candidate(target, payload.preview_payload())
        store = ActivationSessionStore(target.test_journal_root)
        try:
            with store.lock():
                session = store.load(payload.session_id)
                if (
                    session.state != "active"
                    or session.target_id != target.target_id
                    or session.peer_uid != peer_uid
                    or session.plan_fingerprint != payload.plan_fingerprint
                    or session.candidate_system_path != payload.system_path
                ):
                    raise ActivationSessionError(
                        "Only this user's exact active test session can be committed"
                    )
                current = str(Path("/run/current-system").resolve())
                profile = str(Path("/nix/var/nix/profiles/system").resolve())
                if (
                    current != session.candidate_system_path
                    or profile != session.previous_system_path
                ):
                    raise ActivationSessionError(
                        "Runtime or profile changed after the tested activation"
                    )
                prepared = replace(session, state="commit-prepared")
                store.write(prepared)
        except ActivationSessionError as error:
            raise HelperBackendError("commit-precondition-failed", str(error)) from error
        try:
            return self._schedule_system_transition(target, prepared, mode="commit")
        except HelperBackendError:
            try:
                with store.lock():
                    latest = store.load(payload.session_id)
                    if latest.state == "commit-prepared":
                        store.write(replace(latest, state="active"))
            except ActivationSessionError:
                pass
            raise

    def rollback_committed_system(
        self, target: HelperTarget, session_id: str, peer_uid: int
    ) -> Mapping[str, Any]:
        if not target.permanent_switch_enabled or target.test_journal_root is None:
            raise HelperBackendError("operation-disabled", "Generation rollback is disabled")
        store = ActivationSessionStore(target.test_journal_root)
        try:
            with store.lock():
                session = store.load(session_id)
                if (
                    session.state != "committed"
                    or session.target_id != target.target_id
                    or session.peer_uid != peer_uid
                ):
                    raise ActivationSessionError(
                        "Only this user's committed NCM activation can be rolled back"
                    )
                current = str(Path("/run/current-system").resolve())
                profile = str(Path("/nix/var/nix/profiles/system").resolve())
                if (
                    current != session.candidate_system_path
                    or profile != session.candidate_system_path
                ):
                    raise ActivationSessionError(
                        "Current runtime/profile no longer matches the committed session"
                    )
                prepared = replace(session, state="rollback-prepared")
                store.write(prepared)
        except ActivationSessionError as error:
            raise HelperBackendError("rollback-precondition-failed", str(error)) from error
        try:
            return self._schedule_system_transition(target, prepared, mode="rollback")
        except HelperBackendError:
            try:
                with store.lock():
                    latest = store.load(session_id)
                    if latest.state == "rollback-prepared":
                        store.write(replace(latest, state="committed"))
            except ActivationSessionError:
                pass
            raise

    def activation_session_status(
        self, target: HelperTarget, session_id: str, peer_uid: int
    ) -> Mapping[str, Any]:
        if not target.permanent_switch_enabled or target.test_journal_root is None:
            raise HelperBackendError("operation-disabled", "Activation status is disabled")
        try:
            store = ActivationSessionStore(target.test_journal_root)
            with store.lock():
                session = store.load(session_id)
            if session.target_id != target.target_id or session.peer_uid != peer_uid:
                raise ActivationSessionError("Activation session does not match this user")
        except ActivationSessionError as error:
            raise HelperBackendError("activation-status-failed", str(error)) from error
        return {
            **session.to_mapping(),
            "status": session.state,
            "systemPath": (
                session.previous_system_path
                if session.state in {"recovered", "rolled-back"}
                else session.candidate_system_path
            ),
            "switchEnabled": True,
            "rollbackEnabled": session.state == "committed",
            "arbitraryCommandsAccepted": False,
        }


class RoutingHelperBackend:
    def __init__(
        self, *, fixture_backend: Any, live_backend: Any, managed_backend: Any | None = None
    ) -> None:
        self.fixture_backend = fixture_backend
        self.live_backend = live_backend
        self.managed_backend = managed_backend or live_backend

    def _backend(self, target: HelperTarget) -> Any:
        return self.fixture_backend if target.fixture_only else self.live_backend

    def _home_manager_backend(self, target: HelperTarget) -> Any:
        if target.fixture_only or target.home_manager_apply_enabled:
            return self.fixture_backend
        return self.live_backend

    def validate_plan(self, target: HelperTarget, plan: ValidatePlanPayload, peer_uid: int):
        return self._backend(target).validate_plan(target, plan, peer_uid)

    def apply_validated_plan(
        self, target: HelperTarget, plan: PendingValidatedPlan, peer_uid: int
    ):
        return self._backend(target).apply_validated_plan(target, plan, peer_uid)

    def recover_transaction(
        self, target: HelperTarget, transaction_id: str, peer_uid: int
    ):
        return self._backend(target).recover_transaction(
            target, transaction_id, peer_uid
        )

    def validate_home_manager_plan(
        self,
        target: HelperTarget,
        plan: ValidateHomeManagerPlanPayload,
        peer_uid: int,
    ):
        return self._home_manager_backend(target).validate_home_manager_plan(
            target, plan, peer_uid
        )

    def apply_validated_home_manager_plan(
        self,
        target: HelperTarget,
        plan: PendingValidatedHomeManagerPlan,
        peer_uid: int,
    ):
        return self._home_manager_backend(target).apply_validated_home_manager_plan(
            target, plan, peer_uid
        )

    def recover_home_manager_transaction(
        self, target: HelperTarget, transaction_id: str, peer_uid: int
    ):
        return self._home_manager_backend(target).recover_home_manager_transaction(
            target, transaction_id, peer_uid
        )

    def validate_managed_plan(
        self, target: HelperTarget, plan: ValidatePlanPayload, peer_uid: int
    ):
        return self.managed_backend.validate_managed_plan(target, plan, peer_uid)

    def apply_validated_managed_plan(
        self,
        target: HelperTarget,
        plan: PendingValidatedManagedPlan,
        peer_uid: int,
    ):
        return self.managed_backend.apply_validated_managed_plan(
            target, plan, peer_uid
        )

    def recover_managed_transaction(
        self, target: HelperTarget, transaction_id: str, peer_uid: int
    ):
        return self.managed_backend.recover_managed_transaction(
            target, transaction_id, peer_uid
        )

    def preview_activation(
        self, target: HelperTarget, payload: PreviewActivationPayload, peer_uid: int
    ):
        return self._backend(target).preview_activation(target, payload, peer_uid)

    def test_activation(
        self, target: HelperTarget, payload: PreviewActivationPayload, peer_uid: int
    ):
        return self._backend(target).test_activation(target, payload, peer_uid)

    def recover_test_activation(
        self, target: HelperTarget, session_id: str, peer_uid: int
    ):
        return self._backend(target).recover_test_activation(target, session_id, peer_uid)

    def commit_tested_system(
        self, target: HelperTarget, payload: CommitTestedSystemPayload, peer_uid: int
    ):
        return self._backend(target).commit_tested_system(target, payload, peer_uid)

    def rollback_committed_system(
        self, target: HelperTarget, session_id: str, peer_uid: int
    ):
        return self._backend(target).rollback_committed_system(
            target, session_id, peer_uid
        )

    def activation_session_status(
        self, target: HelperTarget, session_id: str, peer_uid: int
    ):
        return self._backend(target).activation_session_status(
            target, session_id, peer_uid
        )

    def discard_validated_plan(
        self, target: HelperTarget, plan: ValidatePlanPayload, peer_uid: int
    ) -> None:
        discard = getattr(self._backend(target), "discard_validated_plan", None)
        if discard is not None:
            discard(target, plan, peer_uid)

    def discard_validated_home_manager_plan(
        self,
        target: HelperTarget,
        plan: ValidateHomeManagerPlanPayload,
        peer_uid: int,
    ) -> None:
        discard = getattr(
            self._home_manager_backend(target),
            "discard_validated_home_manager_plan",
            None,
        )
        if discard is not None:
            discard(target, plan, peer_uid)

    def discard_validated_managed_plan(
        self, target: HelperTarget, plan: ValidatePlanPayload, peer_uid: int
    ) -> None:
        discard = getattr(
            self.managed_backend, "discard_validated_managed_plan", None
        )
        if discard is not None:
            discard(target, plan, peer_uid)
