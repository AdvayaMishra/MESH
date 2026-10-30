import json
import os
import secrets
import subprocess
from uuid import uuid4

import pytest
from app.core.config import settings
from app.scanning import DockerSandbox, normalize

pytestmark = pytest.mark.skipif(
    os.getenv("MESH_DOCKER_SCANNER_TESTS") != "true",
    reason="Dedicated Docker scanner integration is not enabled",
)


def test_real_scanner_containment_and_dependency_extraction(tmp_path, monkeypatch, record_property):
    client_config = tmp_path / "docker-client"
    client_config.mkdir()
    (client_config / "config.json").write_text(
        json.dumps(
            {
                "proxies": {
                    "default": {
                        "httpProxy": "http://synthetic:fixture@proxy.invalid:1",
                        "httpsProxy": "http://synthetic:fixture@proxy.invalid:1",
                        "allProxy": "socks5://synthetic:fixture@proxy.invalid:1",
                    }
                }
            }
        )
    )
    # Preserve context-selected endpoints and implicit TLS credential paths.
    # Our explicit mutual-TLS acceptance endpoint can safely use this test config.
    if (
        os.getenv("DOCKER_HOST")
        and not os.getenv("DOCKER_CONTEXT")
        and (not os.getenv("DOCKER_TLS_VERIFY") or os.getenv("DOCKER_CERT_PATH"))
    ):
        monkeypatch.setenv("DOCKER_CONFIG", str(client_config))
    monkeypatch.setenv("SUPABASE_STORAGE_KEY", "DO_NOT_FORWARD_SYNTHETIC")
    volume = "mesh-" + str(uuid4())
    scanner = DockerSandbox(settings().scanner_image)
    scanner.verify_host()

    def docker(*args):
        return subprocess.run(
            [settings().docker_executable, *args], capture_output=True, timeout=240, check=True
        )

    docker(
        "volume",
        "create",
        "--opt",
        "type=tmpfs",
        "--opt",
        "device=tmpfs",
        "--opt",
        "o=size=32m,uid=10001,gid=10001,mode=0700,noexec,nosuid,nodev",
        volume,
    )
    keeper_name = "mesh-keeper-" + uuid4().hex
    try:
        keeper = scanner.command(keeper_name, volume, "bandit")
        docker(
            *keeper[1:2],
            "--detach",
            *keeper[2:-2],
            "--entrypoint=python",
            settings().scanner_image,
            "-c",
            "import time; time.sleep(1800)",
        )
        # Synthetic test text is never executed; no real secret or repository is used.
        code = (
            "import subprocess\napi_key = "
            + repr(secrets.token_hex(20))
            + "\neval('input()') # nosec # nosemgrep\nsubprocess.run('fixture', shell=True)\n"
        )
        fixture_files = {
            "a.py": code,
            "a.js": "eval('fixture'); // nosemgrep\n",
            "a.ts": "const x: string = 'fixture'; eval(x); // nosemgrep\n",
            "requirements.lock": "django==1.2\n",
            ".semgrepignore": "*\n",
            ".bandit": "[bandit]\nskips=B307\n",
            "probe.sh": "#!/bin/sh\nexit 0\n",
        }
        write = "from pathlib import Path\n" + "\n".join(
            f"Path('/repo/{name}').write_text({content!r})"
            for name, content in fixture_files.items()
        )
        write += "\nPath('/repo/probe.sh').chmod(0o755)"
        docker(
            "run",
            "--rm",
            "--network=none",
            "--read-only",
            "--user=10001:10001",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--mount",
            f"type=volume,src={volume},dst=/repo",
            "--entrypoint=python",
            settings().scanner_image,
            "-c",
            write,
        )
        # Actual runtime probes, not assertions about command strings alone.
        probe = """
import os,socket,subprocess,resource
from pathlib import Path
from importlib.metadata import PackageNotFoundError, distribution
assert os.getuid() == 10001
assert os.getgid() == 10001
assert 'SUPABASE_STORAGE_KEY' not in os.environ
assert 'DATABASE_URL' not in os.environ
for package in ['semgrep','mcp','opentelemetry-api']:
    try:
        distribution(package)
    except PackageNotFoundError:
        pass
    else:
        raise AssertionError('Unused frontend dependency installed: ' + package)
assert all(not os.environ.get(name) for name in ['HTTP_PROXY','HTTPS_PROXY','FTP_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','ftp_proxy','all_proxy','no_proxy'])
assert resource.getrlimit(resource.RLIMIT_NOFILE) == (256,256)
status = Path('/proc/self/status').read_text()
assert int(next(line.split()[1] for line in status.splitlines() if line.startswith('NoNewPrivs:'))) == 1
assert int(next(line.split()[1] for line in status.splitlines() if line.startswith('CapEff:')),16) == 0
cg = Path('/sys/fs/cgroup')
if (cg/'memory.max').exists():
    assert int((cg/'memory.max').read_text()) == 768*1024*1024
    assert int((cg/'memory.swap.max').read_text()) == 0
    assert int((cg/'pids.max').read_text()) == 128
    quota,period=(cg/'cpu.max').read_text().split()
    assert quota != 'max' and int(quota) <= int(period)
else:
    assert int((cg/'memory/memory.limit_in_bytes').read_text()) == 768*1024*1024
    assert int((cg/'memory/memory.memsw.limit_in_bytes').read_text()) == 768*1024*1024
    assert int((cg/'pids/pids.max').read_text()) == 128
    assert 0 < int((cg/'cpu/cpu.cfs_quota_us').read_text()) <= int((cg/'cpu/cpu.cfs_period_us').read_text())
try:
    subprocess.run(['/repo/probe.sh'],check=True)
except PermissionError:
    pass
else:
    raise AssertionError('Repository volume permits direct execution')
for path in ['/repo/forbidden-write','/etc/forbidden-write','/home/scanner/forbidden-write']:
    try:
        open(path,'w').close()
    except OSError:
        pass
    else:
        raise AssertionError('Protected filesystem is writable')
with socket.socket() as connection:
    connection.settimeout(2)
    assert connection.connect_ex(('1.1.1.1',443)) != 0
assert not os.path.exists('/var/run/docker.sock')
"""
        command = scanner.command("mesh-probe-" + uuid4().hex, volume, "bandit")
        probe_result = subprocess.run(
            command[:-2] + ["--entrypoint=python", settings().scanner_image, "-c", probe],
            capture_output=True,
            check=False,
            timeout=30,
        )
        assert probe_result.returncode == 0, probe_result.stderr.decode(errors="replace")[-2000:]
        record_property("containment", "passed")
        assert scanner.execute(volume, "dependencies") == [
            {"ecosystem": "PyPI", "name": "django", "version": "1.2"}
        ]
        record_property("dependency_extraction", "passed")
        results = {}
        for name in ("bandit", "gitleaks", "semgrep"):
            results[name] = normalize(name, scanner.execute(volume, name))
            assert results[name], name + " missed its synthetic finding"
            if name == "bandit":
                assert any(item["rule_id"] == "B307" for item in results[name])
            elif name == "semgrep":
                assert {item["rule_id"] for item in results[name]} >= {
                    "mesh.python.eval",
                    "mesh.python.shell",
                    "mesh.javascript.eval",
                }
                assert any(item["file_path"].endswith("a.ts") for item in results[name])
            record_property(name, "passed")
    finally:
        docker("rm", "-f", keeper_name)
        docker("volume", "rm", "-f", volume)
