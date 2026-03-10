from __future__ import annotations

from typing import Any

from renderdoc_mcp.session_pool import CaptureSession


def attach_capture(payload: dict[str, Any], session: CaptureSession) -> dict[str, Any]:
    payload["capture_id"] = session.capture_id
    payload["capture_path"] = session.capture_path
    payload.setdefault("meta", {})
    return payload


def ensure_meta(payload: dict[str, Any]) -> dict[str, Any]:
    payload.setdefault("meta", {})
    return payload
