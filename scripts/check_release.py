from __future__ import annotations

import argparse
from pathlib import Path
import re
import runpy
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"release check failed: {message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate synchronized release metadata")
    parser.add_argument("--tag", help="Git tag to compare with the declared release")
    args = parser.parse_args(argv)

    version = runpy.run_path(ROOT / "src/nix_control_manager/version.py")
    python_version = version["PYTHON_VERSION"]
    release_version = version["RELEASE_VERSION"]
    release_tag = version["RELEASE_TAG"]
    if not re.fullmatch(r"\d+\.\d+\.\d+-alpha\.\d+", release_version):
        fail(f"invalid alpha version {release_version!r}")
    if not re.fullmatch(r"\d+\.\d+\.\d+a\d+", python_version):
        fail(f"invalid Python alpha version {python_version!r}")
    if release_tag != f"v{release_version}":
        fail("RELEASE_TAG does not match RELEASE_VERSION")
    if args.tag is not None and args.tag != release_tag:
        fail(f"tag {args.tag!r} does not match {release_tag!r}")

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dynamic = pyproject.get("tool", {}).get("setuptools", {}).get("dynamic", {})
    if dynamic.get("version", {}).get("attr") != "nix_control_manager.version.PYTHON_VERSION":
        fail("pyproject version is not sourced from version.PYTHON_VERSION")

    package_nix = (ROOT / "packaging/package.nix").read_text(encoding="utf-8")
    nix_match = re.search(r'^\s*version\s*=\s*"([^"]+)";', package_nix, re.MULTILINE)
    if nix_match is None or nix_match.group(1) != release_version:
        fail("packaging/package.nix version is out of sync")

    required_files = {
        ROOT / "CHANGELOG.md": f"## [{release_version}]",
        ROOT / "docs/installation.md": release_tag,
        ROOT / "docs/updating.md": "nix flake update nix-control-manager",
        ROOT / f"docs/releases/{release_tag}.md": f"# Nix Control Manager {release_version}",
    }
    for path, marker in required_files.items():
        if not path.is_file() or marker not in path.read_text(encoding="utf-8"):
            fail(f"{path.relative_to(ROOT)} is missing marker {marker!r}")

    print(
        f"release metadata: ok ({release_tag}; Python {python_version}; Nix {release_version})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
