from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import renderdoc_mcp.services.common as common_module
from renderdoc_mcp.bridge import QRenderDocBridge
from renderdoc_mcp.service import RenderDocService
from renderdoc_mcp.session_pool import CaptureSessionPool


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeBridge:
    def __init__(self) -> None:
        self.loaded: list[str] = []
        self.calls: list[tuple[str, dict]] = []
        self.closed = 0

    def ensure_capture_loaded(self, capture_path: str) -> dict[str, bool]:
        self.loaded.append(capture_path)
        return {"loaded": True}

    def call(self, method: str, params=None) -> dict:
        payload = params or {}
        self.calls.append((method, payload))
        if method == "get_capture_summary":
            return {"api": "D3D12"}
        if method == "analyze_frame":
            return {"passes": [], "pass_count": 0}
        if method == "list_actions":
            return {
                "actions": [],
                "count": 0,
                "matched_count": 0,
                "returned_count": 0,
                "truncated": False,
                "limit": int(payload.get("limit", 0)),
                "has_more": False,
                "next_cursor": "",
                "cursor": str(payload.get("cursor", 0)),
                "page_mode": "flat_preorder",
            }
        return {"ok": True}

    def close(self) -> None:
        self.closed += 1


def _capture(tmp_path: Path, name: str) -> str:
    capture_path = tmp_path / name
    capture_path.write_text("x", encoding="utf-8")
    return str(capture_path.resolve())


def test_service_reuses_one_pooled_bridge_per_capture(tmp_path: Path, monkeypatch) -> None:
    capture_path = _capture(tmp_path, "sample.rdc")
    created: list[FakeBridge] = []
    pool = CaptureSessionPool(bridge_factory=lambda: created.append(FakeBridge()) or created[-1])
    monkeypatch.setattr(common_module, "get_capture_session_pool", lambda: pool)

    service = RenderDocService()
    service.get_capture_summary(capture_path)
    service.analyze_frame(capture_path)
    service.list_actions(capture_path, cursor=0, limit=10)

    assert len(created) == 1
    assert created[0].loaded == [capture_path, capture_path, capture_path]
    assert [item[0] for item in created[0].calls] == [
        "get_capture_summary",
        "analyze_frame",
        "list_actions",
    ]


def test_session_pool_creates_distinct_bridges_for_distinct_captures(tmp_path: Path) -> None:
    first_capture = _capture(tmp_path, "first.rdc")
    second_capture = _capture(tmp_path, "second.rdc")
    created: list[FakeBridge] = []
    pool = CaptureSessionPool(bridge_factory=lambda: created.append(FakeBridge()) or created[-1])

    with pool.lease(first_capture) as first_bridge:
        pass
    with pool.lease(second_capture) as second_bridge:
        pass
    with pool.lease(first_capture) as reused_bridge:
        pass

    assert len(created) == 2
    assert first_bridge is reused_bridge
    assert first_bridge is not second_bridge


def test_session_pool_evicts_only_expired_idle_sessions(tmp_path: Path) -> None:
    first_capture = _capture(tmp_path, "first.rdc")
    second_capture = _capture(tmp_path, "second.rdc")
    clock = FakeClock()
    created: list[FakeBridge] = []
    pool = CaptureSessionPool(
        idle_timeout_seconds=10.0,
        bridge_factory=lambda: created.append(FakeBridge()) or created[-1],
        monotonic=clock,
    )

    with pool.lease(first_capture):
        pass
    clock.advance(5.0)
    with pool.lease(second_capture):
        pass

    clock.advance(6.0)
    evicted = pool.evict_idle_sessions()

    assert evicted == [first_capture]
    assert pool.session_count() == 1
    assert created[0].closed == 1
    assert created[1].closed == 0


def test_session_pool_keeps_in_use_sessions_during_cleanup(tmp_path: Path) -> None:
    capture_path = _capture(tmp_path, "sample.rdc")
    clock = FakeClock()
    created: list[FakeBridge] = []
    pool = CaptureSessionPool(
        idle_timeout_seconds=10.0,
        bridge_factory=lambda: created.append(FakeBridge()) or created[-1],
        monotonic=clock,
    )

    with pool.lease(capture_path) as bridge:
        clock.advance(11.0)
        evicted = pool.evict_idle_sessions()
        assert evicted == []
        assert bridge.closed == 0
        assert pool.session_count() == 1

    clock.advance(11.0)
    evicted = pool.evict_idle_sessions()

    assert evicted == [capture_path]
    assert created[0].closed == 1
    assert pool.session_count() == 0


def test_bridge_close_terminates_child_process_and_is_idempotent() -> None:
    bridge = QRenderDocBridge()
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    bridge._process = process

    bridge.close()

    assert process.poll() is not None
    assert bridge._process is None

    bridge.close()
    assert process.poll() is not None
