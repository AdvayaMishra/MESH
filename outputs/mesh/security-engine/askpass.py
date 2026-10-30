#!/usr/bin/env python3
import sys
from pathlib import Path

print(
    "x-access-token" if "Username" in sys.argv[1] else Path("/tmp/github_token").read_text().strip()
)
