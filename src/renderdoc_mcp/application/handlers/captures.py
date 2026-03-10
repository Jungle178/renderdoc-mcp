from __future__ import annotations

from pathlib import Path
from typing import Any

from renderdoc_mcp.analysis.frame_analysis import DEFAULT_PASS_PAGE_LIMIT, MAX_PAGE_LIMIT, PASS_CATEGORIES, PASS_SORT_OPTIONS
from renderdoc_mcp.application.context import ApplicationContext
from renderdoc_mcp.application.response import attach_capture, ensure_meta
from renderdoc_mcp.errors import ReplayFailureError

SUPPORTED_PASS_CATEGORIES = set(PASS_CATEGORIES)
SUPPORTED_PASS_SORT_OPTIONS = set(PASS_SORT_OPTIONS)


class CaptureHandlers:
    def __init__(self, context: ApplicationContext) -> None:
        self.context = context

    def renderdoc_open_capture(self, capture_path: str) -> dict[str, Any]:
        session = self.context.open_capture(capture_path)
        try:
            session.bridge.ensure_capture_loaded(session.capture_path)
            summary = ensure_meta(session.bridge.call("get_capture_summary"))
        except Exception:
            self.context.close_capture(session.capture_id)
            raise
        return attach_capture(summary, session)

    def renderdoc_close_capture(self, capture_id: str) -> dict[str, Any]:
        session = self.context.get_session(capture_id)
        self.context.close_capture(capture_id)
        return {
            "capture_id": session.capture_id,
            "capture_path": session.capture_path,
            "closed": True,
            "meta": {},
        }

    def renderdoc_get_capture_summary(self, capture_id: str) -> dict[str, Any]:
        session, result = self.context.capture_tool(capture_id, "get_capture_summary")
        return attach_capture(ensure_meta(result), session)

    def renderdoc_analyze_frame(self, capture_id: str, include_timing_summary: Any = False) -> dict[str, Any]:
        include_timing_summary = bool(
            self.context.normalize_optional_bool(include_timing_summary, "include_timing_summary") or False
        )
        params: dict[str, Any] = {}
        if include_timing_summary:
            params["include_timing_summary"] = True
        session, result = self.context.capture_tool(capture_id, "analyze_frame", params)
        return attach_capture(ensure_meta(result), session)

    def renderdoc_list_passes(
        self,
        capture_id: str,
        cursor: int | str | None = None,
        limit: int | str | None = None,
        category_filter: str | None = None,
        name_filter: str | None = None,
        sort_by: str | None = None,
        threshold_ms: float | str | None = None,
    ) -> dict[str, Any]:
        cursor = self.context.normalize_optional_int(cursor, "cursor")
        limit = self.context.normalize_optional_int(limit, "limit")
        category_filter = self.context.normalize_optional_string(category_filter)
        name_filter = self.context.normalize_optional_string(name_filter)
        sort_by = (self.context.normalize_optional_string(sort_by) or "event_order").lower()
        threshold_ms = self.context.normalize_optional_float(threshold_ms, "threshold_ms")

        if cursor is not None and cursor < 0:
            raise ReplayFailureError("cursor must be greater than or equal to 0.", {"cursor": cursor})
        if limit is not None and (limit <= 0 or limit > MAX_PAGE_LIMIT):
            raise ReplayFailureError(
                "limit must be between 1 and {}.".format(MAX_PAGE_LIMIT),
                {"limit": limit},
            )
        if category_filter and category_filter not in SUPPORTED_PASS_CATEGORIES:
            raise ReplayFailureError(
                "category_filter must be one of {}.".format(", ".join(sorted(SUPPORTED_PASS_CATEGORIES))),
                {"category_filter": category_filter},
            )
        if sort_by not in SUPPORTED_PASS_SORT_OPTIONS:
            raise ReplayFailureError(
                "sort_by must be one of {}.".format(", ".join(sorted(SUPPORTED_PASS_SORT_OPTIONS))),
                {"sort_by": sort_by},
            )
        if threshold_ms is not None and threshold_ms < 0:
            raise ReplayFailureError(
                "threshold_ms must be greater than or equal to 0.",
                {"threshold_ms": threshold_ms},
            )

        params: dict[str, Any] = {"limit": limit or DEFAULT_PASS_PAGE_LIMIT}
        if cursor is not None:
            params["cursor"] = cursor
        if category_filter:
            params["category_filter"] = category_filter
        if name_filter:
            params["name_filter"] = name_filter
        if sort_by != "event_order":
            params["sort_by"] = sort_by
        if threshold_ms is not None:
            params["threshold_ms"] = threshold_ms

        session, result = self.context.capture_tool(capture_id, "list_passes", params)
        return attach_capture(ensure_meta(result), session)

    def renderdoc_get_pass_details(self, capture_id: str, pass_id: str) -> dict[str, Any]:
        normalized_pass_id = self.context.normalize_required_string(pass_id, "pass_id")
        session, result = self.context.capture_tool(capture_id, "get_pass_details", {"pass_id": normalized_pass_id})
        return attach_capture(ensure_meta(result), session)

    def renderdoc_get_timing_data(self, capture_id: str, pass_id: str) -> dict[str, Any]:
        normalized_pass_id = self.context.normalize_required_string(pass_id, "pass_id")
        session, result = self.context.capture_tool(capture_id, "get_timing_data", {"pass_id": normalized_pass_id})
        return attach_capture(ensure_meta(result), session)

    def renderdoc_get_performance_hotspots(self, capture_id: str) -> dict[str, Any]:
        session, result = self.context.capture_tool(capture_id, "get_performance_hotspots")
        return attach_capture(ensure_meta(result), session)

    def renderdoc_recent_captures(self) -> dict[str, Any]:
        config = self.context.read_ui_config()
        recent_paths = list(config.get("RecentCaptureFiles", []))
        captures = []

        for raw_path in recent_paths:
            path = Path(raw_path)
            captures.append(
                {
                    "path": str(path),
                    "exists": path.is_file(),
                }
            )

        return {"recent_captures": captures, "count": len(captures), "meta": {}}

    def renderdoc_capture_summary_resource(self, capture_id: str) -> dict[str, Any]:
        return self.renderdoc_get_capture_summary(capture_id)
