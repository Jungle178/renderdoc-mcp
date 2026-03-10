from __future__ import annotations

from renderdoc_mcp.analysis import frame_analysis


def _resource(name: str) -> dict[str, str]:
    return {"resource_id": name.lower(), "resource_name": name}


def _action(
    event_id: int,
    name: str,
    flags: list[str] | None = None,
    outputs: list[dict[str, str]] | None = None,
    depth_output: dict[str, str] | None = None,
    children: list[dict] | None = None,
    num_indices: int = 0,
    num_instances: int = 1,
    dispatch_dimension: list[int] | None = None,
    dispatch_threads_dimension: list[int] | None = None,
) -> dict:
    payload = {
        "event_id": event_id,
        "action_id": event_id,
        "name": name,
        "custom_name": "",
        "flags": list(flags or []),
        "child_count": 0,
        "is_fake_marker": False,
        "num_indices": num_indices,
        "num_instances": num_instances,
        "dispatch_dimension": list(dispatch_dimension or [0, 0, 0]),
        "dispatch_threads_dimension": list(dispatch_threads_dimension or [0, 0, 0]),
        "outputs": list(outputs or []),
        "depth_output": depth_output or {"resource_id": "", "resource_name": ""},
        "parent_event_id": None,
        "children": list(children or []),
    }

    for child in payload["children"]:
        child["parent_event_id"] = event_id
    payload["child_count"] = len(payload["children"])
    return payload


def _count_stats(nodes: list[dict]) -> dict[str, int]:
    stats = {"total_actions": 0, "draw_calls": 0, "dispatches": 0, "copies": 0, "clears": 0}
    for node in nodes:
        stats["total_actions"] += 1
        flags = set(node["flags"])
        if "draw" in flags:
            stats["draw_calls"] += 1
        if "dispatch" in flags:
            stats["dispatches"] += 1
        if "copy" in flags:
            stats["copies"] += 1
        if "clear" in flags:
            stats["clears"] += 1
        child_stats = _count_stats(node["children"])
        for key, value in child_stats.items():
            stats[key] += value
    return stats


def _metadata(nodes: list[dict]) -> dict:
    return {
        "capture": {"loaded": True, "filename": "sample.rdc"},
        "api": "D3D12",
        "frame": {"frame_number": 1},
        "statistics": _count_stats(nodes),
        "resource_counts": {"textures": 4, "buffers": 2},
    }


def test_build_frame_analysis_classifies_common_pass_shapes() -> None:
    nodes = [
        _action(
            10,
            "Shadow Map Atlas",
            ["push_marker"],
            children=[_action(11, "Draw", ["draw"], depth_output=_resource("ShadowDepth"))],
        ),
        _action(
            20,
            "Depth PrePass",
            ["push_marker"],
            children=[_action(21, "Draw", ["draw"], depth_output=_resource("SceneDepth"))],
        ),
        _action(
            30,
            "BasePass",
            ["push_marker"],
            children=[
                _action(
                    31,
                    "Draw",
                    ["draw"],
                    outputs=[_resource("GBufferA"), _resource("GBufferB")],
                    depth_output=_resource("SceneDepth"),
                )
            ],
        ),
        _action(
            40,
            "Light Culling",
            ["push_marker"],
            children=[_action(41, "Dispatch", ["dispatch"])],
        ),
        _action(
            50,
            "Resolve History",
            ["push_marker"],
            children=[_action(51, "Resolve", ["resolve"])],
        ),
        _action(
            60,
            "SlateUI",
            ["push_marker"],
            children=[_action(61, "Draw", ["draw"], outputs=[_resource("Backbuffer")])],
        ),
        _action(70, "Present(Backbuffer)", []),
    ]

    analysis = frame_analysis.build_frame_analysis(nodes, _metadata(nodes))
    categories = {item["name"]: item["category"] for item in analysis["analysis"]["passes"]}

    assert categories["Shadow Map Atlas"] == "shadow_depth"
    assert categories["Depth PrePass"] == "depth_prepass"
    assert categories["BasePass"] == "geometry"
    assert categories["Light Culling"] == "lighting"
    assert categories["Resolve History"] == "copy_resolve"
    assert categories["SlateUI"] == "ui_overlay"
    assert categories["Present(Backbuffer)"] == "presentation"


def test_action_tree_and_flat_list_have_distinct_contracts() -> None:
    nodes = [_action(event_id, "Event {0}".format(event_id), ["draw"]) for event_id in range(1, 506)]

    tree = frame_analysis.build_action_tree_result(nodes, total_count=505)
    page = frame_analysis.build_action_list_result(nodes, total_count=505, cursor=500, limit=3)

    assert tree["meta"]["page_mode"] == "tree_preview"
    assert tree["meta"]["page"]["returned_count"] == 500
    assert tree["meta"]["page"]["has_more"] is True
    assert page["meta"]["page_mode"] == "flat_preorder"
    assert page["meta"]["page"]["returned_count"] == 3
    assert [item["event_id"] for item in page["actions"]] == [501, 502, 503]


def test_list_passes_uses_meta_page_and_timing_contract() -> None:
    nodes = [
        _action(
            100,
            "BasePass",
            ["push_marker"],
            children=[
                _action(101, "Depth", ["draw"], num_indices=120),
                _action(102, "Color", ["draw"], num_indices=240),
            ],
        ),
        _action(
            200,
            "Lighting",
            ["push_marker"],
            children=[_action(201, "Dispatch", ["dispatch"], dispatch_dimension=[8, 8, 1])],
        ),
    ]

    analysis = frame_analysis.build_frame_analysis(nodes, _metadata(nodes))
    result = frame_analysis.list_passes(
        analysis,
        sort_by="gpu_time",
        threshold_ms=1.0,
        timing_payload={
            "timing_available": True,
            "counter_name": "EventGPUDuration",
            "rows": [
                {"event_id": 101, "gpu_time_ms": 0.5},
                {"event_id": 102, "gpu_time_ms": 1.25},
                {"event_id": 201, "gpu_time_ms": 0.75},
            ],
        },
    )

    assert result["sort_by"] == "gpu_time"
    assert result["effective_sort_by"] == "gpu_time"
    assert result["meta"]["timing"]["timing_available"] is True
    assert result["meta"]["page"]["matched_count"] == 1
    assert result["passes"][0]["name"] == "BasePass"
    assert result["passes"][0]["gpu_time_ms"] == 1.75


def test_build_analysis_result_moves_warnings_and_timing_into_meta() -> None:
    nodes = [
        _action(
            100,
            "BasePass",
            ["push_marker"],
            children=[_action(101, "Depth", ["draw"]), _action(102, "Color", ["draw"])],
        ),
        _action(200, "Present", []),
    ]

    analysis = frame_analysis.build_frame_analysis(nodes, _metadata(nodes))
    result = frame_analysis.build_analysis_result(
        analysis,
        include_timing_summary=True,
        timing_payload={
            "timing_available": True,
            "counter_name": "EventGPUDuration",
            "rows": [
                {"event_id": 101, "gpu_time_ms": 0.25},
                {"event_id": 102, "gpu_time_ms": 0.75},
            ],
        },
    )

    assert "warnings" not in result
    assert result["meta"]["timing"]["timing_available"] is True
    assert isinstance(result["meta"].get("warnings", []), list)
    assert result["passes"][0]["gpu_time_ms"] == 1.0


def test_build_timing_result_and_hotspots_use_meta_timing() -> None:
    nodes = [
        _action(
            100,
            "BasePass",
            ["push_marker"],
            children=[_action(101, "Depth", ["draw"]), _action(102, "Color", ["draw"])],
        ),
        _action(
            200,
            "Compute",
            ["push_marker"],
            children=[_action(201, "Dispatch", ["dispatch"], dispatch_threads_dimension=[4, 4, 4])],
        ),
    ]

    analysis = frame_analysis.build_frame_analysis(nodes, _metadata(nodes))
    timing = frame_analysis.build_timing_result(
        analysis,
        "pass:100-102",
        {
            "timing_available": False,
            "counter_name": "EventGPUDuration",
            "rows": [],
            "reason": "unsupported",
        },
    )
    hotspots = frame_analysis.build_performance_hotspots(
        analysis,
        {"timing_available": False, "counter_name": "EventGPUDuration", "rows": [], "reason": "unsupported"},
    )

    assert timing is not None
    assert timing["basis"] == "unavailable"
    assert timing["meta"]["timing"]["timing_unavailable_reason"] == "unsupported"
    assert hotspots["basis"] == "heuristic"
    assert hotspots["meta"]["timing"]["timing_available"] is False
