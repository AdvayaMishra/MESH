# Python dependency artifact integrity

The original `requirements.lock` preserves the 41 tested runtime versions for inventory and compatibility checks. `requirements-hashed.lock` pins those same versions and records SHA-256 digests from official PyPI release metadata, allowing published non-yanked wheels only. Runtime Docker installation uses `--require-hashes`; source distributions are disabled.

`requirements-build.lock` separately pins setuptools, wheel and packaging with artifact hashes. A Docker builder stage builds the trusted local MESH package with `--no-build-isolation --no-deps --no-index`. Only the resulting MESH wheel is copied to the runtime stage and installed without dependency resolution or network access. The final image check confirms all 41 runtime versions, matching lock-file hashes, UID 10001 and absence of the three build-tool distributions.

Regeneration requires an explicit public-PyPI metadata opt-in and an absolute local wheel-cache path:

```sh
python scripts/generate_dependency_hash_lock.py --wheel-cache ABSOLUTE_WHEEL_CACHE --allow-public-pypi-metadata
```

The generator verifies package/version identity, ignores yanked/source artifacts, requires matching cached wheels and compares their bytes against the published digests before writing either lock. The recorded run verified 44 cached wheels: 41 runtime and three build tools. Other published platform-wheel hashes are metadata-derived; only the installed target-platform artifacts have runtime acceptance evidence. Keep the plain and hashed runtime versions synchronized and rerun image/Compose validation after changing them.

Eight regression cases cover exact lock consistency, invalid/unpinned/duplicate inputs, release identity and artifact metadata, and real offline pip acceptance/rejection using a synthetic wheel. The pip tests download to temporary directories and never install the fixture. `dependency-hash-lock-results.json` records generation evidence; `runtime-artifact-integrity-results.json` binds installed versions and lock bytes to an immutable image ID.

This protects against unexpected artifact changes; it does not prove that publishers, packages, native libraries or the base OS are safe. OS advisory gates remain separate and currently fail. The existing development-tool snapshot is not a fully hash-locked development environment. No vulnerability matches are suppressed by this change.
