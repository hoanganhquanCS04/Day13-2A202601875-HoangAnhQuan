# Hướng dẫn hoàn thành Day 13 Observability (từ A đến Z)

Tài liệu này là checklist thực hành duy nhất. Làm đúng thứ tự, lưu evidence ngay sau mỗi bước và chỉ kết luận incident khi nối được **Metrics → Traces → Logs**. Mục tiêu là đáp ứng toàn bộ rubric 100 điểm; bonus chỉ là phần cộng thêm.

## 0. Phạm vi, điểm và luật bắt buộc

Rubric gồm: logging/PII 10 điểm, traces + prompt version 10, dashboard/SLO/alert 10, điều tra incident 10, demo nhóm 20, báo cáo hiểu bài 20 và commit/evidence cá nhân 20. Không được sửa hoặc tự tạo `config/challenge.json`, không hard-code để qua validator, không làm giả trace/screenshot/log, không commit `.env`, secret, PII hay `.venv`.

Các nguồn chuẩn cần luôn đối chiếu: [README](../README.md), [RUBRIC](../RUBRIC.md), [RULES](../RULES.md), [SETUP](../SETUP.md), [CHECKPOINTS](../CHECKPOINTS.md), [SUBMISSION](../SUBMISSION.md), [prompt versioning](PROMPT_VERSIONING.md), [dashboard setup](DASHBOARD_SETUP.md), [grading evidence](grading-evidence.md).

## 1. Khởi tạo môi trường (Checkpoint 0, 0:00–0:30)

Mở PowerShell tại thư mục repo:

```powershell
python --version                 # phải >= 3.11
git status --short
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Nếu PowerShell chặn activate, chạy một lần `Set-ExecutionPolicy -Scope Process Bypass`, rồi activate lại. Luôn kiểm tra đầu dòng terminal có `(.venv)`.

Mở `.env` và điền key Langfuse project chung/cloud do Lab Coach cấp (không ghi key vào Markdown, report hoặc ảnh):

```dotenv
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PROMPT_NAME=day13-chat
LANGFUSE_PROMPT_LABEL=production
```

Docker Langfuse local là tùy chọn, không cộng điểm riêng. Nếu dùng, clone ra ngoài repo, `docker compose up -d`, tạo project tại `http://localhost:3000`, đặt `LANGFUSE_HOST=http://localhost:3000`; khi xong dùng `docker compose down` (không dùng `down -v` nếu còn cần dữ liệu).

Terminal 1 chạy API:

```powershell
uvicorn app.main:app --reload --env-file .env
```

Terminal 2 kiểm tra health và baseline:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/metrics
python scripts/load_test.py --concurrency 5
python scripts/validate_logs.py
python scripts/validate_dashboard.py
python -m pytest -q
```

`/health` phải có `ok: true`; `data/logs.jsonl` chỉ xuất hiện sau request. Lưu output baseline vào `submission/evidence/validate_logs_baseline.txt` nếu muốn so sánh, nhưng evidence cuối phải là output sau khi sửa.

## 2. Hoàn thiện logging, correlation ID và PII (Checkpoint 1, 0:30–1:30)

### 2.1. Sửa `app/middleware.py`

Trong `dispatch`:

1. Gọi `clear_contextvars()` đầu request để không rò context sang request kế tiếp.
2. Lấy `request.headers.get("x-request-id")`; nếu rỗng, sinh `f"req-{uuid.uuid4().hex[:8]}"`. Nếu muốn an toàn, chỉ chấp nhận ID ngắn hợp lệ rồi sinh mới khi header bẩn.
3. Gọi `bind_contextvars(correlation_id=correlation_id)` và gán `request.state.correlation_id`.
4. Đo `time.perf_counter()` quanh `call_next(request)`.
5. Trước khi trả response, đặt `x-request-id` và `x-response-time-ms` (số mili-giây, làm tròn hợp lý).
6. Dùng `try/finally` để `clear_contextvars()` sau response, kể cả khi handler lỗi.

Ví dụ luồng đúng: `client → middleware tạo ID → handler/agent → JSON log + response header cùng ID`.

### 2.2. Sửa `app/main.py`

Thay TODO ở đầu `/chat`, trước `request_received`:

```python
bind_contextvars(
    user_id_hash=hash_user_id(body.user_id),
    session_id=body.session_id,
    feature=body.feature,
    model=agent.model,
    env=os.getenv("APP_ENV", "dev"),
)
```

Không bind `user_id` nguyên bản. `structlog.contextvars.merge_contextvars` sẽ đưa các trường này vào mọi log API của request (cùng `correlation_id`). Giữ `summarize_text` cho preview, không log toàn bộ message/answer.

`config/logging_schema.json` yêu cầu mọi record có `correlation_id`. Event `app_started` chạy ngoài HTTP request nên truyền rõ `correlation_id="system"` (hoặc bind một system context) khi log startup; các event control đi qua middleware và dùng request ID bình thường.

### 2.3. Sửa PII processor

Trong `app/logging_config.py`, đăng ký `scrub_event` **trước** `JsonlFileProcessor()` và `JSONRenderer()`. Processor phải scrub tất cả chuỗi trong `payload`; `app/pii.py` đã có email, số điện thoại VN, CCCD 12 số và thẻ 16 số. Có thể bổ sung pattern nếu có dữ liệu mới, nhưng không được làm lộ dữ liệu thật.

Thứ tự tối thiểu:

```python
merge_contextvars,
add_log_level,
TimeStamper(...),
scrub_event,
JsonlFileProcessor(),
JSONRenderer(),
```

`JsonlFileProcessor` ghi từng JSON line vào `data/logs.jsonl`; vì vậy scrub phải xảy ra trước lúc render/ghi. Chạy lại load test sau mỗi thay đổi. Gửi một request thử có email, phone và card; log chỉ được chứa `[REDACTED_EMAIL]`, `[REDACTED_PHONE_VN]`, `[REDACTED_CREDIT_CARD]`.

Request kiểm thử PowerShell (chạy khi API đang hoạt động):

```powershell
$body = @{user_id="pii-test"; session_id="pii-session"; feature="qa"; message="Email a@b.com phone 0901234567 card 4111 1111 1111 1111"} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/chat -ContentType "application/json" -Body $body
Get-Content data/logs.jsonl -Tail 5
```

Chỉ dùng dữ liệu giả trong ví dụ và che mọi key khi chụp ảnh.

### 2.4. Chốt checkpoint logging

```powershell
python scripts/load_test.py --concurrency 5
python scripts/validate_logs.py
```

Mục tiêu cuối: `Estimated Score: 100/100` (tối thiểu rubric yêu cầu 80), missing required/enrichment = 0, PII leaks = 0, ít nhất 2 correlation ID. Kiểm tra một request có cùng ID ở `request_received`, `response_sent` và header `x-request-id`.

Lưu:

- `submission/evidence/validate_logs_result.txt`: copy nguyên output cuối.
- `submission/evidence/correlation_id_log.jsonl`: vài dòng log đã lọc, không PII.
- `submission/evidence/correlation_id_header.png`: header và body response.
- `submission/evidence/pii_redaction_log.png`: input thử và log đã redact.

## 3. Traces và prompt versioning (Checkpoint 2, 1:30–2:30)

### 3.1. Kiểm tra tracing

Hai key Langfuse phải cùng tồn tại thì `tracing_enabled()` mới là `true`. Sau khi đổi `.env`, restart uvicorn. Trong Langfuse, tạo text prompt tên **`day13-chat`**, giữ đúng ba biến:

```text
Feature={{feature}}
Docs={{docs}}
Question={{message}}
```

App dùng `LANGFUSE_PROMPT_NAME` và `LANGFUSE_PROMPT_LABEL`; khi fetch lỗi, app báo rõ `prompt_source=local-fallback`, không được giả vờ là managed prompt. Trace generation cần có `prompt_name`, `prompt_label`, `prompt_version`, `prompt_source`, `doc_count`, `query_preview`, usage token và cost.

### 3.2. Tạo v1/v2 và rollback

Trong Langfuse UI:

1. Tạo version 1, gắn labels `baseline` và `production`.
2. Tạo version 2 với một thay đổi nhỏ về format/độ dài, gắn label `candidate`.
3. Giữ cùng một input, đổi `.env` lần lượt `LANGFUSE_PROMPT_LABEL=baseline` rồi `candidate`; mỗi lần restart API và gửi request.
4. Mở hai trace, ghi trace ID và xác nhận đủ name/label/version trong metadata.
5. Chuyển label `production` sang version 2, gửi một request; sau đó rollback `production` về version 1.
6. Chụp màn hình danh sách versions, hai trace và lịch sử đổi label/rollback.

Không chấm prompt nào hay hơn; điểm là khả năng truy xuất version, promote và rollback. Cần tối thiểu 10 traces: chạy `python scripts/load_test.py --concurrency 5` (10 query trong `data/sample_queries.jsonl`) khi Langfuse đã bật; có thể chạy lặp để đủ số lượng.

Lưu `trace_list.png`, `trace_waterfall.png`, `trace_baseline.png`, `trace_candidate.png`, `prompt_versions.png`, `prompt_label_rollback.png`. Ghi ID tương ứng vào mục 4 của `submission/REPORT.md`.

## 4. Dashboard, SLO, alert và runbook (Checkpoint 2)

### 4.1. Không đổi dashboard contract

Nguồn dữ liệu chuẩn là `data/logs.jsonl`, không phải chỉ Langfuse. Chạy trước:

```powershell
python scripts/validate_dashboard.py
```

Kết quả bắt buộc: `HỢP LỆ: 6/6 panel`. Không đổi `config/dashboard.yaml` chỉ để validator qua. Dashboard runtime có thể làm bằng Streamlit, Grafana, notebook hoặc công cụ tương đương; phải đọc JSONL và thể hiện:

| Panel | Dữ liệu/tính toán | Đơn vị và ngưỡng |
|---|---|---|
| Latency | `response_sent.latency_ms`, P50/P95/P99 | ms, P95 ≤ 3000 |
| Traffic | đếm `request_received`, rate theo phút | requests/min, rate ≥ 1 |
| Errors | `request_failed / request_received`, breakdown `error_type` | %, ≤ 2 |
| Cost | tổng `response_sent.cost_usd` theo phút/toàn cửa sổ | USD, total ≤ 2.5 |
| Tokens | tổng `tokens_in`, `tokens_out` | tokens, ≤ 50000 |
| Quality | mean `response_sent.quality_score` | 0–1, ≥ 0.75 |

Đặt time range mặc định 60 phút, refresh 15–30 giây (contract hiện là 30), tên panel/đơn vị rõ và có threshold/SLO line. Chụp một ảnh nhìn được toàn bộ 6 panel: `dashboard_6panels.png`.

### 4.2. SLO và alert

Giữ cửa sổ 28 ngày trong `config/slo.yaml`: latency P95 ≤ 3000 ms/99.5%, error ≤ 2%/99%, daily cost ≤ 2.5 USD/100%, quality ≥ 0.75/95%. Thay `note` nếu nhóm có target khác, nhưng dashboard threshold phải nhất quán.

Thay toàn bộ `TODO` trong `config/alert_rules.yaml` và điền [docs/alerts.md](alerts.md). Ba alert symptom-based nên có điều kiện, thời gian duy trì, severity, owner và runbook 3 bước:

| Alert | Điều kiện gợi ý | Severity |
|---|---|---|
| `LatencyP95High` | P95 > 3000 ms liên tục 5 phút | warning |
| `ErrorRateHigh` | error rate > 2% liên tục 5 phút | critical |
| `DailyCostHigh` | tổng cost 24h > 2.5 USD | warning |

Runbook phải nói ảnh hưởng user, ba bước kiểm tra đầu, mitigation tạm thời và owner; alert dựa trên symptom/SLO, không dựa tên hàm nội bộ. Lưu ảnh/output alert nếu công cụ dashboard hỗ trợ.

Mẫu YAML có thể dùng trực tiếp sau khi thay owner:

```yaml
alerts:
  - name: LatencyP95High
    severity: warning
    condition: "p95(response_sent.latency_ms) > 3000 for 5m"
    type: symptom-based
    owner: "<ten-nguoi-truc>"
    runbook: docs/alerts.md#alert-1
  - name: ErrorRateHigh
    severity: critical
    condition: "error_rate(request_failed, request_received) > 2% for 5m"
    type: symptom-based
    owner: "<ten-nguoi-truc>"
    runbook: docs/alerts.md#alert-2
  - name: DailyCostHigh
    severity: warning
    condition: "sum(response_sent.cost_usd) over 24h > 2.5"
    type: symptom-based
    owner: "<ten-nguoi-truc>"
    runbook: docs/alerts.md#alert-3
```

Trong `docs/alerts.md`, mỗi heading `## Alert 1/2/3` phải lặp đủ tên, severity, SLI/SLO, condition + duration, ảnh hưởng user, ba bước kiểm tra, mitigation và owner.

### 4.3. Kiểm tra runtime practice

```powershell
python scripts/load_test.py --concurrency 5                 # baseline
python scripts/inject_incident.py --scenario rag_slow       # bật
python scripts/load_test.py --concurrency 5                 # P95 phải tăng rõ
python scripts/inject_incident.py --scenario rag_slow --disable
```

Chụp baseline và incident, cho thấy latency tăng rồi phục hồi. Ghi trace ID và correlation ID vào report.

## 5. Điều tra challenge chính thức (Checkpoint 3, 2:30–3:30)

Chỉ làm sau khi Lab Coach release `config/challenge.json`. File hiện mô tả cohort K3, challenge `day13-k3-observability-v1`, incident `rag_slow`, feature `refund`, threshold 2000 ms và 5 query; tuyệt đối không sửa file.

Trình tự:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/metrics       # baseline
python scripts/inject_incident.py                    # đọc incident từ challenge.json
python scripts/load_test.py --challenge --concurrency 5
Invoke-RestMethod http://127.0.0.1:8000/metrics
python scripts/inject_incident.py --scenario rag_slow --disable
```

Điều tra theo đúng chuỗi:

1. Metrics: P95/P99 tăng, traffic/error/cost/tokens gần như không đổi.
2. Langfuse: mở trace chậm nhất trong cửa sổ đó, xem waterfall; retrieval chiếm khoảng 2.5 giây trước generation.
3. JSONL: tìm `response_sent` có `feature=refund`, `latency_ms` khoảng 2500+ và cùng `correlation_id` với request/trace evidence.
4. Root cause: `app/mock_rag.py` gọi `time.sleep(2.5)` khi `STATE["rag_slow"]` bật; query refund đi vào corpus refund. Đây là nguyên nhân có bằng chứng, không suy đoán từ average latency.
5. Fix: tắt incident ngay; đề xuất timeout/deadline, circuit breaker và span retrieval riêng. Preventive: alert P95, dashboard phân theo feature, load test định kỳ, review SLO khi thêm dependency.

Lưu `challenge_metrics_before_after.png`, `challenge_trace_waterfall.png`, `challenge_log_line.png`, `challenge_investigation_summary.png`. Report phải ghi challenge ID, metric, trace ID, log line/correlation ID, root cause, fix và preventive measure.

## 6. Hoàn thiện report và evidence (3:30–4:00)

Tạo thư mục `submission/evidence/` nếu chưa có. Tối thiểu phải có:

```text
validate_logs_result.txt       validate_dashboard_result.txt
correlation_id_log.jsonl       correlation_id_header.png
pii_redaction_log.png          trace_list.png
trace_waterfall.png            trace_baseline.png
trace_candidate.png            prompt_versions.png
prompt_label_rollback.png      dashboard_6panels.png
challenge_metrics_before_after.png
challenge_trace_waterfall.png  challenge_log_line.png
challenge_investigation_summary.png
```

Mở `submission/REPORT.md` và thay **mọi** `[ĐIỀN ...]`, `[TÊN ...]`, `[MSSV ...]`, `[commit/PR]`, trace ID, số liệu và URL. Khai báo mỗi thành viên đúng phần việc và commit/PR thật; report phải khớp Git history. Dẫn link tương đối tới từng evidence. Không để placeholder trong bản nộp.

## 7. Kiểm tra cuối và nộp

```powershell
python -m pytest -q
python scripts/validate_logs.py
python scripts/validate_dashboard.py
git diff --check
git status --short
git log --oneline -n 10
```

Kỳ vọng: toàn bộ test pass, log score ≥80 (mục tiêu 100), dashboard `6/6`, không secret/PII, có ≥10 trace và đủ evidence. Kiểm tra lại bằng `git grep -n "TODO\|pk-lf-\|sk-lf-\|SECRET_KEY"` (TODO trong tài liệu mẫu cần thay hoặc giải thích; không commit key). Commit phần việc hợp lệ, push repo, lấy commit SHA cuối và nộp **repository URL + SHA** theo [SUBMISSION.md](../SUBMISSION.md). `.env`, `.venv`, log runtime bị ignore và không được ép add.

## 8. Kịch bản demo 3–5 phút và câu hỏi vấn đáp

Demo theo thứ tự: `/health` → `/metrics` baseline → mở trace Langfuse + prompt metadata → mở một log JSONL có correlation ID/PII đã redact → dashboard 6 panel + threshold → bật `rag_slow`, chạy challenge, chỉ ra Metrics → Traces → Logs → root cause → disable.

Phải trả lời được:

- Average latency có thể che tail latency, nên xem P95/P99.
- Correlation ID nối một HTTP request qua log/header; trace ID nối các span trong Langfuse, hai ID khác phạm vi.
- Khi error rate tăng, bắt đầu ở metrics để xác định thời gian/triệu chứng, rồi trace để khoanh span, log để chứng minh nguyên nhân.
- PII phải scrub trước JSON render và trước khi ghi file.
- Alert cần condition + duration + severity + owner + runbook/ảnh hưởng user.
- Cost tăng không kèm traffic: kiểm tra tokens in/out, prompt length, model, `cost_spike` và cost theo phút.
- Root cause chỉ hợp lệ khi metric, trace và log cùng cửa sổ/correlation ID nhất quán.
- `validate_logs.py` chỉ là kiểm tra kỹ thuật nhanh; rubric còn chấm dashboard runtime, incident, demo, report và commit cá nhân.

## 9. Bảng đối chiếu nhanh với rubric

| Tiêu chí | Việc phải chứng minh |
|---|---|
| Logging + PII | JSON schema, correlation xuyên request, metadata đủ, PII leak = 0 |
| Trace + prompt | ≥10 trace, v1/v2, name/label/version, promote + rollback |
| Dashboard/SLO/alert | đúng 6 panel từ JSONL, threshold, SLO, 3 alert và runbook |
| Incident | Metrics → trace → log cùng evidence, root cause/fix/prevention |
| Demo | hệ thống chạy được và thành viên giải thích được phần mình |
| Cá nhân | report rõ việc, commit/PR kiểm tra được, kiến thức liên quan |

Làm xong mỗi mục hãy tick ngay và lưu file evidence tương ứng; đừng chờ đến cuối buổi mới dựng lại bằng chứng.
