# Kịch bản demo cuối buổi (3–5 phút)

*(Người 1 — Hoàng Anh Quân, Setup & Integration Lead)*

Luồng demo bám đúng yêu cầu chấm điểm: **Metrics → Traces → Logs → Root cause**.

## 0. Chuẩn bị trước khi vào demo

Terminal 1 — API phải chạy trước:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file .env
```

Terminal 2 — kiểm tra toàn bộ điều kiện demo bằng một lệnh:

```powershell
python scripts/preflight.py --require-api
```

Phải thấy `SẴN SÀNG: toàn bộ hạng mục đã đạt.` trước khi bắt đầu. Nếu có `[FAILED]`,
sửa theo phần *Lỗi thường gặp* trong [SETUP.md](../SETUP.md).

> **Lưu ý cổng 8000:** nếu máy đang chạy service khác (Docker, lab Day 12) chiếm cổng,
> uvicorn vẫn bind được `127.0.0.1:8000` và ưu tiên cho localhost. Kiểm tra bằng
> `curl http://127.0.0.1:8000/health` — kết quả phải có `tracing_enabled`.

## 1. Chạy demo tự động (khuyến nghị)

Một lệnh chạy trọn 6 bước và tự ghi evidence vào `submission/evidence/demo_*`:

```powershell
python scripts/demo_e2e.py
```

Script tự đọc incident từ [config/challenge.json](../config/challenge.json) và **luôn tắt
incident ở bước cuối**, kể cả khi lỗi giữa chừng. Thoát với mã `1` nếu P95 không vượt
ngưỡng — dấu hiệu incident chưa bật đúng.

Tuỳ chọn:

| Cờ | Dùng khi |
|----|----------|
| `--scenario rag_slow` | Tập dượt trước, không dùng challenge chính thức |
| `--no-evidence` | Diễn thử, không muốn ghi đè file evidence |
| `--concurrency 5` | Số request song song mỗi lần load test (mặc định 5) |

## 2. Lời thoại theo từng bước

Kết quả thật của lần chạy đã lưu tại
[`submission/evidence/demo_e2e_run.txt`](../submission/evidence/demo_e2e_run.txt).

### Bước 1 — Health (≈20 giây)

```powershell
curl http://127.0.0.1:8000/health
```

> "API sống, `tracing_enabled: true` nghĩa là Langfuse đã nhận key, và hiện không có
> incident nào đang bật."

Evidence: [`demo_01_health.json`](../submission/evidence/demo_01_health.json)

### Bước 2 — Metrics baseline (≈30 giây)

> "Chạy load test 10 request bình thường. P95 = **1034 ms**, error rate 0, quality 0.88.
> Đây là trạng thái khoẻ mạnh để so sánh."

Evidence: [`demo_03_metrics_baseline.json`](../submission/evidence/demo_03_metrics_baseline.json)

### Bước 3 — Bật incident (≈20 giây)

> "Mô phỏng sự cố production: bật `rag_slow` — đúng incident mà Lab Coach release cho
> cohort K3, ảnh hưởng feature `refund`."

Evidence: [`demo_04_incident_enable.json`](../submission/evidence/demo_04_incident_enable.json)

### Bước 4 — Metrics phát hiện triệu chứng (≈40 giây)

> "Chạy 5 query challenge. P95 nhảy từ **1034 ms lên 2651 ms**, vượt ngưỡng 2000 ms của
> challenge. Đáng chú ý: P50 vẫn 150 ms, error rate vẫn 0, cost gần như không đổi — nên
> đây **không phải** lỗi LLM hay lỗi hệ thống, mà là một nhánh xử lý bị chậm."

Evidence: [`demo_06_metrics_incident.json`](../submission/evidence/demo_06_metrics_incident.json)

### Bước 5 — Traces rồi Logs khoanh vùng (≈60 giây)

Mở Langfuse, lọc trace chậm nhất trong cửa sổ incident:

> "Trace waterfall cho thấy span **retrieval** chiếm gần hết thời gian, span generation
> gần như không đổi so với baseline."

Evidence trace: [`langfuse_challenge_trace_waterfall.json`](../submission/evidence/langfuse_challenge_trace_waterfall.json)

Quay lại log, ghép bằng correlation ID:

> "Request chậm nhất là `req-29634285`, `feature=refund`, `session_id=k3-challenge-s03`,
> `latency_ms=2651`. Cùng một correlation ID nối được metric → trace → log."

Evidence: [`demo_07_log_slowest.json`](../submission/evidence/demo_07_log_slowest.json)

### Bước 6 — Root cause và mitigation (≈60 giây)

> "Root cause: khi `rag_slow` bật, `retrieve()` trong `app/mock_rag.py` chèn `time.sleep(2.5)`
> trước khi trả document. Mọi query challenge đều là feature `refund` nên đi qua RAG path,
> cộng thẳng ~2500 ms vào latency ở bước retrieval.
>
> Mitigation ngay: tắt incident. Sau khi tắt, request chậm nhất chỉ còn **150 ms** — xác
> nhận đúng nguyên nhân.
>
> Phòng ngừa: alert **LatencyP95High** gắn với SLO P95 ≤ 3000 ms, runbook 3 bước kiểm tra
> incident flag và span retrieval trước; thêm timeout/circuit breaker cho bước retrieval."

Evidence: [`demo_08_incident_disable.json`](../submission/evidence/demo_08_incident_disable.json),
[`demo_10_summary.json`](../submission/evidence/demo_10_summary.json)

## 3. Nếu phải demo thủ công

Khi không dùng `demo_e2e.py`, chạy tuần tự:

```powershell
curl http://127.0.0.1:8000/health
python scripts/load_test.py --concurrency 5
curl http://127.0.0.1:8000/metrics
python scripts/inject_incident.py
python scripts/load_test.py --challenge --concurrency 5
curl http://127.0.0.1:8000/metrics
python scripts/inject_incident.py --disable
```

Nhớ chạy lệnh cuối để tắt incident, nếu không dashboard và metrics của nhóm sau sẽ sai.

## 4. Chốt sau demo

```powershell
python -m pytest -q
python scripts/validate_logs.py
python scripts/validate_dashboard.py
python scripts/preflight.py --require-api
git status --short
```

Cả năm lệnh phải sạch trước khi nộp URL repo và commit SHA cuối.
