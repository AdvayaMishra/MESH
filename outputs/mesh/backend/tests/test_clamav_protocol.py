import pytest
from app.documents import clamav_verdict
from fastapi import HTTPException


def test_complete_clamav_clean_frame_clears_upload():
    clamav_verdict(b"stream: OK\0")


@pytest.mark.parametrize(
    "response", [b"stream: OK", b"stream: OK\0extra\0", b"", b"x" * 4096 + b"\0"]
)
def test_truncated_or_ambiguous_clean_frames_fail_closed(response):
    with pytest.raises(HTTPException) as exc:
        clamav_verdict(response)
    assert exc.value.status_code == 503


def test_actual_detection_rejects_without_returning_signature_details():
    with pytest.raises(HTTPException) as exc:
        clamav_verdict(b"stream: PRIVATE_SIGNATURE_NAME FOUND\0")
    assert exc.value.status_code == 422
    assert "PRIVATE_SIGNATURE_NAME" not in exc.value.detail


def test_engine_failure_is_service_unavailability_instead_of_user_rejection():
    with pytest.raises(HTTPException) as exc:
        clamav_verdict(b"stream: INSTREAM size limit exceeded. ERROR\0")
    assert exc.value.status_code == 503
