# Design Template

## Problem

Hệ thống cần nhận một câu hỏi nghiên cứu (`ResearchQuery.query`), tìm bằng chứng liên quan,
đối chiếu/đánh giá độ tin cậy của bằng chứng đó, rồi viết một câu trả lời có cấu trúc, có
citation rõ ràng (`[source_id]`) cho đối tượng đọc kỹ thuật (`audience`). Ràng buộc quan
trọng: hệ thống phải chạy được offline (không cần web search thật), phải có giới hạn số vòng
lặp/thời gian, và phải đo được latency, cost, citation coverage, quality để so sánh với một
baseline đơn giản hơn.

## Why multi-agent?

Một agent đơn (baseline trong `cli.py baseline`) làm cả ba việc — tìm, phân tích, viết —
trong một lần gọi LLM duy nhất, dựa hoàn toàn vào kiến thức nội tại của model. Kết quả đo
được: **0% citation coverage** vì không có bước tra cứu bằng chứng nào tách biệt để model
trích dẫn.

Multi-agent tách được vì mỗi bước đòi hỏi *loại thông tin khác nhau* và *tiêu chí đúng/sai
khác nhau*:

- **Researcher** cần quyền truy cập một nguồn dữ liệu cụ thể (corpus offline) và nhiệm vụ là
  bám sát, không suy diễn.
- **Analyst** cần đọc lại chính research notes để tìm mâu thuẫn/bằng chứng yếu — việc này đòi
  hỏi một "góc nhìn thứ hai" độc lập với việc tìm kiếm.
- **Writer** cần tối ưu cho người đọc (audience, độ dài, cấu trúc) — khác hẳn tiêu chí của hai
  agent trên.

Khi tách ra, mỗi agent có system prompt hẹp, nhiệm vụ rõ, nên dễ kiểm soát chất lượng hơn.
Cái giá phải trả là latency và cost cao hơn hẳn — số đo thực tế trong
`reports/benchmark_report.md`:

| Run | Latency (s) | Cost (USD) | Quality (proxy) | Citation cov. |
|---|---:|---:|---:|---:|
| single-agent baseline | 8.72 | 0.0005 | 5.0 | — |
| multi-agent workflow | 18.90 | 0.0011 | 10.0 | 100% |

Multi-agent chậm hơn ~2.2x và tốn hơn ~2.2x, nhưng là cách duy nhất trong thiết kế này đạt
citation coverage > 0%, vì chỉ multi-agent có bước Researcher tách riêng gắn `source_id` vào
state trước khi Writer viết.

## Agent roles

| Agent | Responsibility | Input | Output | Failure mode |
|---|---|---|---|---|
| Supervisor | Quyết định worker nào chạy tiếp theo dựa trên field còn thiếu trong state; ép dừng khi vượt guardrail | `state.sources`, `state.research_notes`, `state.analysis_notes`, `state.final_answer`, `state.iteration` | 1 route string ghi vào `state.route_history` (`researcher`/`analyst`/`writer`/`done`) | Route sai nếu state bị corrupt; được chặn bởi `max_iterations`/`timeout_seconds` nên không loop vô hạn |
| Researcher | Tìm nguồn liên quan trong corpus offline, tóm tắt thành notes có gắn `[source_id]` | `request.query`, `request.max_sources` | `state.sources`, `state.research_notes` | LLM call fail sau 3 lần retry → `AgentExecutionError`; workflow bắt lỗi, ghi vào `state.errors`, Supervisor tự động thử lại Researcher ở vòng sau (đến khi hết `max_iterations`) |
| Analyst | Trích claim chính, so sánh nguồn, gắn cờ bằng chứng yếu/mâu thuẫn | `state.research_notes` | `state.analysis_notes` | Raise nếu gọi khi chưa có `research_notes` (bug điều phối); LLM fail xử lý giống Researcher |
| Writer | Tổng hợp research + analysis thành câu trả lời cuối, giữ nguyên citation | `state.research_notes`, `state.analysis_notes`, `request.audience` | `state.final_answer` | Raise nếu chưa có `analysis_notes`; LLM fail xử lý giống trên |
| Critic (bonus) | Validate citation coverage của `final_answer`, không chặn pipeline | `state.final_answer`, `state.sources` | Cảnh báo vào `state.errors` nếu coverage < 30% | Không có failure mode chặn — thiết kế cố ý non-blocking để không biến 1 cảnh báo thành 1 lần fail toàn hệ thống |

## Shared state

`ResearchState` (`core/state.py`) là nguồn sự thật duy nhất đi xuyên suốt graph:

- `request: ResearchQuery` — câu hỏi gốc + `max_sources`/`audience`, mọi agent đều cần để biết
  đang làm cho ai/với phạm vi nào.
- `iteration`, `route_history` — Supervisor dùng để enforce `max_iterations` và để trace lại
  đường đi routing khi debug.
- `started_at` — mốc thời gian để Supervisor enforce `timeout_seconds` (guardrail thứ hai,
  độc lập với `max_iterations`).
- `sources` — output của Researcher, input của Critic (đối chiếu citation coverage).
- `research_notes` → `analysis_notes` → `final_answer` — chuỗi handoff tuần tự giữa 3 worker;
  Supervisor dùng chính sự *có mặt/vắng mặt* của 3 field này để quyết định route tiếp theo,
  nên không cần thêm cờ trạng thái riêng.
- `agent_results` — lưu `AgentResult` (agent, content, metadata gồm token/cost) của từng bước,
  dùng để tính `estimated_cost_usd` trong benchmark mà không phải gọi lại LLM.
- `trace` — danh sách sự kiện dạng `{name, payload}` ghi bởi mọi agent (`add_trace_event`), là
  nguồn cho phần "trace explanation" trong peer review rubric.
- `errors` — không dừng chương trình, chỉ tích luỹ cảnh báo/lỗi (từ Supervisor timeout, agent
  fail, hoặc Critic low-coverage) để benchmark tính `failure_rate` và để người review biết sai
  ở đâu.

## Routing policy

```text
                 ┌────────────────────────────┐
                 │                            │
                 ▼                            │
Entry ──────▶ supervisor ──researcher──▶ researcher
                 │                            │
                 │◀───────────────────────────┘
                 │
                 ├──analyst────▶ analyst ──┐
                 │◀────────────────────────┘
                 │
                 ├──writer─────▶ writer ───┐
                 │◀────────────────────────┘
                 │
                 └──done───────▶ critic ──▶ END
```

Supervisor là node duy nhất có conditional edge; 3 worker luôn báo cáo lại về Supervisor sau
mỗi bước (không có cạnh nối thẳng worker → worker) để Supervisor luôn có cơ hội re-check
guardrail trước khi quyết định bước kế tiếp. Điều kiện route (theo thứ tự ưu tiên, xem
`agents/supervisor.py`):

1. `iteration >= max_iterations` hoặc `elapsed > timeout_seconds` → `done` (dừng cưỡng bức).
2. Chưa có `sources`/`research_notes` → `researcher`.
3. Có `research_notes` nhưng chưa có `analysis_notes` → `analyst`.
4. Có `analysis_notes` nhưng chưa có `final_answer` → `writer`.
5. Đủ cả ba → `done` → chuyển sang `critic` → `END`.

## Guardrails

- **Max iterations**: `MAX_ITERATIONS` (mặc định 6, `.env`) — Supervisor đếm qua
  `state.iteration`, ép route `done` khi vượt, dù state chưa đầy đủ.
- **Timeout**: `TIMEOUT_SECONDS` (mặc định 60, `.env`) — Supervisor so `time.time() -
  state.started_at`, độc lập với max_iterations (chặn cả trường hợp 1 LLM call bị treo lâu dù
  số vòng lặp còn ít).
- **Retry**: nằm ở 2 tầng — (1) `LLMClient._create_completion` retry tối đa 3 lần với
  exponential backoff (tenacity) cho lỗi mạng/API tạm thời; (2) tầng graph, nếu 1 agent raise
  `AgentExecutionError` sau khi hết retry, `workflow._wrap` bắt lỗi, ghi vào `state.errors`,
  và để Supervisor tự nhiên route lại đúng agent đó ở vòng sau (vì output field vẫn trống) —
  đây là "retry ở cấp bước", bị chặn trên bởi max_iterations nên không thể vô hạn.
- **Fallback**: khi hết `max_iterations`/`timeout` mà pipeline chưa hoàn chỉnh, workflow vẫn
  trả về `ResearchState` với dữ liệu từng phần (`sources`/`research_notes`/... field nào có
  thì giữ) thay vì crash — CLI/benchmark vẫn nhận được kết quả (có thể `final_answer=None`)
  và `state.errors` giải thích lý do dừng sớm.
- **Validation**: `CriticAgent` chạy cuối pipeline, đối chiếu mọi `source_id` trong
  `state.sources` với text của `final_answer`; nếu citation coverage < 30%, ghi cảnh báo vào
  `state.errors` (không raise, không chặn kết quả) — best-effort quality gate.

## Observability / tracing

Hai tầng, bổ sung cho nhau:

1. **In-state trace (luôn bật)**: mọi agent gọi `state.add_trace_event(...)`, nên `ResearchState.trace`
   luôn chứa đủ chuỗi quyết định của Supervisor và kết quả từng worker. Đây là nguồn cho
   `reports/trace_example.json` và không phụ thuộc nhà cung cấp nào.
2. **LangSmith (bật khi có `LANGSMITH_API_KEY`)**: `observability/trace_span()` mirror mỗi span
   (`researcher.search`, `researcher.llm_call`, `analyst.llm_call`, `writer.llm_call`) thành một
   run trên LangSmith, kèm duration và các attribute mà agent set trong block.

Hai điểm thiết kế đáng lưu ý:

- **Tracing không bao giờ được làm hỏng research run.** Lỗi từ LangSmith (mất mạng, key sai) chỉ
  degrade về span local kèm log warning. Ngược lại, exception từ *chính block của caller* thì phải
  truyền nguyên vẹn ra ngoài, nếu không `AgentExecutionError` sẽ bị nuốt và guardrail retry/
  max_iterations mất tác dụng — có test riêng cho cả hai chiều này trong `tests/test_tracing.py`.
- **Chỉ cần set `LANGSMITH_API_KEY`, không cần `LANGSMITH_TRACING=true`.** LangSmith mặc định tắt
  tracing và sẽ *âm thầm* dựng run rồi không upload; `trace_span` bật tracing tường minh để tránh
  tình trạng "nhìn như đã trace mà server không nhận được gì".

## Benchmark plan

Chạy qua `scripts/run_benchmark.py --query "..."`, dùng `evaluation.run_benchmark` cho cả
`run_baseline` và `run_multi_agent` trên **cùng một query**, ghi kết quả vào
`reports/benchmark_report.md` qua `render_markdown_report`.

| Query | Metric đo | Kỳ vọng |
|---|---|---|
| "Compare single-agent vs multi-agent architectures for research report writing" | Latency (wall-clock) | Multi-agent chậm hơn baseline (đã đo: ~19s vs ~9s, do 3 LLM call tuần tự thay vì 1) |
| — | Cost (USD, từ token usage) | Multi-agent tốn hơn (đã đo: ~$0.0011 vs ~$0.0005, ~2.2x) |
| — | Citation coverage | Baseline = 0% (không có bước tra nguồn); multi-agent > 0% (đã đo: 100%) |
| — | Quality (length + citation-density proxy, 0-10) | Multi-agent ≥ baseline; xác nhận lại bằng peer review rubric (0-10 thật), vì proxy tự động chỉ là ước lượng thô |
| — | Failure rate | Cả hai = 0% khi API key hợp lệ và mạng ổn định; test thêm bằng cách xoá `OPENAI_API_KEY` để xem guardrail/error message có kích hoạt đúng không |

Query bổ sung nên thử (chưa chạy, để mở rộng benchmark): một câu hỏi *ngoài phạm vi* corpus
offline (ví dụ hỏi về một chủ đề không có trong `ai_agent_offline_research_corpus_v2/topics/`)
để kiểm tra Researcher có báo "không tìm thấy nguồn phù hợp" một cách trung thực thay vì bịa
citation hay không — đây là test case tốt cho phần "failure mode" của exit ticket.
