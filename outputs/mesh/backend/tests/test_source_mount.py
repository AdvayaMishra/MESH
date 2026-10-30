from types import SimpleNamespace

import pytest
from app.scan_worker import verify_source_mount


@pytest.mark.parametrize("output", [b"false\n", b"", b"unexpected\n"])
def test_lost_tmpfs_mount_fails_closed(monkeypatch, output):
    monkeypatch.setattr(
        "app.scan_worker.subprocess.run", lambda *args, **kwargs: SimpleNamespace(stdout=output)
    )
    with pytest.raises(RuntimeError, match="keeper stopped"):
        verify_source_mount("mesh-keeper-synthetic")


def test_live_tmpfs_mount_accepted(monkeypatch):
    monkeypatch.setattr(
        "app.scan_worker.subprocess.run", lambda *args, **kwargs: SimpleNamespace(stdout=b"true\n")
    )
    verify_source_mount("mesh-keeper-synthetic")
