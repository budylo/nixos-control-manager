"""Run systemd's offline security analysis on the rendered helper service."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("service_unit", type=Path)
    arguments = parser.parse_args()
    source = arguments.service_unit.expanduser().resolve()
    if not source.is_file() or source.name != "nix-control-manager-helper.service":
        raise RuntimeError("A rendered nix-control-manager-helper.service is required")
    executable = shutil.which("systemd-analyze")
    if executable is None:
        raise RuntimeError("systemd-analyze is unavailable")

    with tempfile.TemporaryDirectory(prefix="ncm-systemd-audit-") as temporary:
        root = Path(temporary)
        unit_directory = root / "etc" / "systemd" / "system"
        runtime_directory = root / "run" / "systemd"
        unit_directory.mkdir(parents=True)
        runtime_directory.mkdir(parents=True)
        shutil.copyfile(source, unit_directory / source.name)
        completed = subprocess.run(
            [
                executable,
                "security",
                "--offline=yes",
                "--no-pager",
                f"--root={root}",
                source.name,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    report = completed.stdout + completed.stderr
    summary = re.search(r"Overall exposure level[^\n]*", report)
    print(
        json.dumps(
            {
                "returnCode": completed.returncode,
                "summary": summary.group(0).strip() if summary else None,
                "temporaryRootRemoved": True,
                "unit": str(source),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if completed.returncode == 0 and summary else 2


if __name__ == "__main__":
    raise SystemExit(main())
