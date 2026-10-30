"""Build-time extraction of native files from an already SHA256-verified official wheel."""

import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath


def extract(wheel: Path, destination: Path) -> None:
    prefix = "semgrep-1.182.1.data/purelib/semgrep/bin/"
    with zipfile.ZipFile(wheel) as archive:
        for entry in archive.infolist():
            if not entry.filename.startswith(prefix) or entry.is_dir():
                continue
            relative = PurePosixPath(entry.filename[len(prefix) :])
            if relative.name == "__init__.py":
                continue
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe core artifact path")
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o555 if relative.name == "semgrep-core" else 0o444)
    if not (destination / "semgrep-core").is_file():
        raise ValueError("Core binary absent from pinned wheel")


if __name__ == "__main__":
    wheels = list(Path(sys.argv[1]).glob("semgrep-1.182.1-*.whl"))
    if len(wheels) != 1:
        raise ValueError("Exactly one pinned wheel required")
    extract(wheels[0], Path(sys.argv[2]))
