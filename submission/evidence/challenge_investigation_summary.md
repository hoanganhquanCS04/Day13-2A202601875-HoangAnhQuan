# Challenge Investigation Summary

## Evidence collected

- Official challenge: `day13-k3-observability-v1` / cohort `K3`.
- Incident: `rag_slow`; affected feature: `refund`; released threshold: `2000 ms`.
- Clean baseline after API restart: traffic 0, P50/P95/P99 = 0 ms, error rate 0, cost 0.
- After the 5 official requests: traffic 5, P50/P95/P99 = 2651 ms, total cost 0.0096 USD, errors 0.
- Sample affected correlation ID: `req-aa84c97d`, session `k3-challenge-s04`, feature `refund`, response log latency 2651 ms.

## Root cause and response

`app/mock_rag.py` executes `time.sleep(2.5)` whenever `STATE["rag_slow"]` is true. The official refund queries enter retrieval, adding about 2500 ms before generation. The incident was disabled after collection. Recommended durable fixes are retrieval timeouts/deadlines, circuit breaking and a dedicated retrieval latency span/metric.

## Trace evidence limitation

This run has `tracing_enabled=false` because `.env` has no Langfuse public/secret keys. The repository does not contain a real Langfuse trace ID, prompt version screenshot or rollback screenshot, and none has been fabricated. Add the Lab Coach keys and collect those three evidence types before submission.
