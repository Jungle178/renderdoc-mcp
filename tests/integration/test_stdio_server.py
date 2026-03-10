from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _find_capture() -> str | None:
    override = os.environ.get("RENDERDOC_MCP_CAPTURE")
    if override and Path(override).is_file():
        return str(Path(override).resolve())

    documents = Path.home() / "Documents"
    if documents.is_dir():
        for path in sorted(documents.glob("*.rdc")):
            return str(path.resolve())
    return None


@pytest.mark.integration
def test_stdio_tools_and_resources() -> None:
    capture_path = _find_capture()
    if capture_path is None:
        pytest.skip("No local .rdc capture was found for integration testing.")

    async def run_test() -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "renderdoc_mcp"],
            env=os.environ.copy(),
        )

        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()

                tool_names = {tool.name for tool in (await session.list_tools()).tools}
                assert {
                    "renderdoc_open_capture",
                    "renderdoc_close_capture",
                    "renderdoc_get_capture_summary",
                    "renderdoc_analyze_frame",
                    "renderdoc_get_action_tree",
                    "renderdoc_list_actions",
                    "renderdoc_list_passes",
                    "renderdoc_get_pass_details",
                    "renderdoc_get_timing_data",
                    "renderdoc_get_performance_hotspots",
                    "renderdoc_get_action_details",
                    "renderdoc_get_pipeline_state",
                    "renderdoc_get_api_pipeline_state",
                    "renderdoc_get_shader_code",
                    "renderdoc_list_resources",
                    "renderdoc_get_pixel_history",
                    "renderdoc_debug_pixel",
                    "renderdoc_get_texture_data",
                    "renderdoc_get_buffer_data",
                    "renderdoc_save_texture_to_file",
                }.issubset(tool_names)

                opened = await session.call_tool("renderdoc_open_capture", {"capture_path": capture_path})
                assert not opened.isError
                opened_payload = opened.structuredContent
                assert opened_payload is not None
                capture_id = opened_payload["capture_id"]

                summary = await session.call_tool("renderdoc_get_capture_summary", {"capture_id": capture_id})
                assert not summary.isError
                assert summary.structuredContent["capture_id"] == capture_id

                action_tree = await session.call_tool(
                    "renderdoc_get_action_tree",
                    {"capture_id": capture_id, "max_depth": 1},
                )
                assert not action_tree.isError
                assert "page" in action_tree.structuredContent["meta"]

                paged_actions = await session.call_tool(
                    "renderdoc_list_actions",
                    {"capture_id": capture_id, "cursor": 0, "limit": 25},
                )
                assert not paged_actions.isError
                assert paged_actions.structuredContent["meta"]["page"]["limit"] == 25
                flat_actions = paged_actions.structuredContent["actions"]
                assert flat_actions is not None

                analysis = await session.call_tool("renderdoc_analyze_frame", {"capture_id": capture_id})
                assert not analysis.isError
                analysis_payload = analysis.structuredContent
                assert analysis_payload["capture_id"] == capture_id
                assert "meta" in analysis_payload

                timed_analysis = await session.call_tool(
                    "renderdoc_analyze_frame",
                    {"capture_id": capture_id, "include_timing_summary": True},
                )
                assert not timed_analysis.isError
                assert "timing" in timed_analysis.structuredContent["meta"]

                listed_passes = await session.call_tool(
                    "renderdoc_list_passes",
                    {"capture_id": capture_id, "limit": 10},
                )
                assert not listed_passes.isError
                assert listed_passes.structuredContent["meta"]["page"]["returned_count"] > 0
                first_pass_id = listed_passes.structuredContent["passes"][0]["pass_id"]

                timed_passes = await session.call_tool(
                    "renderdoc_list_passes",
                    {"capture_id": capture_id, "limit": 10, "sort_by": "gpu_time"},
                )
                assert not timed_passes.isError
                assert timed_passes.structuredContent["effective_sort_by"] in {"gpu_time", "event_order"}

                pass_details = await session.call_tool(
                    "renderdoc_get_pass_details",
                    {"capture_id": capture_id, "pass_id": first_pass_id},
                )
                assert not pass_details.isError
                assert pass_details.structuredContent["pass_id"] == first_pass_id

                timing = await session.call_tool(
                    "renderdoc_get_timing_data",
                    {"capture_id": capture_id, "pass_id": first_pass_id},
                )
                assert not timing.isError
                assert timing.structuredContent["pass"]["pass_id"] == first_pass_id

                hotspots = await session.call_tool(
                    "renderdoc_get_performance_hotspots",
                    {"capture_id": capture_id},
                )
                assert not hotspots.isError
                assert "timing" in hotspots.structuredContent["meta"]

                first_event = flat_actions[0]["event_id"]
                details = await session.call_tool(
                    "renderdoc_get_action_details",
                    {"capture_id": capture_id, "event_id": first_event},
                )
                assert not details.isError
                assert details.structuredContent["action"]["event_id"] == first_event

                pipeline = await session.call_tool(
                    "renderdoc_get_pipeline_state",
                    {"capture_id": capture_id, "event_id": first_event},
                )
                assert not pipeline.isError
                assert pipeline.structuredContent["event_id"] == first_event

                api_pipeline = await session.call_tool(
                    "renderdoc_get_api_pipeline_state",
                    {"capture_id": capture_id, "event_id": first_event},
                )
                assert not api_pipeline.isError
                assert "api_pipeline" in api_pipeline.structuredContent

                shader_probe = await session.call_tool(
                    "renderdoc_list_actions",
                    {"capture_id": capture_id, "cursor": 0, "limit": 100},
                )
                assert not shader_probe.isError

                shader_event = None
                shader_stage = None
                for item in shader_probe.structuredContent["actions"]:
                    if not {"draw", "dispatch"}.intersection(item["flags"]):
                        continue
                    candidate = await session.call_tool(
                        "renderdoc_get_pipeline_state",
                        {"capture_id": capture_id, "event_id": item["event_id"]},
                    )
                    assert not candidate.isError
                    shaders = candidate.structuredContent["pipeline"]["shaders"]
                    if shaders:
                        shader_event = item["event_id"]
                        shader_stage = shaders[0]["stage"]
                        break

                if shader_event is not None and shader_stage is not None:
                    shader_code = await session.call_tool(
                        "renderdoc_get_shader_code",
                        {
                            "capture_id": capture_id,
                            "event_id": shader_event,
                            "stage": shader_stage,
                        },
                    )
                    assert not shader_code.isError
                    assert shader_code.structuredContent["shader"]["stage"] == shader_stage

                resources = await session.call_tool(
                    "renderdoc_list_resources",
                    {"capture_id": capture_id, "kind": "all"},
                )
                assert not resources.isError
                textures = resources.structuredContent["textures"]
                buffers = resources.structuredContent["buffers"]

                first_texture = next(
                    (
                        item
                        for item in textures
                        if item["resource_id"] and item["width"] > 0 and item["height"] > 0
                    ),
                    None,
                )
                if first_texture is not None:
                    pixel_history = await session.call_tool(
                        "renderdoc_get_pixel_history",
                        {
                            "capture_id": capture_id,
                            "texture_id": first_texture["resource_id"],
                            "x": 0,
                            "y": 0,
                        },
                    )
                    assert not pixel_history.isError

                    pixel_debug = await session.call_tool(
                        "renderdoc_debug_pixel",
                        {
                            "capture_id": capture_id,
                            "texture_id": first_texture["resource_id"],
                            "x": 0,
                            "y": 0,
                        },
                    )
                    assert not pixel_debug.isError

                    texture_preview = await session.call_tool(
                        "renderdoc_get_texture_data",
                        {
                            "capture_id": capture_id,
                            "texture_id": first_texture["resource_id"],
                            "mip_level": 0,
                            "x": 0,
                            "y": 0,
                            "width": min(4, first_texture["width"]),
                            "height": min(4, first_texture["height"]),
                        },
                    )
                    assert not texture_preview.isError

                    with tempfile.TemporaryDirectory() as temp_dir:
                        output_path = str(Path(temp_dir) / "texture.png")
                        saved_texture = await session.call_tool(
                            "renderdoc_save_texture_to_file",
                            {
                                "capture_id": capture_id,
                                "texture_id": first_texture["resource_id"],
                                "output_path": output_path,
                            },
                        )
                        assert not saved_texture.isError
                        assert Path(output_path).is_file()

                first_buffer = next((item for item in buffers if item["resource_id"] and item["byte_size"] > 0), None)
                if first_buffer is not None:
                    buffer_size = min(32, first_buffer["byte_size"])
                    buffer_data = await session.call_tool(
                        "renderdoc_get_buffer_data",
                        {
                            "capture_id": capture_id,
                            "buffer_id": first_buffer["resource_id"],
                            "offset": 0,
                            "size": buffer_size,
                        },
                    )
                    assert not buffer_data.isError
                    assert buffer_data.structuredContent["buffer"]["resource_id"] == first_buffer["resource_id"]

                resource_contents = await session.read_resource("renderdoc://recent-captures")
                assert resource_contents.contents

                capture_resource = await session.read_resource("renderdoc://capture/{}/summary".format(capture_id))
                assert capture_resource.contents

                invalid_capture = await session.call_tool("renderdoc_get_capture_summary", {"capture_id": "deadbeef"})
                assert invalid_capture.isError

                invalid_event = await session.call_tool(
                    "renderdoc_get_action_details",
                    {"capture_id": capture_id, "event_id": 999999999},
                )
                assert invalid_event.isError

                closed = await session.call_tool("renderdoc_close_capture", {"capture_id": capture_id})
                assert not closed.isError
                after_close = await session.call_tool("renderdoc_get_capture_summary", {"capture_id": capture_id})
                assert after_close.isError

    anyio.run(run_test)
