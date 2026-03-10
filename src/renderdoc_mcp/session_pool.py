from __future__ import annotations

import atexit
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Iterator

from renderdoc_mcp.bridge import QRenderDocBridge


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass
class _CaptureSession:
    capture_path: str
    bridge: QRenderDocBridge
    last_used_monotonic: float
    in_use_count: int = 0


class CaptureSessionPool:
    def __init__(
        self,
        idle_timeout_seconds: float | None = None,
        bridge_factory: Callable[[], QRenderDocBridge] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self.idle_timeout_seconds = (
            idle_timeout_seconds
            if idle_timeout_seconds is not None
            else _env_float("RENDERDOC_CAPTURE_SESSION_IDLE_SECONDS", 300.0)
        )
        self._bridge_factory = bridge_factory or QRenderDocBridge
        self._monotonic = monotonic or time.monotonic
        self._lock = threading.RLock()
        self._sessions: dict[str, _CaptureSession] = {}
        atexit.register(self.close_all)

    @contextmanager
    def lease(self, capture_path: str) -> Iterator[QRenderDocBridge]:
        bridge = self._acquire(capture_path)
        try:
            yield bridge
        finally:
            self.release(capture_path)

    def release(self, capture_path: str) -> None:
        now = self._monotonic()
        with self._lock:
            session = self._sessions.get(capture_path)
            if session is not None:
                if session.in_use_count > 0:
                    session.in_use_count -= 1
                session.last_used_monotonic = now
            expired = self._pop_expired_locked(now)
        self._close_sessions(expired)

    def evict_idle_sessions(self) -> list[str]:
        with self._lock:
            expired = self._pop_expired_locked(self._monotonic())
        self._close_sessions(expired)
        return [session.capture_path for session in expired]

    def session_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def close_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        self._close_sessions(sessions)

    def _acquire(self, capture_path: str) -> QRenderDocBridge:
        now = self._monotonic()
        with self._lock:
            expired = self._pop_expired_locked(now)
            session = self._sessions.get(capture_path)
            if session is None:
                session = _CaptureSession(
                    capture_path=capture_path,
                    bridge=self._bridge_factory(),
                    last_used_monotonic=now,
                )
                self._sessions[capture_path] = session
            session.in_use_count += 1
            session.last_used_monotonic = now
            bridge = session.bridge
        self._close_sessions(expired)
        return bridge

    def _pop_expired_locked(self, now: float) -> list[_CaptureSession]:
        if self.idle_timeout_seconds <= 0:
            return []

        expired_paths = [
            capture_path
            for capture_path, session in self._sessions.items()
            if session.in_use_count == 0 and (now - session.last_used_monotonic) > self.idle_timeout_seconds
        ]
        expired = [self._sessions.pop(capture_path) for capture_path in expired_paths]
        return expired

    def _close_sessions(self, sessions: list[_CaptureSession]) -> None:
        for session in sessions:
            try:
                session.bridge.close()
            except Exception:
                pass


@lru_cache(maxsize=1)
def get_capture_session_pool() -> CaptureSessionPool:
    return CaptureSessionPool()
