from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from renderdoc_mcp.application.app import RenderDocApplication


@dataclass(frozen=True, slots=True)
class ToolRegistration:
    name: str
    description: str
    handler: Callable[..., dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ResourceRegistration:
    uri: str
    name: str
    description: str
    handler: Callable[..., dict[str, Any]]


def build_tool_registry(application: RenderDocApplication) -> list[ToolRegistration]:
    return [
        ToolRegistration(
            "renderdoc_open_capture",
            "Open a RenderDoc capture and return a capture_id plus basic metadata.",
            application.captures.renderdoc_open_capture,
        ),
        ToolRegistration(
            "renderdoc_close_capture",
            "Close an open RenderDoc capture session by capture_id.",
            application.captures.renderdoc_close_capture,
        ),
        ToolRegistration(
            "renderdoc_get_capture_summary",
            "Return frame, API, action-count, and resource-count summary data for an open capture.",
            application.captures.renderdoc_get_capture_summary,
        ),
        ToolRegistration(
            "renderdoc_analyze_frame",
            "Analyze an open RenderDoc capture into top-level passes, hotspots, and a tail UI/present chain.",
            application.captures.renderdoc_analyze_frame,
        ),
        ToolRegistration(
            "renderdoc_get_action_tree",
            "Return a tree preview of the action hierarchy for an open RenderDoc capture.",
            application.actions.renderdoc_get_action_tree,
        ),
        ToolRegistration(
            "renderdoc_list_actions",
            "List actions in flat preorder with pagination for an open RenderDoc capture.",
            application.actions.renderdoc_list_actions,
        ),
        ToolRegistration(
            "renderdoc_list_passes",
            "List analyzed top-level frame passes with pagination, filtering, and sorting.",
            application.captures.renderdoc_list_passes,
        ),
        ToolRegistration(
            "renderdoc_get_pass_details",
            "Fetch the full analyzed pass structure for a pass_id in an open capture.",
            application.captures.renderdoc_get_pass_details,
        ),
        ToolRegistration(
            "renderdoc_get_timing_data",
            "Fetch per-event GPU timing data for a pass_id when supported by the replay device.",
            application.captures.renderdoc_get_timing_data,
        ),
        ToolRegistration(
            "renderdoc_get_performance_hotspots",
            "Rank passes and individual events by GPU timing or heuristics.",
            application.captures.renderdoc_get_performance_hotspots,
        ),
        ToolRegistration(
            "renderdoc_get_action_details",
            "Fetch details for a specific RenderDoc event_id.",
            application.actions.renderdoc_get_action_details,
        ),
        ToolRegistration(
            "renderdoc_get_pipeline_state",
            "Fetch the API-agnostic pipeline state at a specific RenderDoc event_id.",
            application.actions.renderdoc_get_pipeline_state,
        ),
        ToolRegistration(
            "renderdoc_get_api_pipeline_state",
            "Fetch API-specific pipeline state details for a specific RenderDoc event_id.",
            application.actions.renderdoc_get_api_pipeline_state,
        ),
        ToolRegistration(
            "renderdoc_get_shader_code",
            "Fetch shader disassembly text for a specific shader stage at a RenderDoc event.",
            application.actions.renderdoc_get_shader_code,
        ),
        ToolRegistration(
            "renderdoc_list_resources",
            "List texture and buffer resources in an open RenderDoc capture.",
            application.resources.renderdoc_list_resources,
        ),
        ToolRegistration(
            "renderdoc_get_pixel_history",
            "Inspect the ordered pixel history for a texture pixel and subresource.",
            application.resources.renderdoc_get_pixel_history,
        ),
        ToolRegistration(
            "renderdoc_debug_pixel",
            "Summarize the draw or GPU events that affected a texture pixel.",
            application.resources.renderdoc_debug_pixel,
        ),
        ToolRegistration(
            "renderdoc_get_texture_data",
            "Return a JSON-friendly pixel preview grid for a selected texture region and subresource.",
            application.resources.renderdoc_get_texture_data,
        ),
        ToolRegistration(
            "renderdoc_get_buffer_data",
            "Return a bounded raw byte window from a buffer resource.",
            application.resources.renderdoc_get_buffer_data,
        ),
        ToolRegistration(
            "renderdoc_save_texture_to_file",
            "Save a texture resource to disk, inferring the export type from the output extension.",
            application.resources.renderdoc_save_texture_to_file,
        ),
    ]


def build_resource_registry(application: RenderDocApplication) -> list[ResourceRegistration]:
    return [
        ResourceRegistration(
            "renderdoc://recent-captures",
            "renderdoc_recent_captures",
            "Recent RenderDoc capture files from the local qrenderdoc UI config.",
            application.captures.renderdoc_recent_captures,
        ),
        ResourceRegistration(
            "renderdoc://capture/{capture_id}/summary",
            "renderdoc_capture_summary",
            "A JSON capture summary for an already-open RenderDoc capture session.",
            application.captures.renderdoc_capture_summary_resource,
        ),
    ]
