from __future__ import annotations

from renderdoc_mcp.benchmark_ai_surface import (
    WORKFLOW_VERSION,
    build_delta,
    build_ref_comparison,
    build_scores,
    find_previous_entry,
    sanitize_call_args,
)


def test_build_scores_rewards_smaller_payload_and_lower_latency() -> None:
    compact = build_scores({"approx_tokens": 10_000, "total_elapsed_ms": 500.0})
    heavy = build_scores({"approx_tokens": 100_000, "total_elapsed_ms": 3_000.0})

    assert compact["payload_score"] > heavy["payload_score"]
    assert compact["latency_score"] > heavy["latency_score"]
    assert compact["composite_score"] > heavy["composite_score"]


def test_find_previous_entry_filters_by_workflow_and_capture() -> None:
    history = [
        {"workflow_version": "other", "capture": {"label": "0916"}},
        {"workflow_version": WORKFLOW_VERSION, "capture": {"label": "other"}},
        {"workflow_version": WORKFLOW_VERSION, "capture": {"label": "0916"}, "git": {"commit": "abc123"}},
    ]

    entry = find_previous_entry(history, WORKFLOW_VERSION, "0916")

    assert entry is not None
    assert entry["git"]["commit"] == "abc123"


def test_build_delta_reports_improvement_against_previous_result() -> None:
    previous = {
        "git": {"commit": "old"},
        "scores": {
            "payload_score": 400.0,
            "latency_score": 500.0,
            "composite_score": 415.0,
        },
        "summary": {
            "stages": {
                "interactive": {
                    "total_bytes": 50_000,
                    "approx_tokens": 12_500,
                    "total_elapsed_ms": 600.0,
                }
            }
        },
    }
    current = {
        "scores": {
            "payload_score": 600.0,
            "latency_score": 550.0,
            "composite_score": 592.5,
        },
        "summary": {
            "stages": {
                "interactive": {
                    "total_bytes": 20_000,
                    "approx_tokens": 5_000,
                    "total_elapsed_ms": 450.0,
                }
            }
        },
    }

    delta = build_delta(current, previous)

    assert delta is not None
    assert delta["vs_commit"] == "old"
    assert delta["payload_score_delta"] == 200.0
    assert delta["interactive_bytes_delta"] == -30_000
    assert delta["interactive_tokens_delta"] == -7_500
    assert delta["interactive_elapsed_ms_delta"] == -150.0


def test_build_ref_comparison_reports_percentages_and_startup_delta() -> None:
    baseline = {
        "git": {"commit": "old", "branch": "HEAD^"},
        "scores": {
            "payload_score": 100.0,
            "latency_score": 900.0,
            "composite_score": 220.0,
        },
        "summary": {
            "stages": {
                "interactive": {
                    "total_bytes": 100_000,
                    "approx_tokens": 25_000,
                    "total_elapsed_ms": 500.0,
                }
            }
        },
        "calls": [
            {
                "label": "open_capture",
                "bytes": 500,
                "approx_tokens": 125,
                "elapsed_ms": 4_000.0,
            }
        ],
    }
    current = {
        "scores": {
            "payload_score": 700.0,
            "latency_score": 800.0,
            "composite_score": 715.0,
        },
        "summary": {
            "stages": {
                "interactive": {
                    "total_bytes": 20_000,
                    "approx_tokens": 5_000,
                    "total_elapsed_ms": 650.0,
                }
            }
        },
        "calls": [
            {
                "label": "open_capture",
                "bytes": 650,
                "approx_tokens": 163,
                "elapsed_ms": 3_600.0,
            }
        ],
    }

    comparison = build_ref_comparison(current, baseline)

    assert comparison["baseline_git"]["commit"] == "old"
    assert comparison["score_delta"]["payload_delta"] == 600.0
    assert comparison["interactive_delta"]["bytes_delta"] == -80_000
    assert comparison["interactive_delta"]["bytes_pct"] == -80.0
    assert comparison["interactive_delta"]["elapsed_ms_delta"] == 150.0
    assert comparison["interactive_delta"]["elapsed_ms_pct"] == 30.0
    assert comparison["startup_delta"] is not None
    assert comparison["startup_delta"]["bytes_delta"] == 150
    assert comparison["startup_delta"]["elapsed_ms_delta"] == -400.0


def test_sanitize_call_args_redacts_local_paths() -> None:
    sanitized = sanitize_call_args(
        {
            "capture_path": r"C:\captures\sample.rdc",
            "capture_id": "abc123",
            "event_id": 42,
        }
    )

    assert sanitized["capture_path"] == "<redacted>"
    assert sanitized["capture_id"] == "abc123"
    assert sanitized["event_id"] == 42
