# Báo cáo Day 13 Observability

## 1. Thông tin nhóm

- **Tên nhóm:** `B4_E402`
- **Repository URL:** https://github.com/hoanganhquanCS04/Day13-2A202601875-HoangAnhQuan.git
- **Commit SHA cuối:** `cd84f4f91f5dd6a4b869c93d95eb7c85412409f3` *(cập nhật lại trước khi nộp)*
- **Thành viên và vai trò:**

| STT | Họ tên | MSSV | Vai trò | Phạm vi chính |
|-----|--------|------|---------|---------------|
| 1 | `Hoàng Anh Quân` | ` 2A202601875` | Setup & Integration Lead | Môi trường, Langfuse key, pytest, demo cuối |
| 2 | `Bùi Gia Huy` | ` 2A202601879` | Logging & PII | Correlation ID, metadata log, redaction |
| 3 | `Nguyễn Huy Đức` | ` 2A202601097` | Tracing & Prompt Versioning | Langfuse traces, prompt v1/v2, label/rollback |
| 4 | `Nguyễn Minh Hùng` | `2A202601183` | Dashboard, SLO & Alerts | 6 panel, threshold, alert rules, runbook |
| 5 | `Phạm Hải Đăng` | ` 2A202601367` | Incident, Report & Evidence | Challenge, điều tra root cause, gom evidence |

### Phân công theo checkpoint

| Checkpoint | Thời gian | Người phụ trách | Đầu ra |
|------------|-----------|-----------------|--------|
| 0 — Setup & baseline | 0:00–0:30 | Người 1 | API `/health` ok, load test chạy được, baseline `validate_logs.py` |
| 1 — Logging & PII | 0:30–1:30 | Người 2 | Correlation ID, metadata, PII redaction; `validate_logs.py` ≥ 80/100 |
| 2 — Traces & prompt | 1:30–2:30 | Người 3 | ≥ 10 traces, prompt v1/v2, evidence rollback |
| 2 — Dashboard & SLO | 1:30–2:30 | Người 4 | `validate_dashboard.py` 6/6 panel, ảnh dashboard, alert/runbook |
| 3 — Challenge | 2:30–3:30 | Người 5 | Metrics → Traces → Logs → root cause |
| 4 — Báo cáo & demo | 3:30–4:00 | Người 1 + 5 | Report hoàn chỉnh, demo, kiểm tra Git |

---

## 2. Kết quả kỹ thuật

- **Điểm `validate_logs.py`:** `100` / 100
  - Lệnh: `python scripts/validate_logs.py`
  - Evidence: [`submission/evidence/validate_logs_result.txt`](evidence/validate_logs_result.txt)

- **Tổng số traces:** `20` (10 production/version 3 + 10 candidate/version 4)
  - Evidence: [`submission/evidence/langfuse_trace_list.json`](evidence/langfuse_trace_list.json), [`submission/evidence/langfuse_trace_evidence.png`](evidence/langfuse_trace_evidence.png)

- **Số PII leak còn lại:** `0`
  - Evidence: [`submission/evidence/pii_redaction_log.jsonl`](evidence/pii_redaction_log.jsonl)

- **Link/đường dẫn dashboard:** `submission/evidence/dashboard.html`
  - Công cụ dùng: `scripts/generate_dashboard.py` (HTML không dependency, đọc `data/logs.jsonl`)
  - Evidence: [`submission/evidence/dashboard_6panels.png`](evidence/dashboard_6panels.png)

### Kiểm tra trước nộp

```bash
python -m pytest -q
python scripts/validate_logs.py
python scripts/validate_dashboard.py
git status --short
```

---

## 3. Logging và tracing

### 3.1. Correlation ID (Người 2)

**Triển khai:**

- `app/middleware.py`: clear contextvars mỗi request; lấy `x-request-id` từ header hoặc sinh `req-<8-char-hex>`; bind vào structlog; trả header `x-request-id` và `x-response-time-ms`.
- `app/main.py`: bind thêm `user_id_hash`, `session_id`, `feature`, `model`, `env` trước event `request_received`.

**Luồng:**

```text
Client → CorrelationIdMiddleware (tạo/bind ID) → /chat handler (enrich context) → agent.run() → response + headers
```

**Evidence correlation ID:**

- Log mẫu: [`submission/evidence/correlation_id_log.jsonl`](evidence/correlation_id_log.jsonl) *(hoặc screenshot)*
- Response header có `x-request-id`: [`submission/evidence/correlation_id_header.txt`](evidence/correlation_id_header.txt)
- Cùng một `correlation_id` xuất hiện ở `request_received` và `response_sent`: `req-45071b35`

### 3.2. PII redaction (Người 2)

**Triển khai:**

- `app/logging_config.py`: đăng ký processor `scrub_event` trước `JsonlFileProcessor`.
- `app/pii.py`: scrub email, phone VN, CCCD, credit card; pattern bổ sung nếu cần.

**Evidence PII redaction:**

- Input thử nghiệm chứa email/phone/card → log chỉ còn `[REDACTED_*]`: [`submission/evidence/pii_redaction_log.jsonl`](evidence/pii_redaction_log.jsonl)
- `validate_logs.py` báo `[PASSED] PII scrubbing`: [`submission/evidence/validate_logs_result.txt`](evidence/validate_logs_result.txt)

### 3.3. Tracing (Người 3)

**Evidence trace waterfall:**

- Trace waterfall đầy đủ: [`submission/evidence/langfuse_trace_waterfall.json`](evidence/langfuse_trace_waterfall.json) và ảnh [`submission/evidence/langfuse_trace_evidence.png`](evidence/langfuse_trace_evidence.png).
- Trace ID mẫu: `d1905f1bd24175818e1d4eeae74e16f9` (production/version 3 sau rollback).

**Giải thích một span đáng chú ý:**

Span **generation** (LLM) trong Langfuse ghi metadata `prompt_name`, `prompt_label`, `prompt_version`, `doc_count`, `query_preview` và usage/cost. Span này cho biết request dùng prompt version nào, retrieve bao nhiêu document, và chi phí token — hữu ích khi latency tăng nhưng LLM không phải nút thắt (ví dụ challenge `rag_slow`: thời gian chủ yếu nằm ở bước retrieval trước generation).

**Phân biệt Correlation ID vs Trace ID:**

| | Correlation ID | Trace ID |
|---|----------------|----------|
| Phạm vi | Một HTTP request xuyên suốt API + log | Một lần chạy agent trên Langfuse |
| Nơi thấy | Log JSON, response header | Langfuse UI |
| Mục đích | Nối log cùng request | Nối span, điều tra latency/error theo pipeline |

---

## 4. Prompt versioning

*(Người 3 — theo [docs/PROMPT_VERSIONING.md](../docs/PROMPT_VERSIONING.md))*

- **Prompt name:** `day13-chat`
- **Version/label baseline:** Version 3 — labels `baseline`, `production`
- **Version/label candidate:** Version 4 — label `candidate` *(một thay đổi nhỏ về format/độ dài câu trả lời)*
- **Biến prompt:** `Feature={{feature}}`, `Docs={{docs}}`, `Question={{message}}`

**Trace ID của mỗi version:**

| Label | Version | Trace ID | Evidence |
|-------|---------|----------|----------|
| `baseline` | 3 | `d89f8c82d9ba69d65ec5955f51af05a0` | [`submission/evidence/langfuse_trace_list.json`](evidence/langfuse_trace_list.json) |
| `candidate` | 4 | `7a3fa8c7ff2ff4bd487751a928f8bb46` | [`submission/evidence/langfuse_trace_list.json`](evidence/langfuse_trace_list.json) |

**Quy trình label/rollback đã thực hiện:**

1. Chạy cùng input với `LANGFUSE_PROMPT_LABEL=baseline` và `candidate`; xác minh metadata trace khác `prompt_version`.
2. Chuyển label `production` sang version 2; chạy lại một request.
3. Rollback `production` về version 1.

**Bằng chứng đổi label hoặc rollback:**

- Ảnh trước/sau promote/rollback: [`submission/evidence/prompt_label_promote.txt`](evidence/prompt_label_promote.txt), [`submission/evidence/prompt_label_rollback.txt`](evidence/prompt_label_rollback.txt), [`submission/evidence/prompt_promote_trace.json`](evidence/prompt_promote_trace.json), [`submission/evidence/prompt_rollback_final_trace.json`](evidence/prompt_rollback_final_trace.json)
- Danh sách versions/labels: [`submission/evidence/prompt_versions.json`](evidence/prompt_versions.json)

---

## 5. Dashboard, SLO và alerts

*(Người 4 — theo [docs/DASHBOARD_SETUP.md](../docs/DASHBOARD_SETUP.md), contract [config/dashboard.yaml](../config/dashboard.yaml))*

### 5.1. Dashboard

**Kết quả `validate_dashboard.py`:** `[HỢP LỆ: 6/6 panel]`
- Evidence: [`submission/evidence/validate_dashboard_result.txt`](evidence/validate_dashboard_result.txt)

**Evidence dashboard:**

- Ảnh 6 panel (latency, traffic, errors, cost, tokens, quality): [`submission/evidence/dashboard_6panels.png`](evidence/dashboard_6panels.png)
- Mỗi panel có: tên, đơn vị, time range 60 phút, threshold/SLO line.

**Nguồn dữ liệu:** `data/logs.jsonl` — events `request_received`, `response_sent`, `request_failed`.

| Panel | Event/field | Aggregation | Threshold |
|-------|-------------|-------------|-----------|
| Latency | `response_sent.latency_ms` | P50, P95, P99 | P95 ≤ 3000 ms |
| Traffic | `request_received` | count, req/phút | rate ≥ 1 |
| Errors | `request_failed` / `request_received` | error rate %, breakdown | ≤ 2% |
| Cost | `response_sent.cost_usd` | sum/phút, total | total ≤ 2.5 USD |
| Tokens | `tokens_in`, `tokens_out` | sum theo field | ≤ 50000 |
| Quality | `response_sent.quality_score` | mean | ≥ 0.75 |

**Kiểm tra runtime (practice):**

1. Baseline: `python scripts/load_test.py --concurrency 5`
2. Bật incident: `python scripts/inject_incident.py --scenario rag_slow`
3. Load test lại → P95 latency panel tăng rõ
4. Tắt: `python scripts/inject_incident.py --scenario rag_slow --disable`

### 5.2. SLO đã chọn và lý do

*(Căn cứ [config/slo.yaml](../config/slo.yaml) — cửa sổ 28 ngày)*

| SLI | Objective | Target | Lý do |
|-----|-----------|--------|-------|
| Latency P95 | ≤ 3000 ms | 99.5% | Chat AI chấp nhận được dưới 3s; khớp threshold dashboard |
| Error rate | ≤ 2% | 99.0% | Cho phép lỗi transient retrieval/LLM nhưng không vượt 2% |
| Daily cost | ≤ 2.5 USD | 100% | Kiểm soát chi phí mock billing theo token |
| Quality score avg | ≥ 0.75 | 95% | Proxy chất lượng câu trả lời (RAG + heuristic) |

### 5.3. Alert rules và runbook

*(Người 4 — [config/alert_rules.yaml](../config/alert_rules.yaml), [docs/alerts.md](../docs/alerts.md))*

#### Alert 1 — LatencyP95High

| Trường | Giá trị |
|--------|---------|
| Severity | `warning` |
| SLI/SLO | `latency_p95_ms` — objective 3000 ms |
| Condition | P95 latency > 3000 ms trong 5 phút liên tiếp |
| Ảnh hưởng | Phản hồi chậm, trải nghiệm chat kém |
| 3 bước kiểm tra đầu | (1) Mở panel Latency, xác nhận P95/P99; (2) Lọc trace chậm nhất trên Langfuse; (3) Tìm log `response_sent` cùng correlation ID, so sánh `latency_ms` |
| Mitigation tạm | Giảm concurrency load test; kiểm tra incident `rag_slow` có đang bật không |
| Owner | `observability-team` |

#### Alert 2 — ErrorRateHigh

| Trường | Giá trị |
|--------|---------|
| Severity | `critical` |
| SLI/SLO | `error_rate_pct` — objective 2% |
| Condition | Error rate > 2% trong 5 phút liên tiếp |
| Ảnh hưởng | Request fail, user không nhận được câu trả lời |
| 3 bước kiểm tra đầu | (1) Panel Errors — breakdown `error_type`; (2) Trace request failed; (3) Log `request_failed` + correlation ID |
| Mitigation tạm | Kiểm tra incident `tool_fail`; restart API nếu vector store timeout |
| Owner | `observability-team` |

#### Alert 3 — DailyCostHigh

| Trường | Giá trị |
|--------|---------|
| Severity | `warning` |
| SLI/SLO | `daily_cost_usd` — objective 2.5 USD |
| Condition | Tổng cost trong 24h > 2.5 USD |
| Ảnh hưởng | Chi phí inference vượt ngân sách |
| 3 bước kiểm tra đầu | (1) Panel Cost — sum theo phút; (2) So sánh `tokens_in`/`tokens_out`; (3) Kiểm tra incident `cost_spike` hoặc traffic bất thường |
| Mitigation tạm | Giảm traffic; review prompt dài hoặc model đắt |
| Owner | `observability-team` |

Runbook chi tiết: [docs/alerts.md](../docs/alerts.md)

---

## 6. Điều tra challenge

*(Người 5 — challenge đã release: [config/challenge.json](../config/challenge.json))*

- **Challenge ID:** `day13-k3-observability-v1`
- **Cohort:** K3
- **Incident:** `rag_slow`
- **Feature bị ảnh hưởng:** `refund`
- **Ngưỡng latency:** 2000 ms

### Lệnh chạy

```bash
python scripts/inject_incident.py
python scripts/load_test.py --challenge --concurrency 5
```

### Triệu chứng từ metrics

Sau khi bật incident và chạy load test challenge:

- **`/metrics`:** `latency_p95` và `latency_p99` tăng mạnh (từ baseline ~vài trăm ms lên > 2500 ms).
- **Dashboard panel Latency:** P95 vượt threshold 3000 ms (hoặc ít nhất vượt `latency_threshold_ms` 2000 ms của challenge).
- **Traffic / Error rate:** traffic ổn định; error rate không tăng đáng kể *(incident `rag_slow` chỉ delay, không fail request)*.
- **Cost / Tokens:** không đổi đáng kể so với baseline.

Evidence: [`submission/evidence/challenge_metrics_before.json`](evidence/challenge_metrics_before.json), [`submission/evidence/challenge_metrics_after.json`](evidence/challenge_metrics_after.json)

### Trace ID liên quan

- Trace chậm nhất trong cửa sổ incident: `59a6bc64719c710668c4b876a4bfe2a5` (session `k3-challenge-s04`).
- Evidence waterfall: [`submission/evidence/langfuse_challenge_trace_waterfall.json`](evidence/langfuse_challenge_trace_waterfall.json) và danh sách 5 challenge traces [`submission/evidence/langfuse_challenge_traces.json`](evidence/langfuse_challenge_traces.json).
- Quan sát: trace production/version 3 ghi nhận retrieval/RAG chiếm phần lớn latency trước generation.

### Log line / correlation ID liên quan

- Correlation ID request chậm: `req-aa84c97d`
- Log `response_sent` tương ứng: `latency_ms` ≈ 2500+ (do sleep 2.5s trong retrieval)
- `feature`: `refund`, `session_id`: `k3-challenge-s0*`

Evidence: [`submission/evidence/challenge_log_line.jsonl`](evidence/challenge_log_line.jsonl)

### Root cause

Khi incident `rag_slow` được bật (`POST /incidents/rag_slow/enable`), hàm `retrieve()` trong `app/mock_rag.py` gọi `time.sleep(2.5)` trước khi trả document. Các query challenge đều dùng `feature: "refund"` và message chứa từ khóa *refund* → đi qua RAG path → mỗi request bị cộng ~2500 ms latency ở bước retrieval, trong khi LLM generation gần như không đổi.

**Chuỗi bằng chứng:**

```text
Metrics (P95 ↑) → Trace (`59a6bc64719c710668c4b876a4bfe2a5`, retrieval chậm) → Log (latency_ms ~2500+, feature=refund, cùng correlation_id).
```

### Fix action

1. **Mitigation ngay:** `python scripts/inject_incident.py --scenario rag_slow --disable` hoặc `POST /incidents/rag_slow/disable`.
2. **Fix kỹ thuật (đề xuất):** thêm timeout/deadline cho bước retrieval; circuit breaker khi RAG vượt ngưỡng; log span `retrieve` riêng với `latency_ms` để localize nhanh hơn generation span.

### Preventive measure

- Alert **LatencyP95High** (mục 5.3) với runbook kiểm tra incident flags và span retrieval trước.
- Dashboard theo dõi latency tách theo `feature` để phát hiện `refund` (hoặc feature khác) bị ảnh hưởng lệch.
- Load test định kỳ với practice incident trước khi release; SLO review khi thêm sleep/dependency mới vào RAG path.
- Không log PII trong message refund; giữ `summarize_text` cho preview.

Evidence tổng hợp challenge: [`submission/evidence/challenge_investigation_summary.md`](evidence/challenge_investigation_summary.md)

---

## 7. Đóng góp cá nhân

Với mỗi thành viên, ghi rõ nhiệm vụ và link commit/PR tương ứng *(cập nhật SHA/PR trước khi nộp)*.

| Thành viên | Phần việc | Commit/PR | Điều đã học |
|------------|-----------|-----------|-------------|
| `[TÊN 1]` — Setup & Integration Lead | Virtualenv, `.env` Langfuse, chạy API + load test baseline; `pytest -q` cuối buổi; demo Metrics → Traces → Logs → Root cause | `[commit/PR]` | Cách bootstrapping môi trường observability và kiểm tra end-to-end trước nộp |
| `[TÊN 2]` — Logging & PII | `app/middleware.py`, `app/main.py`, `app/logging_config.py`, `app/pii.py`; đạt `validate_logs.py` ≥ 80/100; evidence correlation ID & PII | `[commit/PR]` | Correlation ID phải clear/bind contextvars; PII scrub trước khi JSON render xuống file |
| `[TÊN 3]` — Tracing & Prompt Versioning | Prompt `day13-chat` v1/v2 trên Langfuse; ≥ 10 traces; label promote + rollback; metadata `prompt_name/label/version` | `https://github.com/hoanganhquanCS04/Day13-2A202601875-HoangAnhQuan/pull/1` | Prompt versioning phục vụ truy xuất và rollback, không phải tối ưu chất lượng câu trả lời |
| `Nguyễn Minh Hùng` — Dashboard, SLO & Alerts | Dashboard 6 panel từ `logs.jsonl`; `config/slo.yaml`; `config/alert_rules.yaml` + `docs/alerts.md`; practice `rag_slow` trên dashboard | `f1a02e5` | Dashboard contract tách khỏi Langfuse; alert nên symptom-based gắn SLO, có runbook 3 bước |
| `[TÊN 5]` — Incident, Report & Evidence | Challenge `day13-k3-observability-v1`; điều tra root cause; hoàn thiện report & `submission/evidence/` | `[commit/PR]` | Chỉ kết luận root cause khi metric, trace và log cùng correlation ID khớp nhau |

---

## Phụ lục — Danh sách evidence (`submission/evidence/`)

Theo [SUBMISSION.md](../SUBMISSION.md) và [docs/grading-evidence.md](../docs/grading-evidence.md):

| File | Mô tả | Người thu |
|------|-------|-----------|
| `validate_logs_result.txt` | Output `validate_logs.py` | Người 2 |
| `validate_dashboard_result.txt` | Output `validate_dashboard.py` | Người 4 |
| `correlation_id_log.jsonl`, `correlation_id_header.txt` | Log/header correlation ID | Người 2 |
| `pii_redaction_log.jsonl` | PII đã redact | Người 2 |
| `langfuse_trace_evidence.png`, `langfuse_trace_waterfall.json` | 20 traces + waterfall | Người 3 |
| `langfuse_trace_list.json` | 10 production + 10 candidate traces | Người 3 |
| `prompt_versions.json`, `prompt_label_promote.txt`, `prompt_label_rollback.txt` | Version/label/rollback | Người 3 |
| `dashboard_6panels.png` | Dashboard runtime | Người 4 |
| `challenge_metrics_before.json`, `challenge_metrics_after.json` | Metric trước/sau incident | Người 5 |
| `langfuse_challenge_traces.json`, `langfuse_challenge_trace_waterfall.json` | Trace challenge | Người 5 |
| `challenge_log_line.jsonl` | Log line + correlation ID | Người 5 |
| `challenge_investigation_summary.md` | Tóm tắt điều tra | Người 5 |

---

## Phụ lục — Demo script (3–5 phút, Người 1)

1. **Health:** `GET /health` — tracing enabled, incidents status.
2. **Metrics baseline:** `GET /metrics` — P95, traffic, quality.
3. **Trace:** Mở Langfuse — trace mẫu, chỉ metadata prompt version *(Người 3)*.
4. **Log:** Một dòng `data/logs.jsonl` — correlation ID, không PII *(Người 2)*.
5. **Dashboard:** 6 panel + threshold *(Người 4)*.
6. **Incident:** Bật `rag_slow` → load test → metric/trace/log → root cause → disable *(Người 5)*.
