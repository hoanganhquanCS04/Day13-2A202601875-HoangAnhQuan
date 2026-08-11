"""Render captured Langfuse API evidence as a reviewable local HTML page."""

from __future__ import annotations

import html
import json
from pathlib import Path


def read_json(path: Path):
    raw = path.read_bytes()
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    return json.loads(raw.decode(encoding))


def main() -> int:
    evidence = Path("submission/evidence")
    waterfall = read_json(evidence / "langfuse_trace_waterfall.json")
    traces = read_json(evidence / "langfuse_trace_list.json")
    rows = "".join(
        f"<tr><td>{html.escape(item['id'])}</td><td>{html.escape(item['metadata']['prompt_label'])}</td>"
        f"<td>{html.escape(str(item['metadata']['prompt_version']))}</td><td>{html.escape(item['session_id'])}</td></tr>"
        for item in traces
    )
    metadata = waterfall["trace_metadata"]
    generation = waterfall["metadata"]
    page = f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Langfuse evidence</title>
<style>body{{font:15px system-ui;background:#f4f6f8;color:#17202a;padding:24px}}main{{max-width:1100px;margin:auto}}
section{{background:#fff;border:1px solid #d8dee4;border-radius:6px;padding:18px;margin:16px 0}}h1{{margin-top:0}}
table{{width:100%;border-collapse:collapse}}td,th{{border-bottom:1px solid #d8dee4;padding:8px;text-align:left;font-family:ui-monospace,monospace;font-size:12px}}
.span{{border-left:6px solid #2471a3;padding:12px;background:#eef6fb}}dt{{font-weight:700;margin-top:8px}}dd{{margin-left:0}}</style></head><body><main>
<h1>Langfuse trace and prompt evidence</h1><section><h2>Trace list ({len(traces)} captured)</h2><table><tr><th>Trace ID</th><th>Label</th><th>Version</th><th>Session</th></tr>{rows}</table></section>
<section><h2>Waterfall detail</h2><div class='span'><strong>{html.escape(waterfall['type'])}: {html.escape(waterfall['name'])}</strong><br>Latency: {html.escape(str(waterfall['latency']))} s | Observation: {html.escape(waterfall['observation_id'])}</div>
<dl><dt>Trace ID</dt><dd>{html.escape(waterfall['trace_id'])}</dd><dt>Prompt metadata</dt><dd>{html.escape(json.dumps(metadata,ensure_ascii=False))}</dd><dt>Generation metadata</dt><dd>{html.escape(json.dumps(generation,ensure_ascii=False))}</dd><dt>Usage/cost</dt><dd>{html.escape(json.dumps({'usage':waterfall['usage'],'cost':waterfall['cost']},ensure_ascii=False))}</dd></dl></section></main></body></html>"""
    output = evidence / "langfuse_trace_evidence.html"
    output.write_text(page, encoding="utf-8")
    print(f"Rendered {len(traces)} traces to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
