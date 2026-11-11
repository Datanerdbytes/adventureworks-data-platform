"""Offline test/syntax hooks and advisory checks; never run ELT or dbt."""

import argparse
from pathlib import Path
import shutil
import subprocess  # nosec B404
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], quiet: bool = False) -> int:
    try:
        return subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            stdout=subprocess.DEVNULL if quiet else None,
        ).returncode  # nosec B603
    except FileNotFoundError:
        print(f"Required tool is missing: {command[0]}", file=sys.stderr)
        return 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "check",
        choices=("python-tests", "javascript-syntax", "dependency-audit"),
    )
    parser.add_argument("filenames", nargs="*")
    args = parser.parse_args()
    if args.check == "python-tests":
        # The offline suite mocks all external services and reads no warehouse.
        return run(
            [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
        )
    if args.check == "javascript-syntax":
        for filename in args.filenames:
            result = run(["node", "--check", "--", filename])
            if result:
                return result
        return 0
    if not shutil.which("uv"):
        print("Install uv to audit locked dependencies.", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="adventureworks-audit-") as directory:
        requirements = str(Path(directory) / "requirements.txt")
        result = run(
            [
                "uv",
                "export",
                "--locked",
                "--format=requirements.txt",
                "--output-file",
                requirements,
            ],
            quiet=True,
        )
        if result:
            return result
        return run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "--strict",
                "--requirement",
                requirements,
            ],
        )


if __name__ == "__main__":
    raise SystemExit(main())
