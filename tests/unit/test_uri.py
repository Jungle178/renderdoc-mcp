import pytest

from renderdoc_mcp.uri import create_capture_id, normalize_capture_id


def test_capture_id_round_trip() -> None:
    capture_id = create_capture_id()
    assert normalize_capture_id(capture_id) == capture_id


def test_capture_id_validation_rejects_non_hex_values() -> None:
    with pytest.raises(ValueError):
        normalize_capture_id("not-a-capture-id")
