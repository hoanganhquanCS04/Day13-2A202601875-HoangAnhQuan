"""Demo end-to-end Metrics → Traces → Logs → Root cause — Người 1 (Setup & Integration Lead).

Chạy trọn kịch bản demo cuối buổi bằng một lệnh và ghi evidence theo từng bước:

    python scripts/demo_e2e.py                 # dùng incident trong config/challenge.json
    python scripts/demo_e2e.py --scenario rag_slow --no-evidence

Script luôn tắt incident ở bước cuối, kể cả khi có lỗi giữa chừng.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.challenge import load_challenge
from app.cli import configure_utf8_stdio

BASE_URL = "http://127.0.0.1:8000"
EVIDENCE_DIR = REPO_ROOT / "submission" / "evidence"
LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"


class DemoError(RuntimeError):
    pass


def banner(step: int, title: str) -> None:
    print(f"\n=== Bước {step}: {title} ===")


def write_evidence(name: str, content: str, evidence_dir: Path | None) -> None:
    if evidence_dir is None:
        return
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / name).write_text(content, encoding="utf-8")
    print(f"    -> evidence: submission/evidence/{name}")


def dump_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def get_json(client: httpx.Client, path: str) -> dict:
    response = client.get(path)
    response.raise_for_status()
    return response.json()


def post_json(client: httpx.Client, path: str) -> dict:
    response = client.post(path)
    response.raise_for_status()
    return response.json()


def run_load_test(challenge: bool, concurrency: int) -> str:
    """Gọi lại scripts/load_test.py để demo dùng đúng công cụ nhóm đã nộp."""
    command = [sys.executable, str(REPO_ROOT / "scripts" / "load_test.py"), "--concurrency", str(concurrency)]
    if challenge:
        command.append("--challenge")
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    output = (result.stdout or "") + (result.stderr or "")
    print(output.rstrip())
    if result.returncode != 0:
        raise DemoError(f"load_test.py thoát với mã {result.returncode}")
    return output


def read_log_records(since_line: int = 0) -> list[dict]:
    if not LOG_PATH.exists():
        return []
    lines = [line for line in LOG_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    records = []
    for line in lines[since_line:]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def count_log_lines() -> int:
    if not LOG_PATH.exists():
        return 0
    return len([line for line in LOG_PATH.read_text(encoding="utf-8").splitlines() if line.strip()])


def slowest_response(records: list[dict]) -> dict | None:
    responses = [rec for rec in records if rec.get("event") == "response_sent" and rec.get("latency_ms")]
    if not responses:
        return None
    return max(responses, key=lambda rec: rec["latency_ms"])


def percentile_delta(before: dict, after: dict, key: str) -> str:
    start, end = before.get(key, 0), after.get(key, 0)
    return f"{start:.0f} ms -> {end:.0f} ms"


def run_demo(client: httpx.Client, scenario: str, threshold_ms: int, concurrency: int, evidence_dir: Path | None) -> int:
    banner(1, "Health — API và tracing đã sẵn sàng")
    health = get_json(client, "/health")
    print(dump_json(health))
    if not health.get("ok"):
        raise DemoError("/health không trả về ok=True")
    write_evidence("demo_01_health.json", dump_json(health), evidence_dir)

    banner(2, "Metrics baseline — trạng thái bình thường")
    baseline_load = run_load_test(challenge=False, concurrency=concurrency)
    write_evidence("demo_02_load_baseline.txt", baseline_load, evidence_dir)
    metrics_before = get_json(client, "/metrics")
    print(dump_json(metrics_before))
    write_evidence("demo_03_metrics_baseline.json", dump_json(metrics_before), evidence_dir)

    banner(3, f"Bật incident `{scenario}` — mô phỏng sự cố production")
    enabled = post_json(client, f"/incidents/{scenario}/enable")
    print(dump_json(enabled))
    write_evidence("demo_04_incident_enable.json", dump_json(enabled), evidence_dir)

    log_cursor = count_log_lines()
    banner(4, "Metrics — triệu chứng: latency P95 vượt ngưỡng")
    incident_load = run_load_test(challenge=True, concurrency=concurrency)
    write_evidence("demo_05_load_challenge.txt", incident_load, evidence_dir)
    metrics_after = get_json(client, "/metrics")
    print(dump_json(metrics_after))
    write_evidence("demo_06_metrics_incident.json", dump_json(metrics_after), evidence_dir)

    print(f"\n    P50: {percentile_delta(metrics_before, metrics_after, 'latency_p50')}")
    print(f"    P95: {percentile_delta(metrics_before, metrics_after, 'latency_p95')} (ngưỡng {threshold_ms} ms)")
    print(f"    P99: {percentile_delta(metrics_before, metrics_after, 'latency_p99')}")
    breached = metrics_after.get("latency_p95", 0) > threshold_ms

    banner(5, "Logs — khoanh vùng request chậm nhất theo correlation ID")
    incident_records = read_log_records(since_line=log_cursor)
    slowest = slowest_response(incident_records)
    if slowest is None:
        raise DemoError("Không tìm thấy event response_sent nào sau khi bật incident")
    print(
        f"    correlation_id = {slowest.get('correlation_id')} | "
        f"feature = {slowest.get('feature')} | latency_ms = {slowest.get('latency_ms')}"
    )
    print(f"    session_id = {slowest.get('session_id')} | model = {slowest.get('model')}")
    write_evidence(
        "demo_07_log_slowest.json",
        dump_json(
            {
                "correlation_id": slowest.get("correlation_id"),
                "feature": slowest.get("feature"),
                "session_id": slowest.get("session_id"),
                "latency_ms": slowest.get("latency_ms"),
                "record": slowest,
            }
        ),
        evidence_dir,
    )

    banner(6, "Root cause và mitigation — tắt incident, xác nhận phục hồi")
    disabled = post_json(client, f"/incidents/{scenario}/disable")
    print(dump_json(disabled))
    write_evidence("demo_08_incident_disable.json", dump_json(disabled), evidence_dir)

    recovery_cursor = count_log_lines()
    recovery_load = run_load_test(challenge=True, concurrency=concurrency)
    write_evidence("demo_09_load_recovered.txt", recovery_load, evidence_dir)
    recovered_slowest = slowest_response(read_log_records(since_line=recovery_cursor))
    recovered_latency = recovered_slowest.get("latency_ms") if recovered_slowest else None
    print(f"\n    Latency chậm nhất sau khi tắt incident: {recovered_latency} ms")

    summary = {
        "scenario": scenario,
        "latency_threshold_ms": threshold_ms,
        "metrics_baseline": metrics_before,
        "metrics_incident": metrics_after,
        "p95_breached_threshold": breached,
        "slowest_correlation_id": slowest.get("correlation_id"),
        "slowest_latency_ms": slowest.get("latency_ms"),
        "slowest_feature": slowest.get("feature"),
        "slowest_latency_ms_after_disable": recovered_latency,
    }
    write_evidence("demo_10_summary.json", dump_json(summary), evidence_dir)

    print("\n--- Kết luận demo ---")
    print(f"Metrics: P95 {percentile_delta(metrics_before, metrics_after, 'latency_p95')}")
    print(f"Traces:  span retrieval của feature `{slowest.get('feature')}` chiếm phần lớn latency (xem Langfuse)")
    print(f"Logs:    correlation_id {slowest.get('correlation_id')} có latency_ms = {slowest.get('latency_ms')}")
    print(f"Root cause: incident `{scenario}` làm chậm bước retrieval trước generation")
    print(f"Mitigation: tắt incident -> latency chậm nhất còn {recovered_latency} ms")

    if not breached:
        print(f"\nCẢNH BÁO: P95 không vượt ngưỡng {threshold_ms} ms — kiểm tra incident đã bật đúng chưa.")
        return 1
    return 0


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Demo end-to-end Day 13: Metrics → Traces → Logs → Root cause")
    parser.add_argument("--base-url", default=BASE_URL, help="Base URL của API đang chạy")
    parser.add_argument(
        "--scenario",
        choices=["rag_slow", "tool_fail", "cost_spike"],
        help="Chỉ dùng cho practice. Bỏ tham số này để đọc config/challenge.json.",
    )
    parser.add_argument("--concurrency", type=int, default=5, help="Số request song song mỗi lần load test")
    parser.add_argument("--no-evidence", action="store_true", help="Chỉ demo trên màn hình, không ghi file evidence")
    args = parser.parse_args()

    challenge = load_challenge()
    scenario = args.scenario or challenge.incident
    evidence_dir = None if args.no_evidence else EVIDENCE_DIR

    print(f"Challenge: {challenge.challenge_id} | Cohort: {challenge.cohort}")
    print(f"Incident demo: {scenario} | feature: {challenge.affected_feature} | ngưỡng: {challenge.latency_threshold_ms} ms")

    started = time.perf_counter()
    with httpx.Client(base_url=args.base_url, timeout=60.0) as client:
        try:
            exit_code = run_demo(client, scenario, challenge.latency_threshold_ms, args.concurrency, evidence_dir)
        except (httpx.HTTPError, DemoError) as exc:
            print(f"\nDEMO LỖI: {exc}")
            exit_code = 1
        finally:
            # Không để incident sót lại sau demo, kể cả khi có lỗi giữa chừng.
            try:
                client.post(f"/incidents/{scenario}/disable")
            except httpx.HTTPError:
                print(f"Không tắt được incident `{scenario}` — kiểm tra thủ công POST /incidents/{scenario}/disable")

    print(f"\nTổng thời gian demo: {time.perf_counter() - started:.1f}s")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
