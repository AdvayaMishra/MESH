import json
import subprocess
import sys
from pathlib import Path


def test_repository_owned_bandit_policy_cannot_suppress_eval(tmp_path):
    (tmp_path / "a.py").write_text("eval('input()') # nosec\n", encoding="utf-8")
    (tmp_path / ".bandit").write_text("[bandit]\nskips=B307\n", encoding="utf-8")
    policy = Path(__file__).resolve().parents[2] / "security-engine/bandit.ini"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bandit",
            "-r",
            str(tmp_path),
            "-f",
            "json",
            "--ignore-nosec",
            "--ini",
            str(policy),
        ],
        cwd=tmp_path,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 1
    assert any(finding["test_id"] == "B307" for finding in json.loads(result.stdout)["results"])
