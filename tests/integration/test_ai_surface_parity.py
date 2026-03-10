from __future__ import annotations

import io
import os
import subprocess
import sys
import tarfile
import tempfile
from collections import deque
from pathlib import Path
from typing import Any

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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _find_legacy_surface_ref() -> str:
    repo_root = _repo_root()
    if not (repo_root / ".git").exists():
        pytest.skip("The AI parity test requires a local git checkout.")

    history = subprocess.run(
        ["git", "rev-list", "--max-count", "20", "HEAD"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
        timeout=10.0,
    )
    if history.returncode != 0:
        pytest.skip(f"Unable to inspect git history: {history.stderr.strip()}")

    refs = [line.strip() for line in history.stdout.splitlines() if line.strip()]
    for ref in refs[1:]:
        probe = subprocess.run(
            [
                "git",
                "grep",
                "-n",
                "def renderdoc_get_capture_summary",
                ref,
                "--",
                "src/renderdoc_mcp/application/handlers/captures.py",
            ],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=10.0,
        )
        if probe.returncode == 0:
            return ref

    pytest.skip("Unable to find a recent git ref that still exposes the legacy MCP surface.")


def _extract_git_ref(ref: str, destination: Path) -> None:
    repo_root = _repo_root()
    if not (repo_root / ".git").exists():
        pytest.skip("The AI parity test requires a local git checkout.")

    result = subprocess.run(
        ["git", "archive", "--format=tar", ref],
        cwd=str(repo_root),
        capture_output=True,
        check=False,
        timeout=30.0,
    )
    if result.returncode != 0:
        pytest.skip(f"Unable to archive git ref {ref!r}: {result.stderr.decode('utf-8', errors='replace')}")

    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
        archive.extractall(destination)


def _server_env(src_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("RENDERDOC_BRIDGE_TIMEOUT_SECONDS", "180")
    env["PYTHONPATH"] = str(src_root / "src")
    return env


async def _call_tool(session: ClientSession, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await session.call_tool(name, arguments)
    assert not result.isError, f"{name} failed: {result.content}"
    payload = result.structuredContent
    assert payload is not None
    return payload


async def _collect_legacy_flat_actions(session: ClientSession, capture_id: str) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    cursor = 0
    while True:
        payload = await _call_tool(
            session,
            "renderdoc_list_actions",
            {"capture_id": capture_id, "cursor": cursor, "limit": 200},
        )
        actions.extend(payload["actions"])
        next_cursor = payload["meta"]["page"]["next_cursor"]
        if not next_cursor:
            return actions
        cursor = int(next_cursor)


async def _collect_current_action_tree(session: ClientSession, capture_id: str) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    queue: deque[int | None] = deque([None])
    visited_parents: set[int | None] = set()

    while queue:
        parent_event_id = queue.popleft()
        if parent_event_id in visited_parents:
            continue
        visited_parents.add(parent_event_id)

        cursor = 0
        while True:
            arguments: dict[str, Any] = {"capture_id": capture_id, "cursor": cursor, "limit": 200}
            if parent_event_id is not None:
                arguments["parent_event_id"] = parent_event_id

            payload = await _call_tool(session, "renderdoc_list_actions", arguments)
            batch = payload["actions"]
            actions.extend(batch)
            for item in batch:
                if int(item.get("child_count", 0)) > 0:
                    queue.append(int(item["event_id"]))

            next_cursor = payload["meta"]["page"]["next_cursor"]
            if not next_cursor:
                break
            cursor = int(next_cursor)

    return actions


async def _collect_current_resources(session: ClientSession, capture_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor = 0
    while True:
        payload = await _call_tool(
            session,
            "renderdoc_list_resources",
            {"capture_id": capture_id, "kind": "all", "cursor": cursor, "limit": 200, "sort_by": "name"},
        )
        items.extend(payload["items"])
        next_cursor = payload["meta"]["page"]["next_cursor"]
        if not next_cursor:
            return items
        cursor = int(next_cursor)


async def _collect_current_timing_events(session: ClientSession, capture_id: str, pass_id: str) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    cursor = 0
    total_gpu_time_ms = None
    basis = "unavailable"

    while True:
        payload = await _call_tool(
            session,
            "renderdoc_list_timing_events",
            {
                "capture_id": capture_id,
                "pass_id": pass_id,
                "cursor": cursor,
                "limit": 500,
                "sort_by": "event_order",
            },
        )
        events.extend(payload["events"])
        total_gpu_time_ms = payload["total_gpu_time_ms"]
        basis = payload["basis"]
        next_cursor = payload["meta"]["page"]["next_cursor"]
        if not next_cursor:
            return {
                "basis": basis,
                "events": events,
                "timed_event_count": payload["timed_event_count"],
                "total_gpu_time_ms": total_gpu_time_ms,
            }
        cursor = int(next_cursor)


async def _collect_current_shader_text(
    session: ClientSession,
    capture_id: str,
    event_id: int,
    stage: str,
) -> dict[str, Any]:
    lines: list[str] = []
    start_line = 1
    first_payload: dict[str, Any] | None = None

    while True:
        payload = await _call_tool(
            session,
            "renderdoc_get_shader_code_chunk",
            {
                "capture_id": capture_id,
                "event_id": event_id,
                "stage": stage,
                "start_line": start_line,
                "line_count": 200,
            },
        )
        if first_payload is None:
            first_payload = payload
        lines.extend(payload["text"].splitlines())
        if not payload["has_more"]:
            assert first_payload is not None
            return {
                "payload": first_payload,
                "lines": lines,
            }
        start_line += int(payload["returned_line_count"])


def _choose_representative_event(pass_summary: dict[str, Any]) -> int:
    for event in pass_summary.get("representative_events", []):
        flags = set(event.get("flags", []))
        if flags.intersection({"draw", "dispatch"}):
            return int(event["event_id"])
    return int(pass_summary["event_range"]["start_event_id"])


def _choose_resource(resources: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in resources:
        if item.get("kind") == "texture":
            return item
    return resources[0] if resources else None


def _action_signature(item: dict[str, Any]) -> tuple[str, tuple[str, ...], int | None, int, int]:
    parent_event_id = item.get("parent_event_id")
    normalized_parent = int(parent_event_id) if parent_event_id not in (None, "") else None
    return (
        str(item["name"]),
        tuple(sorted(str(flag) for flag in item.get("flags", []))),
        normalized_parent,
        int(item.get("child_count", 0)),
        int(item.get("depth", 0)),
    )


def _root_pass_signature(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item["pass_id"]),
        str(item["name"]),
        str(item["category"]),
    )


def _trim_trailing_empty_lines(lines: list[str]) -> list[str]:
    trimmed = list(lines)
    while trimmed and trimmed[-1] == "":
        trimmed.pop()
    return trimmed


def _current_resource_signature(item: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "kind": item["kind"],
        "resource_id": item["resource_id"],
        "name": item["name"],
        "byte_size": int(item["byte_size"]),
    }
    if item["kind"] == "texture":
        payload.update(
            {
                "dimension": item["dimension"],
                "width": int(item["width"]),
                "height": int(item["height"]),
                "mips": int(item["mips"]),
                "sample_count": int(item["sample_count"]),
            }
        )
    else:
        payload["usage_flags"] = item["usage_flags"]
    return payload


def _legacy_resource_signature(item: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "kind": item["kind"],
        "resource_id": item["resource_id"],
        "name": item["name"],
        "byte_size": int(item["byte_size"]),
    }
    if item["kind"] == "texture":
        payload.update(
            {
                "dimension": item["dimension"],
                "width": int(item["width"]),
                "height": int(item["height"]),
                "mips": int(item["mip_levels"]),
                "sample_count": int(item["sample_count"]),
            }
        )
    else:
        payload["usage_flags"] = item["creation_flags"]
    return payload


async def _collect_current_semantics(capture_path: str, src_root: Path) -> dict[str, Any]:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "renderdoc_mcp"],
        env=_server_env(src_root),
    )

    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            opened = await _call_tool(session, "renderdoc_open_capture", {"capture_path": capture_path})
            capture_id = opened["capture_id"]
            try:
                overview = await _call_tool(session, "renderdoc_get_capture_overview", {"capture_id": capture_id})
                worklist = await _call_tool(
                    session,
                    "renderdoc_get_analysis_worklist",
                    {"capture_id": capture_id, "focus": "performance", "limit": 10},
                )
                root_passes = await _call_tool(
                    session,
                    "renderdoc_list_passes",
                    {"capture_id": capture_id, "limit": 200, "sort_by": "event_order"},
                )
                full_actions = await _collect_current_action_tree(session, capture_id)
                full_resources = await _collect_current_resources(session, capture_id)

                chosen_pass_id = next(
                    (
                        str(item["id"])
                        for item in worklist.get("items", [])
                        if item.get("kind") == "pass" and item.get("id")
                    ),
                    str(root_passes["passes"][0]["pass_id"]),
                )
                pass_summary = await _call_tool(
                    session,
                    "renderdoc_get_pass_summary",
                    {"capture_id": capture_id, "pass_id": chosen_pass_id},
                )
                timing = await _collect_current_timing_events(session, capture_id, chosen_pass_id)

                chosen_event_id = _choose_representative_event(pass_summary)
                action_summary = await _call_tool(
                    session,
                    "renderdoc_get_action_summary",
                    {"capture_id": capture_id, "event_id": chosen_event_id},
                )
                pipeline_overview = await _call_tool(
                    session,
                    "renderdoc_get_pipeline_overview",
                    {"capture_id": capture_id, "event_id": chosen_event_id},
                )

                stage = None
                shader_summary = None
                shader_text = None
                shaders = pipeline_overview["pipeline"]["shaders"]
                if shaders:
                    stage = str(shaders[0]["stage"])
                    shader_summary = await _call_tool(
                        session,
                        "renderdoc_get_shader_summary",
                        {"capture_id": capture_id, "event_id": chosen_event_id, "stage": stage},
                    )
                    shader_text = await _collect_current_shader_text(session, capture_id, chosen_event_id, stage)

                selected_resource = _choose_resource(full_resources)
                resource_summary = None
                if selected_resource is not None:
                    resource_summary = await _call_tool(
                        session,
                        "renderdoc_get_resource_summary",
                        {"capture_id": capture_id, "resource_id": selected_resource["resource_id"]},
                    )

                return {
                    "opened": opened,
                    "overview": overview,
                    "worklist": worklist,
                    "root_passes": root_passes["passes"],
                    "actions": full_actions,
                    "resources": full_resources,
                    "pass_summary": pass_summary,
                    "timing": timing,
                    "action_summary": action_summary,
                    "pipeline_overview": pipeline_overview,
                    "shader_summary": shader_summary,
                    "shader_text": shader_text,
                    "selected_resource": selected_resource,
                    "resource_summary": resource_summary,
                    "selected_event_id": chosen_event_id,
                    "selected_pass_id": chosen_pass_id,
                    "selected_stage": stage,
                }
            finally:
                await _call_tool(session, "renderdoc_close_capture", {"capture_id": capture_id})


async def _collect_legacy_semantics(
    capture_path: str,
    src_root: Path,
    *,
    pass_id: str,
    event_id: int,
    stage: str | None,
) -> dict[str, Any]:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "renderdoc_mcp"],
        env=_server_env(src_root),
    )

    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            opened = await _call_tool(session, "renderdoc_open_capture", {"capture_path": capture_path})
            capture_id = opened["capture_id"]
            try:
                summary = await _call_tool(session, "renderdoc_get_capture_summary", {"capture_id": capture_id})
                analysis = await _call_tool(
                    session,
                    "renderdoc_analyze_frame",
                    {"capture_id": capture_id, "include_timing_summary": True},
                )
                root_passes = await _call_tool(
                    session,
                    "renderdoc_list_passes",
                    {"capture_id": capture_id, "limit": 200, "sort_by": "event_order"},
                )
                root_actions = await _call_tool(
                    session,
                    "renderdoc_get_action_tree",
                    {"capture_id": capture_id, "max_depth": 0, "limit": 500},
                )
                actions = await _collect_legacy_flat_actions(session, capture_id)
                resources = await _call_tool(session, "renderdoc_list_resources", {"capture_id": capture_id, "kind": "all"})
                pass_details = await _call_tool(
                    session,
                    "renderdoc_get_pass_details",
                    {"capture_id": capture_id, "pass_id": pass_id},
                )
                timing = await _call_tool(
                    session,
                    "renderdoc_get_timing_data",
                    {"capture_id": capture_id, "pass_id": pass_id},
                )
                action_details = await _call_tool(
                    session,
                    "renderdoc_get_action_details",
                    {"capture_id": capture_id, "event_id": event_id},
                )
                pipeline_state = await _call_tool(
                    session,
                    "renderdoc_get_pipeline_state",
                    {"capture_id": capture_id, "event_id": event_id},
                )

                shader_code = None
                if stage:
                    shader_code = await _call_tool(
                        session,
                        "renderdoc_get_shader_code",
                        {"capture_id": capture_id, "event_id": event_id, "stage": stage},
                    )

                return {
                    "opened": opened,
                    "summary": summary,
                    "analysis": analysis,
                    "root_passes": root_passes["passes"],
                    "root_actions": root_actions["actions"],
                    "actions": actions,
                    "resources": resources["items"],
                    "pass_details": pass_details,
                    "timing": timing,
                    "action_details": action_details,
                    "pipeline_state": pipeline_state,
                    "shader_code": shader_code,
                }
            finally:
                await _call_tool(session, "renderdoc_close_capture", {"capture_id": capture_id})


@pytest.mark.integration
def test_ai_surface_semantic_parity() -> None:
    capture_path = _find_capture()
    if capture_path is None:
        pytest.skip("No local .rdc capture was found for parity testing.")

    async def run_test() -> None:
        current_root = _repo_root()
        legacy_ref = _find_legacy_surface_ref()
        with tempfile.TemporaryDirectory(prefix="renderdoc_mcp_legacy_") as temp_dir:
            legacy_root = Path(temp_dir) / "legacy"
            _extract_git_ref(legacy_ref, legacy_root)

            current = await _collect_current_semantics(capture_path, current_root)
            legacy = await _collect_legacy_semantics(
                capture_path,
                legacy_root,
                pass_id=current["selected_pass_id"],
                event_id=current["selected_event_id"],
                stage=current["selected_stage"],
            )

        assert current["overview"]["api"] == legacy["summary"]["api"]
        assert current["overview"]["frame"] == legacy["summary"]["frame"]
        assert current["overview"]["statistics"] == legacy["summary"]["statistics"]
        assert current["overview"]["resource_counts"] == legacy["summary"]["resource_counts"]
        assert current["overview"]["root_pass_count"] == len(legacy["root_passes"])
        assert current["overview"]["action_root_count"] == len(legacy["root_actions"])

        assert [_root_pass_signature(item) for item in current["root_passes"]] == [
            _root_pass_signature(item) for item in legacy["root_passes"]
        ]

        current_action_map = {int(item["event_id"]): _action_signature(item) for item in current["actions"]}
        legacy_action_map = {int(item["event_id"]): _action_signature(item) for item in legacy["actions"]}
        assert current_action_map == legacy_action_map

        current_resource_ids = {str(item["resource_id"]) for item in current["resources"]}
        legacy_resource_ids = {str(item["resource_id"]) for item in legacy["resources"]}
        assert current_resource_ids == legacy_resource_ids

        current_pass = {
            "pass_id": current["pass_summary"]["pass_id"],
            "name": current["pass_summary"]["name"],
            "category": current["pass_summary"]["category"],
            "confidence": current["pass_summary"]["confidence"],
            "reasons": current["pass_summary"]["reasons"],
            "level": current["pass_summary"]["level"],
            "event_range": current["pass_summary"]["event_range"],
            "stats": current["pass_summary"]["stats"],
            "output_summary": current["pass_summary"]["output_summary"],
            "representative_events": current["pass_summary"]["representative_events"],
            "child_pass_count": current["pass_summary"].get("child_pass_count", 0),
        }
        legacy_pass = {
            "pass_id": legacy["pass_details"]["pass_id"],
            "name": legacy["pass_details"]["name"],
            "category": legacy["pass_details"]["category"],
            "confidence": legacy["pass_details"]["confidence"],
            "reasons": legacy["pass_details"]["reasons"],
            "level": legacy["pass_details"]["level"],
            "event_range": legacy["pass_details"]["event_range"],
            "stats": legacy["pass_details"]["stats"],
            "output_summary": legacy["pass_details"]["output_summary"],
            "representative_events": legacy["pass_details"]["representative_events"],
            "child_pass_count": legacy["pass_details"].get("child_pass_count", 0),
        }
        assert current_pass == legacy_pass

        assert current["timing"]["basis"] == legacy["timing"]["basis"]
        assert current["timing"]["timed_event_count"] == legacy["timing"]["timed_event_count"]
        assert current["timing"]["total_gpu_time_ms"] == pytest.approx(
            legacy["timing"]["total_gpu_time_ms"],
            abs=1e-3,
        )
        assert len(current["timing"]["events"]) == len(legacy["timing"]["events"])
        for current_item, legacy_item in zip(current["timing"]["events"], legacy["timing"]["events"], strict=True):
            assert int(current_item["event_id"]) == int(legacy_item["event_id"])
            assert str(current_item["name"]) == str(legacy_item["name"])
            assert float(current_item["gpu_time_ms"]) == pytest.approx(float(legacy_item["gpu_time_ms"]), abs=1e-3)

        current_action = current["action_summary"]["action"]
        legacy_action = legacy["action_details"]["action"]
        legacy_action_signature = legacy_action_map[int(current_action["event_id"])]
        assert current_action["event_id"] == legacy_action["event_id"]
        assert current_action["name"] == legacy_action["name"]
        assert set(current_action["flags"]) == set(legacy_action["flags"])
        assert current_action["depth"] == legacy_action_signature[4]
        assert current_action["child_count"] == legacy_action_signature[3]
        assert current_action["parent_event_id"] == legacy_action_signature[2]
        assert current_action["num_indices"] == legacy_action["num_indices"]
        assert current_action["num_instances"] == legacy_action["num_instances"]
        assert current_action["dispatch_dimension"] == legacy_action["dispatch_dimension"]
        assert current_action["dispatch_threads_dimension"] == legacy_action["dispatch_threads_dimension"]
        assert current_action["resource_usage_summary"]["output_count"] == legacy_action["resource_usage_summary"][
            "output_count"
        ]
        assert current_action["resource_usage_summary"]["has_depth_output"] == legacy_action["resource_usage_summary"][
            "has_depth_output"
        ]

        current_pipeline = current["pipeline_overview"]["pipeline"]
        legacy_pipeline = legacy["pipeline_state"]["pipeline"]
        assert current_pipeline["available"] == legacy_pipeline["available"]
        assert current_pipeline["topology"] == legacy_pipeline["topology"]
        assert current_pipeline["graphics_pipeline_object"] == legacy_pipeline["graphics_pipeline_object"]
        assert current_pipeline["compute_pipeline_object"] == legacy_pipeline["compute_pipeline_object"]
        assert current_pipeline["counts"]["descriptor_accesses"] == len(legacy_pipeline["descriptor_accesses"])
        assert current_pipeline["counts"]["vertex_buffers"] == len(legacy_pipeline["vertex_buffers"])
        assert current_pipeline["counts"]["vertex_inputs"] == len(legacy_pipeline["vertex_inputs"])
        assert current_pipeline["counts"]["output_targets"] == (
            len(legacy_pipeline["output_targets"])
            + int(bool((legacy_pipeline["depth_target"] or {}).get("resource_id")))
            + int(bool((legacy_pipeline["depth_resolve_target"] or {}).get("resource_id")))
        )
        assert current_pipeline["counts"]["shaders"] == len(legacy_pipeline["shaders"])
        assert [
            (item["stage"], item["shader_id"], item["shader_name"], item["entry_point"])
            for item in current_pipeline["shaders"]
        ] == [
            (item["stage"], item["shader_id"], item["shader_name"], item["entry_point"])
            for item in legacy_pipeline["shaders"]
        ]

        selected_resource = current["selected_resource"]
        if selected_resource is not None and current["resource_summary"] is not None:
            legacy_resource_map = {str(item["resource_id"]): item for item in legacy["resources"]}
            legacy_resource = legacy_resource_map[selected_resource["resource_id"]]
            assert _current_resource_signature(current["resource_summary"]["resource"]) == _legacy_resource_signature(
                legacy_resource
            )

        if current["shader_summary"] is not None and current["shader_text"] is not None and legacy["shader_code"] is not None:
            current_shader = current["shader_summary"]["shader"]
            legacy_shader = legacy["shader_code"]["shader"]
            assert current_shader["stage"] == legacy_shader["stage"]
            assert current_shader["shader_id"] == legacy_shader["shader_id"]
            assert current_shader["shader_name"] == legacy_shader["shader_name"]
            assert current_shader["entry_point"] == legacy_shader["entry_point"]
            assert current_shader["counts"]["read_only_resources"] == len(legacy_shader["read_only_resources"])
            assert current_shader["counts"]["read_write_resources"] == len(legacy_shader["read_write_resources"])
            assert current_shader["counts"]["samplers"] == len(legacy_shader["samplers"])
            assert current_shader["counts"]["constant_blocks"] == len(legacy_shader["constant_blocks"])
            assert set(current["shader_summary"]["disassembly"]["available_targets"]) == set(
                legacy["shader_code"]["disassembly"]["available_targets"]
            )
            assert _trim_trailing_empty_lines(current["shader_text"]["lines"]) == _trim_trailing_empty_lines(
                legacy["shader_code"]["disassembly"]["text"].splitlines()
            )

    anyio.run(run_test)
