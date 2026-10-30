import importlib.util
import json
from pathlib import Path

import pytest
from app.document_ocr import Suggestions
from app.ocr_evaluation import evaluate_samples


def suggestion(name=None, employee_id=None):
    return Suggestions(suggested_name=name, suggested_employee_id=employee_id, engine="fixture")


def test_aggregate_evaluation_distinguishes_errors_abstentions_and_exact_matches():
    report = evaluate_samples(
        [
            (suggestion("Private Person", "ID-1"), suggestion("PRIVATE   PERSON", "ID-1")),
            (suggestion("Another Person", "ID-2"), suggestion(None, "ID2")),
            (suggestion(), suggestion("Invented Person")),
        ]
    )
    assert report["sample_count"] == 3
    assert report["fields"]["name"]["exact_matches"] == 0
    assert report["fields"]["name"]["normalized_matches"] == 1
    assert report["fields"]["name"]["abstentions"] == 1
    assert report["fields"]["name"]["incorrect_nonempty"] == 1
    assert report["fields"]["employee_id"]["exact_matches"] == 2
    assert report["fields"]["employee_id"]["incorrect_nonempty"] == 1
    assert not report["production_clearance"]
    assert not report["automatic_identity_approval"]
    assert not report["representativeness_verified"]
    serialized = json.dumps(report)
    for sensitive in ("Private Person", "Another Person", "Invented Person", "ID-1", "ID-2"):
        assert sensitive not in serialized


@pytest.mark.parametrize("count", [0, 1001])
def test_evaluation_rejects_unbounded_or_empty_corpus(count):
    with pytest.raises(ValueError):
        evaluate_samples([(suggestion(), suggestion())] * count)


def driver():
    path = Path(__file__).resolve().parents[2] / "scripts/evaluate_ocr_dataset.py"
    spec = importlib.util.spec_from_file_location("mesh_ocr_evaluation_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "reference",
    [
        "sha256:" + "a" * 64,
        "mesh-ocr@sha256:" + "b" * 64,
        "localhost:5000/mesh/ocr@sha256:" + "c" * 64,
    ],
)
def test_corpus_evaluation_accepts_existing_immutable_local_or_registry_images(reference):
    assert driver().immutable_image_reference(reference)


@pytest.mark.parametrize(
    "reference",
    [
        "mesh-ocr:latest",
        "mesh-ocr:local",
        "--privileged",
        "sha256:abc",
        "sha256:" + "A" * 64,
        "mesh-ocr@sha256:" + "b" * 64 + " --network=host",
    ],
)
def test_corpus_evaluation_rejects_mutable_or_malformed_image_references(reference):
    assert not driver().immutable_image_reference(reference)


def manifest(tmp_path, rows):
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def row(image="fixture.png", **updates):
    return {
        "image": image,
        "expected_name": "Synthetic Tester",
        "expected_employee_id": "MESH-42",
        **updates,
    }


def test_manifest_only_accepts_bounded_unique_files_inside_corpus(tmp_path):
    image = tmp_path / "fixture.png"
    image.write_bytes(b"fixture")
    entries = driver().dataset(manifest(tmp_path, [row()]))
    assert entries[0][0] == image.resolve()
    with pytest.raises(ValueError):
        driver().dataset(manifest(tmp_path, [row(), row()]))


@pytest.mark.parametrize(
    "rows",
    [
        [],
        {},
        [row("../outside.png")],
        [row(expected_name="")],
        [row(expected_name=123)],
        [row(extra="forbidden")],
        [row("missing.png")],
    ],
)
def test_invalid_dataset_is_rejected_before_any_ocr(tmp_path, rows):
    (tmp_path / "fixture.png").write_bytes(b"fixture")
    with pytest.raises(ValueError):
        driver().dataset(manifest(tmp_path, rows))


def test_dataset_rejects_oversized_images(tmp_path):
    (tmp_path / "fixture.png").write_bytes(b"x" * 2097153)
    with pytest.raises(ValueError):
        driver().dataset(manifest(tmp_path, [row()]))


def test_dataset_requires_explicit_authorization_before_manifest_or_docker_access(
    monkeypatch, capsys
):
    module = driver()
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate_ocr_dataset.py",
            "--manifest",
            "private-missing.json",
            "--docker-executable",
            "missing-docker",
            "--image",
            "fixture",
        ],
    )
    assert module.main() == 1
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "dataset_authorization_required"
    assert "private" not in json.dumps(output)
