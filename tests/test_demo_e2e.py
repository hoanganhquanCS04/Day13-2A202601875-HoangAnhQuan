from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import demo_e2e  # noqa: E402


def response(correlation_id: str, latency_ms: float) -> dict:
    return {
        "event": "response_sent",
        "correlation_id": correlation_id,
        "feature": "refund",
        "latency_ms": latency_ms,
    }


def test_slowest_response_picks_highest_latency() -> None:
    records = [response("req-a", 120), response("req-b", 2651), response("req-c", 780)]

    assert demo_e2e.slowest_response(records)["correlation_id"] == "req-b"


def test_slowest_response_ignores_non_response_events() -> None:
    records = [
        {"event": "request_received", "correlation_id": "req-a", "latency_ms": 9999},
        response("req-b", 150),
    ]

    assert demo_e2e.slowest_response(records)["correlation_id"] == "req-b"


def test_slowest_response_returns_none_without_responses() -> None:
    assert demo_e2e.slowest_response([{"event": "app_started"}]) is None


def test_percentile_delta_formats_before_and_after() -> None:
    delta = demo_e2e.percentile_delta({"latency_p95": 1034.0}, {"latency_p95": 2651.0}, "latency_p95")

    assert delta == "1034 ms -> 2651 ms"


def test_read_log_records_skips_lines_before_cursor(tmp_path: Path, monkeypatch) -> None:
    log_file = tmp_path / "logs.jsonl"
    log_file.write_text(
        '{"event":"app_started"}\n\n{"event":"response_sent","latency_ms":150}\nkhông-phải-json\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(demo_e2e, "LOG_PATH", log_file)

    assert demo_e2e.count_log_lines() == 3
    assert demo_e2e.read_log_records(since_line=1) == [{"event": "response_sent", "latency_ms": 150}]


def test_write_evidence_is_skipped_when_disabled(tmp_path: Path) -> None:
    demo_e2e.write_evidence("demo_test.json", "{}", None)

    assert not (tmp_path / "demo_test.json").exists()
