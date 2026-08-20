# Exit Ticket

Học viên: Nguyễn Duy Hưng

Trả lời dựa trên số liệu benchmark thực tế đã chạy trong `reports/benchmark_report.md` và
`reports/trace_example.json` (cùng một query, so sánh baseline vs multi-agent).

## 1. Case nào nên dùng multi-agent? Vì sao?

Nên dùng khi **task cần citation/bằng chứng có thể truy vết**, và khi các bước xử lý đòi hỏi
tiêu chí đánh giá khác nhau đến mức khó gộp vào một prompt duy nhất mà không mất chất lượng.

Bằng chứng cụ thể từ benchmark của tôi: cùng một câu hỏi, baseline single-agent cho
**citation coverage = 0%** (model trả lời hoàn toàn từ kiến thức nội tại, không có bước tra
cứu nguồn nào tách biệt để trích dẫn), trong khi multi-agent đạt **citation coverage = 100%**
vì có Researcher tách riêng gắn `[source_id]` vào state trước khi Analyst/Writer sử dụng.

Cụ thể hơn, multi-agent hợp lý khi:

- Output cần được audit lại (research report, tài liệu pháp lý, tài liệu y tế) — citation
  coverage đo được là yêu cầu cứng, không phải "nice to have".
- Có một bước cần "góc nhìn thứ hai" độc lập với bước tạo ra nội dung — ví dụ Analyst trong hệ
  thống của tôi có nhiệm vụ minh bạch là tìm bằng chứng yếu/mâu thuẫn trong chính research
  notes, việc mà Researcher (người tạo ra notes đó) khó tự phát hiện vì thiên lệch xác nhận
  (confirmation bias) nếu gộp chung một agent.
- Chi phí tăng thêm (trong bài đo của tôi: cost tăng ~2.2x, latency tăng ~2.2x, từ 3 lệnh gọi
  LLM tuần tự thay vì 1) chấp nhận được so với giá trị của việc có trace/citation kiểm chứng
  được.

## 2. Case nào không nên dùng multi-agent? Vì sao?

Không nên dùng khi task đơn giản, không cần trích dẫn, và latency/cost quan trọng hơn khả năng
audit. Bằng chứng: baseline đã cho quality-proxy 5.0/10 chỉ trong 8.72s với cost 0.0005 USD,
tức là "đủ dùng" cho câu hỏi giải thích khái niệm thông thường — trả thêm 2.2x cost và 2.2x
latency để lấy quality-proxy 10.0 chỉ hợp lý nếu 10.0 đó (chủ yếu đến từ citation) thực sự có
giá trị với người dùng cuối.

Cụ thể hơn, nên tránh multi-agent khi:

- Task không có "câu trả lời sai lệch tốn kém" — ví dụ hỏi định nghĩa, tóm tắt nhanh, brainstorm
  — một LLM call là đủ, chia nhỏ chỉ tạo thêm overhead điều phối (guardrail, retry, trace) mà
  không đổi lại chất lượng tương xứng.
- Latency là yêu cầu cứng (ví dụ trả lời realtime cho người dùng đang chờ) — pipeline tuần tự
  Researcher → Analyst → Writer trong thiết kế của tôi cộng dồn latency của cả 3 LLM call, gần
  gấp đôi baseline; muốn giữ multi-agent trong ngữ cảnh latency-sensitive sẽ cần chạy song song
  các bước độc lập được, việc hệ thống hiện tại chưa làm (Analyst phụ thuộc tuần tự vào
  Researcher).
- Nguồn dữ liệu để Researcher tra cứu không tồn tại hoặc không đáng tin — lúc đó multi-agent
  không tạo thêm giá trị citation nào so với baseline mà chỉ tốn thêm tiền/thời gian, đồng thời
  có rủi ro mới: agent "tưởng" mình có nguồn tốt trong khi nguồn thực ra nghèo/nhiễu (xem
  `reports/failure_mode.md` cho ví dụ khi Researcher fail hẳn vì lỗi kết nối API).
