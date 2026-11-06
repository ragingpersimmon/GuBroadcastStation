"""Repo integrity: the 5protocol submodule pin must stay in the tree.

It was silently dropped once by `git add -A` in a checkout without the
submodule; the droplet then had no news pipeline."""
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_5protocol_submodule_is_pinned():
    try:
        out = subprocess.run(["git", "ls-files", "-s", "vendor/5protocol"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    assert out.startswith("160000 "), "vendor/5protocol gitlink missing: re-add with git update-index --cacheinfo"
    assert "vendor/5protocol" in (ROOT / ".gitmodules").read_text()


def test_env_example_has_no_inline_comments():
    for line in (ROOT / ".env.example").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            assert " #" not in line, f"systemd keeps inline comments as part of the value: {line!r}"
