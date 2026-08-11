"""Generate a dependency-free runtime dashboard from the canonical JSONL logs."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from statistics import mean


def percentile(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(p / 100 * len(ordered) + 0.5) - 1))
    return ordered[index]


def load_records(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Log source not found: {path}")
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def make_dashboard(records: list[dict]) -> str:
    responses = [r for r in records if r.get("event") == "response_sent"]
    received = [r for r in records if r.get("event") == "request_received"]
    failed = [r for r in records if r.get("event") == "request_failed"]
    latencies = [float(r["latency_ms"]) for r in responses if r.get("latency_ms") is not None]
    costs = [float(r["cost_usd"]) for r in responses if r.get("cost_usd") is not None]
    tokens_in = sum(int(r.get("tokens_in", 0)) for r in responses)
    tokens_out = sum(int(r.get("tokens_out", 0)) for r in responses)
    quality = [float(r["quality_score"]) for r in responses if r.get("quality_score") is not None]
    error_rate = (len(failed) / len(received) * 100) if received else 0.0
    panels = [
        ("Latency percentiles", f"P50 {percentile(latencies, 50):.0f} ms | P95 {percentile(latencies, 95):.0f} ms | P99 {percentile(latencies, 99):.0f} ms", "P95 <= 3000 ms"),
        ("Request traffic", f"{len(received)} requests | {len(received) / 60:.2f} requests/min", "Rate >= 1/min"),
        ("Error rate and breakdown", f"{error_rate:.2f}% ({len(failed)}/{len(received) or 1})", "Error rate <= 2%"),
        ("Cost over time", f"${sum(costs):.6f} total | ${mean(costs) if costs else 0:.6f} average", "Total <= $2.50"),
        ("Input and output tokens", f"{tokens_in:,} in | {tokens_out:,} out", "Total <= 50,000"),
        ("Quality proxy", f"{mean(quality) if quality else 0:.2f} mean score", "Mean >= 0.75"),
    ]
    cards = "\n".join(
        f'<section class="panel"><h2>{html.escape(title)}</h2><p class="value">{html.escape(value)}</p><p class="threshold">Threshold: {html.escape(threshold)}</p></section>'
        for title, value, threshold in panels
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="30">
<title>Day 13 AI Observability</title><style>
body{{font-family:system-ui,sans-serif;background:#f4f6f8;color:#17202a;margin:0;padding:24px}}
header{{display:flex;justify-content:space-between;align-items:end;border-bottom:2px solid #d8dee4;margin-bottom:20px}}
h1{{font-size:24px;margin:0 0 8px}} .meta{{color:#52606d;font-size:13px}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(280px,1fr));gap:16px;max-width:1100px}}
.panel{{background:white;border:1px solid #d8dee4;border-radius:6px;padding:18px;min-height:110px;box-shadow:0 1px 2px #00000012}}
.panel h2{{font-size:16px;margin:0 0 22px}} .value{{font-size:20px;font-weight:650;margin:0 0 14px}}
.threshold{{font-size:13px;color:#52606d;margin:0}} @media(max-width:700px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><header><div><h1>Day 13 AI Observability</h1><div class="meta">Source: data/logs.jsonl | Time range: 60 minutes | Refresh: 30 seconds</div></div><div class="meta">Records: {len(records)}</div></header><main class="grid">{cards}</main></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the six-panel Day 13 dashboard")
    parser.add_argument("--logs", type=Path, default=Path("data/logs.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("submission/evidence/dashboard.html"))
    args = parser.parse_args()
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(make_dashboard(load_records(args.logs)), encoding="utf-8")
    print(f"Dashboard written to {output} (6 panels)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
