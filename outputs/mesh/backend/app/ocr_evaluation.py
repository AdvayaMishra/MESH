"""Aggregate OCR evaluation without retaining sample identities or suggestions."""

import unicodedata

from app.document_ocr import Suggestions


def normalized(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def evaluate_samples(samples: list[tuple[Suggestions, Suggestions]]) -> dict:
    if not samples or len(samples) > 1000:
        raise ValueError("Evaluation requires 1 to 1000 samples")
    metrics = {}
    for field in ("suggested_name", "suggested_employee_id"):
        counts = {
            "exact_matches": 0,
            "normalized_matches": 0,
            "abstentions": 0,
            "incorrect_nonempty": 0,
            "expected_present": 0,
        }
        for expected, observed in samples:
            truth, prediction = getattr(expected, field), getattr(observed, field)
            counts["expected_present"] += int(truth is not None)
            counts["exact_matches"] += int(truth == prediction)
            counts["normalized_matches"] += int(normalized(truth) == normalized(prediction))
            counts["abstentions"] += int(prediction is None)
            counts["incorrect_nonempty"] += int(
                prediction is not None and normalized(truth) != normalized(prediction)
            )
        metrics[field.removeprefix("suggested_")] = {
            **counts,
            "exact_accuracy": counts["exact_matches"] / len(samples),
            "normalized_accuracy": counts["normalized_matches"] / len(samples),
        }
    return {
        "sample_count": len(samples),
        "normalization": "Unicode NFKC, casefold and whitespace only; punctuation preserved",
        "fields": metrics,
        "representativeness_verified": False,
        "production_clearance": False,
        "automatic_identity_approval": False,
    }
