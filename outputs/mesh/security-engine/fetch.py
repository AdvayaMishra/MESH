"""Dedicated fetch-container entrypoint; no build hooks, submodules or external URL input."""

import os
import re
import resource
import subprocess
import sys
from pathlib import Path

repository, commit = sys.argv[1:]
if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not re.fullmatch(
    r"[a-f0-9]{40}", commit
):
    raise SystemExit(2)
resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 1024 * 1024, 256 * 1024 * 1024))
credential = sys.stdin.buffer.read(8193)
if len(credential) > 8192 or not credential:
    raise SystemExit(2)
Path("/tmp/github_token").write_bytes(credential)
os.chmod("/tmp/github_token", 0o600)
environment = {
    "PATH": os.environ["PATH"],
    "HOME": "/tmp",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "/opt/mesh/askpass.py",
}


def git(*arguments):
    subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "protocol.file.allow=never",
            "-c",
            "protocol.ext.allow=never",
            "-c",
            "http.followRedirects=false",
            *arguments,
        ],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=120,
        check=True,
    )


os.chdir("/repo")
git("init")
git("remote", "add", "origin", "https://github.com/" + repository + ".git")
git("fetch", "--depth=1", "--no-tags", "origin", commit)
git("checkout", "--detach", commit)
git("rev-parse", "--verify", "HEAD")
total = count = 0
for directory, directories, filenames in os.walk("/repo", followlinks=False):
    for name in list(directories):
        linked = Path(directory, name)
        if linked.is_symlink():
            linked.unlink()
            directories.remove(name)
    directories[:] = [
        name for name in directories if name != ".git" and not Path(directory, name).is_symlink()
    ]
    for name in filenames:
        path = Path(directory, name)
        if path.is_symlink():
            path.unlink()
            continue
        count += 1
        total += path.stat().st_size
        if count > 50000 or total > 256 * 1024 * 1024:
            raise SystemExit(2)
# No executable repository file is invoked. Make regular files world-readable for scanner UID.
for directory, _directories, filenames in os.walk("/repo", followlinks=False):
    os.chmod(directory, 0o755)
    for name in filenames:
        path = Path(directory, name)
        if not path.is_symlink():
            os.chmod(path, 0o644)
