from __future__ import annotations

from typing import Any

from renderdoc_mcp.analysis.frame_analysis import LEGACY_ACTION_LIST_NODE_LIMIT, MAX_PAGE_LIMIT
from renderdoc_mcp.application.context import ApplicationContext
from renderdoc_mcp.application.response import attach_capture, ensure_meta
from renderdoc_mcp.errors import ReplayFailureError

SUPPORTED_SHADER_STAGES = {
    "vertex": "Vertex",
    "vs": "Vertex",
    "hull": "Hull",
    "hs": "Hull",
    "domain": "Domain",
    "ds": "Domain",
    "geometry": "Geometry",
    "gs": "Geometry",
    "pixel": "Pixel",
    "fragment": "Pixel",
    "ps": "Pixel",
    "compute": "Compute",
    "cs": "Compute",
    "task": "Task",
    "amplification": "Task",
    "as": "Task",
    "mesh": "Mesh",
    "raygen": "RayGen",
    "raygeneration": "RayGen",
    "intersection": "Intersection",
    "anyhit": "AnyHit",
    "closesthit": "ClosestHit",
    "miss": "Miss",
    "callable": "Callable",
}


def _normalize_shader_stage(stage: str | None) -> str | None:
    if stage is None:
        return None
    key = stage.strip().replace("_", "").replace("-", "").replace(" ", "").lower()
    return SUPPORTED_SHADER_STAGES.get(key)


class ActionHandlers:
    def __init__(self, context: ApplicationContext) -> None:
        self.context = context

    def renderdoc_get_action_tree(
        self,
        capture_id: str,
        max_depth: int | None = None,
        name_filter: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        max_depth = self.context.normalize_optional_int(max_depth, "max_depth")
        name_filter = self.context.normalize_optional_string(name_filter)
        limit = self.context.normalize_optional_int(limit, "limit")

        if max_depth is not None and max_depth < 0:
            raise ReplayFailureError("max_depth must be greater than or equal to 0.")
        if limit is not None and (limit <= 0 or limit > LEGACY_ACTION_LIST_NODE_LIMIT):
            raise ReplayFailureError(
                "limit must be between 1 and {}.".format(LEGACY_ACTION_LIST_NODE_LIMIT),
                {"limit": limit},
            )

        params: dict[str, Any] = {}
        if max_depth is not None:
            params["max_depth"] = max_depth
        if name_filter:
            params["name_filter"] = name_filter
        if limit is not None:
            params["limit"] = limit

        session, result = self.context.capture_tool(capture_id, "get_action_tree", params)
        return attach_capture(ensure_meta(result), session)

    def renderdoc_list_actions(
        self,
        capture_id: str,
        max_depth: int | None = None,
        name_filter: str | None = None,
        cursor: int | str | None = None,
        limit: int | str | None = None,
    ) -> dict[str, Any]:
        max_depth = self.context.normalize_optional_int(max_depth, "max_depth")
        name_filter = self.context.normalize_optional_string(name_filter)
        cursor = self.context.normalize_optional_int(cursor, "cursor")
        limit = self.context.normalize_optional_int(limit, "limit")

        if max_depth is not None and max_depth < 0:
            raise ReplayFailureError("max_depth must be greater than or equal to 0.")
        if cursor is not None and cursor < 0:
            raise ReplayFailureError("cursor must be greater than or equal to 0.", {"cursor": cursor})
        if limit is not None and (limit <= 0 or limit > MAX_PAGE_LIMIT):
            raise ReplayFailureError(
                "limit must be between 1 and {}.".format(MAX_PAGE_LIMIT),
                {"limit": limit},
            )

        params: dict[str, Any] = {}
        if max_depth is not None:
            params["max_depth"] = max_depth
        if name_filter:
            params["name_filter"] = name_filter
        if cursor is not None:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = limit

        session, result = self.context.capture_tool(capture_id, "list_actions", params)
        return attach_capture(ensure_meta(result), session)

    def renderdoc_get_action_details(self, capture_id: str, event_id: int) -> dict[str, Any]:
        normalized_event_id = self.context.normalize_required_int(event_id, "event_id")
        session, result = self.context.capture_tool(capture_id, "get_action_details", {"event_id": normalized_event_id})
        return attach_capture(ensure_meta(result), session)

    def renderdoc_get_pipeline_state(self, capture_id: str, event_id: int) -> dict[str, Any]:
        normalized_event_id = self.context.normalize_required_int(event_id, "event_id")
        session, result = self.context.capture_tool(capture_id, "get_pipeline_state", {"event_id": normalized_event_id})
        return attach_capture(ensure_meta(result), session)

    def renderdoc_get_api_pipeline_state(self, capture_id: str, event_id: int) -> dict[str, Any]:
        normalized_event_id = self.context.normalize_required_int(event_id, "event_id")
        session, result = self.context.capture_tool(
            capture_id,
            "get_api_pipeline_state",
            {"event_id": normalized_event_id},
        )
        return attach_capture(ensure_meta(result), session)

    def renderdoc_get_shader_code(
        self,
        capture_id: str,
        event_id: int,
        stage: str,
        target: str | None = None,
    ) -> dict[str, Any]:
        normalized_event_id = self.context.normalize_required_int(event_id, "event_id")
        normalized_stage = _normalize_shader_stage(self.context.normalize_optional_string(stage))
        normalized_target = self.context.normalize_optional_string(target)

        if normalized_stage is None:
            raise ReplayFailureError(
                "stage must name a supported shader stage.",
                {"stage": stage, "supported_stages": sorted(set(SUPPORTED_SHADER_STAGES.values()))},
            )

        params = {"event_id": normalized_event_id, "stage": normalized_stage}
        if normalized_target:
            params["target"] = normalized_target

        session, result = self.context.capture_tool(capture_id, "get_shader_code", params)
        return attach_capture(ensure_meta(result), session)
