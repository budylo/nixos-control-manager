#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from nix_control_manager.candidate_build import CandidateBuildManager


ACTIVE = {"queued", "preparing", "running", "analyzing", "cancelling", "cleaning"}


def source_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(path for path in root.rglob("*") if path.is_file())
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a disposable NixOS candidate without activation"
    )
    parser.add_argument("config_root", type=Path)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    root = args.config_root.resolve()
    before = source_hashes(root)
    current_system = Path("/run/current-system")
    generation_before = os.path.realpath(current_system) if current_system.exists() else None
    result_link = Path.cwd() / "result"
    result_link_existed = result_link.exists() or result_link.is_symlink()

    manager = CandidateBuildManager(config_root=root, timeout=args.timeout)
    started = manager.start()
    job_id = started["jobId"]
    cursor = 0
    events: list[dict] = []
    result = started
    deadline = time.monotonic() + args.timeout + 30
    try:
        while True:
            result = manager.poll(job_id, after=cursor)
            events.extend(result["events"])
            cursor = result["nextCursor"]
            if result["status"] not in ACTIVE:
                break
            if time.monotonic() >= deadline:
                manager.cancel(job_id)
                raise RuntimeError("build-preview integration exceeded its deadline")
            time.sleep(0.1)
    finally:
        manager.close()

    after = source_hashes(root)
    generation_after = os.path.realpath(current_system) if current_system.exists() else None
    command = result.get("command", [])
    command_text = " ".join(command)
    summary = {
        "status": result["status"],
        "configurationMode": result.get("configurationMode"),
        "source": str(root),
        "sourceFilesUnchanged": len(after) if before == after else False,
        "currentSystemUnchanged": generation_before == generation_after,
        "workingCopyRemoved": result.get("workingCopyRemoved"),
        "outputPaths": result.get("outputPaths", []),
        "impactAvailable": result.get("impactAvailable"),
        "closureDiffLines": len(result.get("closureDiff", "").splitlines()),
        "eventCount": len(events),
        "privileged": result.get("privileged"),
        "configurationWriteEnabled": result.get("configurationWriteEnabled"),
        "activationEnabled": result.get("activationEnabled"),
        "resultSymlinkCreated": (
            not result_link_existed and (result_link.exists() or result_link.is_symlink())
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))

    assert result["status"] == "passed", result
    assert result["workingCopyRemoved"] is True
    assert result["privileged"] is False
    assert result["configurationWriteEnabled"] is False
    assert result["activationEnabled"] is False
    assert result["testEnabled"] is False
    assert result["switchEnabled"] is False
    assert result["outputPaths"]
    assert result["impactAvailable"] is True
    assert "diff-closures" in result["impactCommand"]
    assert result["dryActivateExecuted"] is False
    assert result["activationPreviewReady"] is True
    assert before == after
    assert generation_before == generation_after
    assert result_link_existed or not (result_link.exists() or result_link.is_symlink())
    assert "nixos-rebuild" not in command_text
    assert "switch" not in command
    assert "test" not in command
    assert "--no-link" in command or "--no-out-link" in command
    assert any(event["stream"] == "command" for event in events)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
