# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert 1

- Tên: `LatencyP95High`.
- Severity: `warning`.
- SLI/SLO liên quan: latency P95, mục tiêu <= 3000 ms trong cửa sổ 28 ngày.
- Điều kiện và thời gian duy trì: P95 `response_sent.latency_ms` > 3000 ms trong 5 phút liên tục.
- Ảnh hưởng tới người dùng: phản hồi chat chậm, dễ timeout hoặc bỏ cuộc.
- Ba bước kiểm tra đầu tiên: (1) xem panel Latency, xác nhận P95/P99; (2) mở trace chậm nhất trong cùng cửa sổ; (3) tìm log `response_sent` cùng correlation ID và so sánh `latency_ms`.
- Mitigation tạm thời: kiểm tra incident `rag_slow`, giảm concurrency và tắt dependency chậm nếu xác nhận được.
- Owner: `observability-team`.

## Alert 2

- Tên: `ErrorRateHigh`.
- Severity: `critical`.
- SLI/SLO liên quan: error rate, mục tiêu <= 2% trong cửa sổ 28 ngày.
- Điều kiện và thời gian duy trì: `request_failed / request_received` > 2% trong 5 phút liên tục.
- Ảnh hưởng tới người dùng: request thất bại, không nhận được câu trả lời.
- Ba bước kiểm tra đầu tiên: (1) xem panel Errors và breakdown `error_type`; (2) mở trace request lỗi; (3) tìm `request_failed` cùng correlation ID.
- Mitigation tạm thời: kiểm tra `tool_fail`, tắt incident và khôi phục dependency retrieval trước khi retry.
- Owner: `observability-team`.

## Alert 3

- Tên: `DailyCostHigh`.
- Severity: `warning`.
- SLI/SLO liên quan: daily cost, mục tiêu <= 2.5 USD.
- Điều kiện và thời gian duy trì: tổng `response_sent.cost_usd` trong 24 giờ > 2.5 USD.
- Ảnh hưởng tới người dùng: ngân sách inference bị vượt dù traffic có thể không tăng.
- Ba bước kiểm tra đầu tiên: (1) xem panel Cost theo phút; (2) so sánh `tokens_in` và `tokens_out`; (3) kiểm tra traffic, prompt length và incident `cost_spike`.
- Mitigation tạm thời: giảm concurrency, tắt `cost_spike`, giới hạn output token và review prompt/model.
- Owner: `observability-team`.
