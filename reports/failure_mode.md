# Failure Mode: LLM provider call failure (invalid/expired API key)

Học viên: Nguyễn Duy Hưng

## Cách tái hiện

Chạy multi-agent workflow với `OPENAI_API_KEY` sai và `MAX_ITERATIONS=3` (để rút ngắn thời
gian demo) mà không sửa `.env` thật:

```bash
OPENAI_API_KEY="sk-invalid-demo-key" MAX_ITERATIONS=3 \
  python -m multi_agent_research_lab.cli multi-agent \
  --query "Compare single-agent vs multi-agent architectures for research report writing"
```

## Quan sát được (log thật, không phải suy đoán)

1. `ResearcherAgent.run` gọi `LLMClient.complete`, provider trả lỗi
   `401 invalid_api_key`.
2. `LLMClient._create_completion` retry nội bộ 3 lần (tenacity, exponential backoff), tất cả
   đều fail vì key sai không tự khỏi được → sau lần thứ 3, `LLMClient.complete` bắt exception
   gốc và raise `AgentExecutionError("LLM call failed after retries: ...")`.
3. `MultiAgentWorkflow._wrap` bắt `AgentExecutionError` ở tầng node, **không để graph crash**:
   ghi lỗi vào `state.errors`, thêm trace event `researcher.failed`, trả `state` nguyên vẹn về
   Supervisor.
4. Vì `state.research_notes` vẫn `None` (Researcher chưa từng ghi thành công), Supervisor route
   lại `researcher` ở vòng lặp kế tiếp → lặp lại bước 1-3 — đây chính là cơ chế **retry ở cấp
   bước** đã thiết kế (khác với retry ở cấp API call trong `LLMClient`).
5. Sau đúng `max_iterations=3` vòng lặp thất bại liên tiếp, Supervisor tự ép route `done`
   (guardrail `max_iterations`), ghi thêm lỗi `"Supervisor: reached max_iterations=3,
   stopping."`.
6. `CriticAgent` chạy, thấy `final_answer=None`, tự bỏ qua validation (`critic.skipped`,
   `reason: no final_answer`) thay vì raise lỗi thêm.
7. CLI vẫn thoát bình thường, in ra `ResearchState` đầy đủ với `final_answer=null` và
   `state.errors` liệt kê chính xác 3 lần fail + lý do dừng — **không có exception nào lọt ra
   ngoài, không treo vô hạn, người vận hành đọc `errors` là hiểu ngay nguyên nhân.**

## Vì sao đây là kết quả đúng theo thiết kế, không phải bug

Guardrail hoạt động đúng thứ tự đã định (`agents/supervisor.py`): retry bị chặn trên bởi
`max_iterations` nên không lặp vô hạn dù nguồn lỗi (key sai) không tự phục hồi được. Đây là
hành vi "fail gracefully with partial state" đã chủ đích thiết kế trong
`docs/design_template.md` (mục Guardrails).

## Điểm yếu thực sự và cách fix

Vấn đề không phải ở việc hệ thống crash, mà ở **chi phí lãng phí**: cả 3 vòng lặp đều retry lại
đúng một request chắc chắn sẽ fail (sai key là lỗi vĩnh viễn, không phải lỗi tạm thời như rate
limit hay timeout mạng) — tốn ~3 lần gọi API (mỗi lần retry nội bộ 3 lần nữa = 9 lần request
thực tế) trước khi dừng, dù lẽ ra có thể phát hiện và dừng ngay từ lần fail đầu tiên.

**Cách fix đề xuất** (chưa implement, để dành làm bài tập mở rộng):

1. Trong `LLMClient._create_completion`, phân loại lỗi trước khi retry: dùng
   `tenacity.retry_if_exception_type` chỉ retry với lỗi tạm thời (timeout, 429 rate limit, 5xx),
   và `reraise` ngay lập tức (không retry) với lỗi vĩnh viễn như `401 invalid_api_key` — OpenAI
   SDK phân biệt rõ qua `openai.AuthenticationError` vs `openai.APIConnectionError`/
   `openai.RateLimitError`.
2. Ở tầng Supervisor, thêm một "circuit breaker" đơn giản: nếu cùng một agent fail liên tiếp
   với cùng loại lỗi ≥ 2 lần, route thẳng tới `done` thay vì chờ hết `max_iterations` — vừa tiết
   kiệm cost, vừa trả lỗi nhanh hơn cho người dùng.

Cả hai thay đổi đều không phá vỡ guardrail hiện có (`max_iterations`/`timeout_seconds` vẫn là
lưới an toàn cuối cùng), chỉ làm hệ thống dừng sớm hơn khi biết chắc retry là vô ích.
