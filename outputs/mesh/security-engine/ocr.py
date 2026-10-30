"""No document text is logged or returned. Only explicit, ambiguous-safe labels are suggested."""

import json
import re
import subprocess
import sys


def extract(text: str) -> dict:
    def unique(pattern):
        values = {
            match.strip() for match in re.findall(pattern, text, re.MULTILINE | re.IGNORECASE)
        }
        return next(iter(values)) if len(values) == 1 else None

    return {
        "suggested_name": unique(
            r"^\s*(?:full |employee )?name\s*:\s*([A-Za-z][A-Za-z .'-]{1,99})\s*$"
        ),
        "suggested_employee_id": unique(
            r"^\s*(?:employee|staff)\s+id\s*:\s*([A-Za-z0-9][A-Za-z0-9._/ -]{0,49})\s*$"
        ),
        "engine": "tesseract-5.5.0-eng-psm6-v1",
        "untrusted": True,
    }


def main():
    content = sys.stdin.buffer.read(2097153)
    if (
        not content
        or len(content) > 2097152
        or not content.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff"))
    ):
        raise ValueError("Invalid bounded image")
    result = subprocess.run(  # nosec B603 B607 # fixed image binary/arguments; sandbox resource limits apply
        ["tesseract", "stdin", "stdout", "-l", "eng", "--psm", "6"],
        input=content,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=30,
        check=True,
    )
    if len(result.stdout) > 1048576:
        raise ValueError("OCR output exceeded bound")
    print(json.dumps(extract(result.stdout.decode("utf-8", errors="replace"))))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(1)  # No image, engine diagnostic or extracted identity text on stderr.
