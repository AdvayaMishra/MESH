"""Bounded static manifest parsing. Never installs packages or follows repository links."""

import json
import os
import re
import shutil
import tomllib
from pathlib import Path
from urllib.parse import unquote

PIN = re.compile(r"([A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_,.-]+\])?==([A-Za-z0-9.+_-]+)")


def prepare_semgrep_tree(root: Path, target: Path) -> None:
    if target.resolve().is_relative_to(root.resolve()) or root.resolve().is_relative_to(
        target.resolve()
    ):
        raise ValueError("Semgrep staging must be separate from the source tree")
    assert_semgrep_source_sizes(root)
    shutil.copytree(root, target, symlinks=True, ignore=shutil.ignore_patterns(".git"))
    for directory, folders, files in os.walk(target, followlinks=False):
        for name in list(folders):
            path = Path(directory, name)
            if path.is_symlink():
                path.unlink()
                folders.remove(name)
        for name in files:
            path = Path(directory, name)
            if path.is_symlink():
                path.unlink()
            elif name == ".semgrepignore":
                path.write_text("", encoding="utf-8")
    (target / ".semgrepignore").write_text("", encoding="utf-8")


def assert_semgrep_source_sizes(root: Path) -> None:
    """Do not let Semgrep's target-size skipping produce a false clean result."""
    visited = 0
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = [
            name for name in folders if name != ".git" and not Path(directory, name).is_symlink()
        ]
        for name in files:
            visited += 1
            if visited > 50000:
                raise ValueError("Repository file limit exceeded")
            path = Path(directory, name)
            if (
                path.suffix.lower() in {".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
                and not path.is_symlink()
                and path.stat().st_size > 1000000
            ):
                raise ValueError("Supported source exceeds the Semgrep target-size limit")


def extract(root: Path) -> list[dict[str, str]]:
    packages: dict[tuple[str, str, str], dict[str, str]] = {}
    visited = manifests = total = 0

    def add(ecosystem: str, name: str, version: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9@_./-]{1,200}", name) or not re.fullmatch(
            r"[A-Za-z0-9.+_-]{1,100}", version
        ):
            raise ValueError("Invalid dependency metadata")
        if ecosystem == "PyPI":
            if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?", name):
                raise ValueError("Invalid PyPI package name")
            name = re.sub(r"[-_.]+", "-", name).lower()
        elif not re.fullmatch(r"(?:@[A-Za-z0-9][A-Za-z0-9_.-]*/)?[A-Za-z0-9][A-Za-z0-9_.-]*", name):
            raise ValueError("Invalid npm package name")
        key = (ecosystem, name, version)
        packages[key] = {"ecosystem": ecosystem, "name": name, "version": version}
        if len(packages) > 500:
            raise ValueError("Dependency limit exceeded")

    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = sorted(
            name for name in folders if name != ".git" and not Path(directory, name).is_symlink()
        )
        for name in sorted(files):
            visited += 1
            if visited > 50000:
                raise ValueError("Repository file limit exceeded")
            if name in {"yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb"}:
                raise ValueError(
                    "Unsupported JavaScript lockfile; a complete inventory cannot be claimed"
                )
            python = name.startswith("requirements") and name.endswith((".txt", ".lock"))
            sbom = name == "bom.json" or name.endswith(".cdx.json")
            if (
                not python
                and not sbom
                and name
                not in {
                    "package-lock.json",
                    "Pipfile.lock",
                    "poetry.lock",
                    "uv.lock",
                }
            ):
                continue
            path = Path(directory, name)
            if path.is_symlink():
                continue
            size = path.stat().st_size
            manifests += 1
            total += size
            if size > 4 * 1024 * 1024 or total > 16 * 1024 * 1024 or manifests > 100:
                raise ValueError("Manifest size/count limit exceeded")
            content = path.read_text(encoding="utf-8-sig")
            if sbom:
                data = json.loads(content)
                if (
                    not isinstance(data, dict)
                    or data.get("bomFormat") != "CycloneDX"
                    or data.get("specVersion") not in {"1.5", "1.6"}
                ):
                    raise ValueError("Unsupported CycloneDX format/version")
                stack = [(data.get("components"), 0)]
                count = 0
                while stack:
                    components, depth = stack.pop()
                    if not isinstance(components, list) or depth > 32:
                        raise ValueError("Invalid or excessive CycloneDX nesting")
                    for component in components:
                        count += 1
                        if count > 5000 or not isinstance(component, dict):
                            raise ValueError("Invalid or excessive CycloneDX inventory")
                        purl = component.get("purl", "")
                        if not isinstance(purl, str) or len(purl) > 4096:
                            raise ValueError("Invalid CycloneDX package identifier")
                        purl = purl.split("?", 1)[0].split("#", 1)[0]
                        if not purl.startswith(("pkg:pypi/", "pkg:npm/")) or "@" not in purl:
                            raise ValueError(
                                "CycloneDX component requires a supported versioned PyPI/npm purl"
                            )
                        identity, version = purl.rsplit("@", 1)
                        kind, package_name = identity[4:].split("/", 1)
                        package_name, version = (
                            unquote(package_name, errors="strict"),
                            unquote(version, errors="strict"),
                        )
                        if component.get("version") != version or (
                            kind == "pypi" and "/" in package_name
                        ):
                            raise ValueError("CycloneDX version or package mismatch")
                        add("PyPI" if kind == "pypi" else "npm", package_name, version)
                        if "components" in component:
                            stack.append((component["components"], depth + 1))
                continue
            if name == "Pipfile.lock":
                data = json.loads(content)
                if not isinstance(data, dict) or not {"default", "develop"} <= data.keys():
                    raise ValueError("Invalid Pipenv lockfile")
                for group_name, group in data.items():
                    if group_name == "_meta":
                        continue
                    if not isinstance(group, dict):
                        raise ValueError("Invalid Pipenv package group")
                    for package_name, package in group.items():
                        if not isinstance(package, dict) or any(
                            key in package for key in ("git", "path", "file", "editable", "ref")
                        ):
                            raise ValueError("Unsupported non-registry Pipenv dependency")
                        match = PIN.fullmatch(package_name + str(package.get("version", "")))
                        if not match:
                            raise ValueError("Unpinned Pipenv dependency")
                        add("PyPI", *match.groups())
                continue
            if name in {"poetry.lock", "uv.lock"}:
                data = tomllib.loads(content)
                if name == "uv.lock" and data.get("version") != 1:
                    raise ValueError("Unsupported uv lockfile version")
                if name == "poetry.lock" and data.get("metadata", {}).get("lock-version") not in {
                    "2.0",
                    "2.1",
                }:
                    raise ValueError("Unsupported Poetry lockfile version")
                packages_data = data.get("package")
                if not isinstance(packages_data, list) or len(packages_data) > 5000:
                    raise ValueError("Invalid or oversized Python lockfile inventory")
                for package in packages_data:
                    if not isinstance(package, dict):
                        raise ValueError("Invalid Python lockfile package")
                    source = package.get("source", {})
                    if not isinstance(source, dict):
                        raise ValueError("Invalid Python lockfile source")
                    if name == "uv.lock":
                        if (
                            set(source) in ({"virtual"}, {"editable"})
                            and source.get("virtual", source.get("editable")) == "."
                        ):
                            continue  # root project, not an installed registry dependency
                        if set(source) != {"registry"} or not isinstance(source["registry"], str):
                            raise ValueError("Unsupported non-registry uv dependency")
                    elif source and source.get("type") not in {"legacy", "pypi"}:
                        raise ValueError("Unsupported non-registry Poetry dependency")
                    add("PyPI", package.get("name", ""), package.get("version", ""))
                continue
            if python:
                # Join pip hash continuation lines, without evaluating markers or URLs.
                content = re.sub(r"\\\s*\n", " ", content)
                for line in content.splitlines():
                    line = line.split("#", 1)[0].strip()
                    if not line:
                        continue
                    if line.startswith(("-r ", "--requirement ", "-c ", "--constraint ")):
                        reference = path.parent / line.split(maxsplit=1)[1]
                        resolved = reference.resolve()
                        if (
                            not resolved.is_relative_to(root.resolve())
                            or not reference.is_file()
                            or reference.is_symlink()
                            or not reference.name.startswith("requirements")
                            or not reference.name.endswith((".txt", ".lock"))
                        ):
                            raise ValueError("Unsupported dependency manifest reference")
                        continue  # safe referenced files are discovered independently
                    if line.startswith(
                        (
                            "--index-url ",
                            "--index-url=",
                            "--extra-index-url ",
                            "--extra-index-url=",
                            "--trusted-host ",
                            "--trusted-host=",
                            "--require-hashes",
                            "--only-binary ",
                            "--only-binary=",
                        )
                    ):
                        continue  # no package manager is invoked
                    requirement = line.split(";", 1)[0].split(" --hash=", 1)[0].strip()
                    match = PIN.fullmatch(requirement)
                    if not match:
                        raise ValueError(
                            "Dependency manifest contains an unpinned or unsupported requirement"
                        )
                    add("PyPI", *match.groups())
                continue
            data = json.loads(content)
            if not isinstance(data, dict) or data.get("lockfileVersion") not in {1, 2, 3}:
                raise ValueError("Unsupported npm lockfile")
            if data["lockfileVersion"] in {2, 3}:
                entries = data.get("packages")
                if not isinstance(entries, dict):
                    raise ValueError("Missing npm packages")
                for location, package in entries.items():
                    if "node_modules/" not in location:
                        continue
                    if not isinstance(package, dict):
                        raise ValueError("Invalid npm package")
                    if package.get("link"):
                        continue  # local workspace is not a registry dependency
                    # npm aliases use the install-directory alias as the location;
                    # lock v2/v3 records the actual registry identity in name.
                    add(
                        "npm",
                        package.get("name", location.rsplit("node_modules/", 1)[1]),
                        package.get("version", ""),
                    )
            else:
                stack = [data.get("dependencies", {})]
                count = 0
                while stack:
                    group = stack.pop()
                    if not isinstance(group, dict):
                        raise ValueError("Invalid npm dependencies")
                    for name, package in group.items():
                        count += 1
                        if count > 5000 or not isinstance(package, dict):
                            raise ValueError("npm dependency inventory exceeds bounds")
                        add("npm", name, package.get("version", ""))
                        if "dependencies" in package:
                            stack.append(package["dependencies"])
    return [packages[key] for key in sorted(packages)]
