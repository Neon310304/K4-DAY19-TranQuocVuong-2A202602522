# Báo cáo Day 19 — Flat RAG vs GraphRAG

**Họ tên:** Trần Quốc Vương  **MSSV:** 2A202602522  **Ngày cập nhật:** 2026-10-05

> Kỳ vọng và thang điểm: `SUBMISSION.md`. Mọi số liệu phải khớp với `ket_qua_benchmark_kg.txt`. Bản thiết kế ontology nộp riêng ở `report/ONTOLOGY.md`.

**BẢN NHÁP — CHƯA ĐỦ ĐIỀU KIỆN NỘP.** KG-1 đến KG-4 và test đã hoàn thiện; benchmark live chưa chạy thành công vì repo chưa có cấu hình API. Chưa có file kết quả, ba ảnh Neo4j hoặc hai lỗi được chứng minh trên dữ liệu thật. Không dùng fixture test, số 0 hoặc số liệu giả thay kết quả benchmark.

## 1. Chi phí (10 điểm)

Chưa có bảng Indexing/Querying: lệnh `--judge` dừng ở SETUP-1 trước khi gọi API và tạo file kết quả. Các ô dưới là chưa đo, không phải chi phí bằng 0. Sẽ thay bằng hai bảng nguyên văn từ `ket_qua_benchmark_kg.txt` sau khi chạy thành công.

| Chỉ số | Flat | Graph | Graph / Flat |
| --- | --- | --- | --- |
| Indexing USD | Chưa đo | Chưa đo | Chưa tính |
| Indexing giây | Chưa đo | Chưa đo | Chưa tính |
| Mỗi câu: USD | Chưa đo | Chưa đo | Chưa tính |
| Mỗi câu: giây | Chưa đo | Chưa đo | Chưa tính |
| Mỗi câu: in_tok | Chưa đo | Chưa đo | Chưa tính |

**Chi phí tăng thêm đến từ đâu?** (2–3 câu)
Về cơ chế, Graph indexing gồm embedding index dùng chung và phần LLM extraction/build KG; querying thêm graph facts vào ngữ cảnh cùng vector chunks. Đây chưa phải kết luận số liệu: cần benchmark để biết overhead token/latency và lợi ích recall. Judge calls có chi phí thật nhưng runner không cộng vào usage của pipeline; USD của gateway YesScale phải được đối chiếu với giá thực tế thay vì coi bảng giá OpenAI là hóa đơn.

## 2. Từng câu hỏi (10 điểm)

| Câu | Loại | Flat recall / judge | Graph recall / judge | Thắng | Vì sao (1 câu) |
| --- | --- | --- | --- | --- | --- |
| Q1 | single-hop-law | Chưa đo | Chưa đo | Chưa kết luận | Cần đọc định nghĩa tiền chất và câu trả lời thực tế. |
| Q2 | single-hop-news | Chưa đo | Chưa đo | Chưa kết luận | Cần đối chiếu mức án từng người trong vụ hơn 36 kg. |
| Q3 | cross-kb | Chưa đo | Chưa đo | Chưa kết luận | Cần đối chiếu sentence phía tin với khoản 1 phía luật. |
| Q4 | cross-kb | Chưa đo | Chưa đo | Chưa kết luận | Cần kiểm tra context có khoản khung tối đa, không suy thành án đã tuyên. |
| Q5 | cross-kb-multi-hop | Chưa đo | Chưa đo | Chưa kết luận | Cần kiểm tra người–lượng–chất–khoản, không chỉ tên chất. |
| Q6 | aggregation | Chưa đo | Chưa đo | Chưa kết luận | Cần so tập vụ trong graph với answer nguyên văn. |

Sau khi chạy, đọc toàn bộ 12 câu trả lời ở Per question, không chỉ các điểm trung bình; ghi rõ câu nào thắng/hòa và lý do bằng chứng cụ thể. Không mặc định GraphRAG thắng vì có thêm graph context.

## 3. Phân tích lỗi (20 điểm)

**Chưa có hai lỗi được chứng minh.** Graph lưu bền vững có 0 node vì chưa nạp, không phải bằng chứng E1. Kết quả test fixture đã rollback chỉ kiểm chứng code, không chứng minh lỗi extraction/answer của LLM thật.

Truy vấn Q-A/Q-B/Q-D và E1–E6 đã chuẩn bị trong `report/GRAPH_DIAGNOSTICS.md`. Mỗi lỗi được chọn sau benchmark phải thuộc nhóm khác nhau và đủ bốn mục: hiện tượng, bằng chứng nguyên văn/Cypher kèm kết quả, nguyên nhân trong pipeline, đề xuất sửa kèm trade-off. Không coi property rỗng hợp lý hoặc điểm recall/judge khác thang là lỗi khi chưa đối chiếu nguồn.

| Quan sát | Mã lỗi | Hiện tượng | Bằng chứng | Nguyên nhân | Đề xuất sửa |
| --- | --- | --- | --- | --- | --- |
| 1 | Chưa xác định | Chưa quan sát trên graph/answer thật | Chưa có | Chưa kết luận | Chờ bằng chứng |
| 2 | Chưa xác định | Chưa quan sát trên graph/answer thật | Chưa có | Chưa kết luận | Chờ bằng chứng |

## 4. Kết luận (5 điểm)

Khi nào nên dùng KG, khi nào Flat RAG là đủ? Dẫn số liệu ở mục 1–2.
Chưa có số liệu để kết luận hệ thống nào đáng dùng hơn. Giả thuyết cần kiểm chứng là KG hữu ích cho truy vấn nối người/vụ ở tin sang tội/điều/khoản ở luật, còn câu hỏi chỉ cần một đoạn luật hoặc một bài báo có thể được Flat RAG đáp ứng với overhead thấp hơn. Chỉ chốt kết luận sau khi dẫn số liệu indexing/querying, recall/judge Q1–Q6 và lỗi thực tế; không công bố điểm hòa vốn khi thiếu cơ sở chi phí.

## 5. Tự kiểm (5 điểm)

```
$ .\.venv\Scripts\python.exe -m pytest tests/test_base.py tests/test_graph.py -q
48 passed in 0.09s

$ .\.venv\Scripts\python.exe -m pytest tests/ -q
83 passed, 10 subtests passed in 0.12s
```

83 test gồm 48 test gốc không bị chỉnh sửa và 35 test bổ sung. Neo4j driver đã kiểm chứng multi-hop, charge cá nhân, alias/khung tối đa, định nghĩa PCMT, aggregation MDMA, giới hạn context và prompt KG-4 bằng fixture tổng hợp trong transaction; toàn bộ fixture rollback và không tính là benchmark live.

Kết quả `--check` gần nhất:

```text
[OK] Dữ liệu: 18 điều luật, 20 bài báo
[OK] KG-1 link_entity
[OK] Neo4j kết nối được

[LỖI SETUP-1] Chưa dùng được provider LLM: Chưa có API key nào cho chat: cần một trong OPENAI_API_KEY / OPENROUTER_API_KEY / GEMINI_API_KEY / ANTHROPIC_API_KEY
  Cách sửa: copy .env.example thành .env, điền ít nhất một key: OPENAI_API_KEY, OPENROUTER_API_KEY, GEMINI_API_KEY hoặc ANTHROPIC_API_KEY (Anthropic chỉ dùng cho chat; embedding cần một trong 3 key đầu).
  Tra bảng lỗi: LAB_GUIDE.md mục 'Xử lý lỗi'
```

Chỉ có ba `[OK]`, chưa đủ bảy; exit code của `--check` và `--judge` đều là 1. Provider/model live và số liệu benchmark chưa được xác nhận. Đây là lỗi cấu hình trước pipeline, không tính là một trong hai lỗi E1–E6 cần phân tích.

Kiểm tra Git trước khi đưa code lên repo: `git diff --check` thành công; `bench_kg.py`, hai file test gốc và `data/` không có thay đổi. `git check-ignore .env` trả về `.env`, `git ls-files .env` không có kết quả; không có `.env` hoặc `.venv/` trong danh sách file được theo dõi/không bị ignore. Kiểm tra các mẫu API token phổ biến trên file text và diff của toàn bộ lịch sử Git không phát hiện key; kiểm tra theo mẫu không phải bảo đảm phát hiện mọi loại bí mật.

| Ảnh cần nộp | Trạng thái |
| --- | --- |
| `report/img/kg_count.png` | Chưa chụp — chờ graph đầy đủ |
| `report/img/kg_cross_kb.png` | Chưa chụp — chờ graph đầy đủ |
| `report/img/kg_my_case.png` | Chưa chụp — chờ graph đầy đủ |

Người đã chọn cho Q-D: chưa xác minh; sẽ chọn node thật khác Lê Minh Thành theo truy vấn chuẩn bị, rồi ghi họ tên chính xác tại đây.

## Vấn đề gặp phải (không tính điểm)

Lệnh đã thử từ root bằng interpreter `.venv`:

```text
$ python bench_kg.py --judge

[LỖI SETUP-1] Chưa dùng được provider LLM: Chưa có API key nào cho chat: cần một trong OPENAI_API_KEY / OPENROUTER_API_KEY / GEMINI_API_KEY / ANTHROPIC_API_KEY
  Cách sửa: copy .env.example thành .env, điền ít nhất một key: OPENAI_API_KEY, OPENROUTER_API_KEY, GEMINI_API_KEY hoặc ANTHROPIC_API_KEY (Anthropic chỉ dùng cho chat; embedding cần một trong 3 key đầu).
  Tra bảng lỗi: LAB_GUIDE.md mục 'Xử lý lỗi'
```

Exit code là 1; chưa sinh `ket_qua_benchmark_kg.txt`, chưa gọi paid API, Neo4j lưu bền vững vẫn có 0 node. `.env` đã được tạo và Git bỏ qua nhưng các biến key được repo hỗ trợ vẫn trống. Người dùng dự định dùng YesScale; còn cần key được lưu đúng file, Base URL, chat/embedding model và ngân sách chạy được xác nhận. Không gửi key trong chat; dùng `OPENAI_API_KEY` và `OPENAI_BASE_URL` cho gateway tương thích OpenAI, hoặc cấu hình embedding provider khác nếu gateway không có embedding API.

Với cấu hình gateway này, đặt `LLM_PROVIDER=openai`; tên model của chat và embedding lần lượt dùng `OPENAI_CHAT_MODEL` và `OPENAI_EMBEDDING_MODEL`, không dùng một biến `LLM_MODEL` chung. SDK đọc `OPENAI_BASE_URL` để tránh gửi key gateway sang endpoint OpenAI mặc định. Sau khi lưu cấu hình, chạy lại `--check`, rồi `--judge` từ code cuối cùng trước khi điền số liệu và chụp ảnh. Hai bảng chi phí phải sao chép từ file kết quả thật; chỉ tính Graph/Flat khi mẫu số khác 0, và ghi N/A nếu không xác định được tỉ lệ.

### Checklist bước benchmark/ảnh/lỗi

- [x] Code và test hoàn thiện; chuẩn bị query Browser theo ontology hiện tại.
- [x] Ghi lại lỗi setup và phân biệt dữ liệu fixture với kết quả live.
- [ ] Full `--judge` chạy thành công, sinh file kết quả hợp lệ từ code cuối.
- [ ] Đọc đủ 12 câu trả lời, điền số liệu và nhận định Q1–Q6.
- [ ] Chụp ba ảnh Browser thật, đủ query input và Results overview.
- [ ] Ghi bằng chứng cho ít nhất hai nhóm lỗi khác nhau, đủ bốn phần.

### Trạng thái nộp bài

Repo bài làm: https://github.com/Neon310304/K4-DAY19-TranQuocVuong-2A202602522

Bản hiện tại chỉ là code đã kiểm thử và báo cáo nháp; chưa đủ điều kiện nộp theo `SUBMISSION.md`. Chưa có xác nhận link đã được nộp lên VLearn. Không chọn bonus ontology riêng, nên không tạo file `ket_qua_benchmark_kg.hint.txt` khi chưa có phép đo HINT thật.
