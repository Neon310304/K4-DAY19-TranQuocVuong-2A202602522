# Báo cáo Day 19 — Flat RAG vs GraphRAG

**Họ tên:** Trần Quốc Vương · **MSSV:** 2A202602522 · **Ngày đo:** 2026-10-05

Kết quả nguồn: [`ket_qua_benchmark_kg.txt`](../ket_qua_benchmark_kg.txt), được runner sinh bằng `python bench_kg.py --judge`, không sửa tay. Ontology: [`ONTOLOGY.md`](ONTOLOGY.md). Đã đọc đủ 12 câu trả lời, kiểm tra graph thật và chụp ba ảnh Neo4j Browser; phần bắt buộc hoàn thành tại máy. Không nhận bonus ontology riêng và chưa xác nhận nộp VLearn.

## 1. Chi phí

### Điều kiện đo

- Python 3.11.15, Neo4j 5 trong container lab riêng `neo4j-drug-kg`; không dùng database chung.
- Gateway YesScale tương thích OpenAI: `LLM_PROVIDER=openai`, `EMBEDDING_PROVIDER=openai`, host `api.yescale.io` qua `OPENAI_BASE_URL`; key chỉ trong `.env` bị Git bỏ qua.
- Chat `gpt-4o-mini`, embedding `text-embedding-3-small` (1536 chiều), cùng cấu hình cho hai pipeline; `top_k=3`, `chunk_size=800`.
- Toàn bộ 18 tài liệu luật + 20 bài báo nguyên bản: 176 chunks; graph cuối có **202 node / 382 relationship**. Không dùng `LAB_SOLUTION_PACKAGE`, không đưa gold vào prompt.

Hai bảng dưới sao chép nguyên số liệu từ file kết quả:

```text
== Indexing (one-off)
pipeline  calls    in_tok  out_tok       USD  seconds
flat        176     56072        0   0.00112    922.1
graph       196     94958     4802   0.00984   1028.9

== Querying (mean per question)
pipeline  recall  judge   in_tok  out_tok       USD  seconds
flat        0.43   1.00      694       47   0.00013     8.91
graph       1.00   1.83     5436       74   0.00085     8.63
```

| Giai đoạn / chỉ số | Flat | Graph | Graph / Flat |
| --- | ---: | ---: | ---: |
| Indexing: calls | 176 | 196 | 1,11× |
| Indexing: input tokens | 56.072 | 94.958 | 1,69× |
| Indexing: output tokens | 0 | 4.802 | N/A — mẫu số bằng 0 |
| Indexing: USD | 0,00112 | 0,00984 | **8,79×** |
| Indexing: giây | 922,1 | 1.028,9 | 1,12× |
| Mỗi câu: input tokens | 694 | 5.436 | **7,83×** |
| Mỗi câu: output tokens | 47 | 74 | 1,57× |
| Mỗi câu: USD | 0,00013 | 0,00085 | **6,54×** |
| Mỗi câu: giây | 8,91 | 8,63 | 0,97× |

Tỉ lệ dùng các số đã làm tròn trong output. Recall tăng từ 0,43 lên 1,00, judge từ 1,00 lên 1,83; recall là khớp chuỗi trên sáu câu, judge là thang 0/1/2, không phải hai thước đo tương đương.

**Overhead nằm ở đâu?** `build_graph()` dùng regex cho luật nhưng gọi LLM JSON cho từng bài báo: Graph indexing bao gồm vector index chung cộng thêm **20 chat calls, 38.886 input tokens, 4.802 output tokens, 0,00872 USD và 106,8 giây** extraction/build. Đây là chênh lệch Graph − Flat; không cộng chi phí vector index lần thứ hai. Khi trả lời, `GraphRAGAgent.answer()` vẫn lấy top-k chunks như Flat nhưng bổ sung facts từ `Neo4jGraph.context()`, nên input tăng 7,83× và USD tăng 6,54×; output chỉ tăng 1,57×.

**Giới hạn phép đo.** USD dùng bảng giá OpenAI trong `src/llm.py`, không phải hóa đơn YesScale; giá gateway thực tế cần đối chiếu riêng. Judge calls cũng tốn API nhưng không nằm trong usage pipeline ở hai bảng. Indexing chủ yếu mất thời gian ở 176 embedding calls tuần tự qua gateway; toàn lệnh mất khoảng 19 phút, không phải ba phút như ước tính của lab. Query Graph 8,63 giây so với Flat 8,91 giây chỉ là một lần đo với sáu câu; không kết luận graph vốn nhanh hơn, nhất là Q1, Q2 và Q5 Graph chậm hơn từng câu tương ứng.

## 2. Từng câu hỏi Q1–Q6

| Câu / loại | Flat recall / judge | Graph recall / judge | Bên tốt hơn | Bằng chứng và cơ chế |
| --- | --- | --- | --- | --- |
| Q1 — single-hop-law | 1,00 / 2 | 1,00 / 2 | Hòa chất lượng | Cả hai định nghĩa đúng tiền chất. Graph thêm Điều 2 Luật PCMT khoản 4, nhưng một chunk luật đã đủ cho Flat; Graph mất 7,44 s so với 2,16 s. |
| Q2 — single-hop-news | 1,00 / 2 | 1,00 / 2 | Hòa chất lượng | Cả hai nêu Trần Thanh Tuấn và Trần Minh Tâm lãnh án tử hình; đáp án nằm ngay trong một bài báo. Graph không tăng điểm, mất 4,10 s so với 2,85 s. |
| Q3 — cross-kb | 0,00 / 0 | 1,00 / 2 | Graph | Flat trả “Không đủ thông tin.” Graph nối sentence của Lê Minh Thành ở tin qua Crime tới Điều 251 khoản 1: 36 tháng tù, khung 02–07 năm. |
| Q4 — cross-kb | 0,00 / 0 | 1,00 / 2 | Graph | Flat không đủ thông tin. Graph nhận biệt danh Hoàng Nato, lấy Điều 255 khoản 4: mức tối đa tù chung thân, không nói người vừa bị bắt đã nhận án đó. |
| Q5 — cross-kb-multi-hop | 0,60 / 1 | 1,00 / 2 | Graph | Flat có MDMA và khung phạt nhưng viết “khoản b)” và thiếu số điều/khoản. Graph nối vụ Cái Quang Huy với Điều 250 khoản 4, khung 20 năm, tù chung thân hoặc tử hình. |
| Q6 — aggregation | 0,00 / 1 | 1,00 / 1 | Graph về recall; hòa judge | Flat dùng tên ngắn “Đức”, “Thành”, “Đông”. Graph nêu Cái Quang Huy, Lê Minh Thành, Lê Văn Đông nhờ mở các Case liên quan MDMA ngoài top-k; judge vẫn chỉ 1 nên không nhận đáp án hoàn hảo. |

Trích nguyên văn Q3 Graph từ file kết quả:

> Lê Minh Thành bị tuyên 36 tháng tù về tội mua bán trái phép chất ma túy. Tội này được quy định tại Điều 251 của Bộ luật Hình sự, với khung hình phạt cơ bản là từ 02 năm đến 07 năm tù (khoản 1).

Trích nguyên văn Q5 Flat cho thấy căn cứ chưa chính xác dù có phần khung phạt:

> Cái Quang Huy bị truy tố về tội vận chuyển trái phép chất ma túy với loại ma túy là MDMA. Với khối lượng MDMA hơn 9,6kg trong vụ này, khoản b) của điều luật tương ứng được áp dụng, và khung hình phạt là từ 20 năm tù, tù chung thân hoặc tử hình.

Q3–Q5 có recall trung bình Flat **0,20**, Graph **1,00**; judge trung bình Flat **0,33**, Graph **2,00**. Đây là bằng chứng rõ nhất cho cầu nối tin → Crime ← luật. Q1–Q2 hòa nên không có căn cứ nói Graph luôn thắng. Q6 minh họa thêm giới hạn scorer: tên ngắn không khớp keyword và recall cao không bảo đảm judge cao; không tự sửa scorer hoặc gold để làm đẹp bảng.

## 3. Phân tích lỗi trên graph thật

Các truy vấn dưới chạy đọc trên graph đầy đủ sau benchmark, không reset hay dùng fixture. Hai lỗi thuộc **E3 và E6**, có thể kiểm chứng bằng dữ liệu nguồn. Đề xuất là công việc tiếp theo, chưa được triển khai; code sinh benchmark giữ nguyên sau lần đo cuối.

### E3 — Một vụ của Cái Quang Huy thành hai Case

**Hiện tượng.** Cùng vụ vận chuyển hai lần qua Nội Bài xuất hiện hai Case thuộc hai nguồn. Đếm trực tiếp Case của Huy cho kết quả 2 dù nguồn cho thấy chỉ một vụ được nhắc lại. Scope khóa theo tài liệu bảo vệ provenance nhưng không bảo đảm định danh sự kiện thực tế.

**Bằng chứng.** Trong Browser đặt `:param name => 'Cái Quang Huy'`, rồi chạy:

```cypher
MATCH (:Person {name: $name})-[:INVOLVED_IN]->(case_node:Case)
RETURN case_node.name AS case_name, case_node.doc_id AS doc_id
ORDER BY doc_id;
```

| case_name trả về | doc_id |
| --- | --- |
| news-100260917203001265 :: Vụ vận chuyển ma túy từ Đức về Việt Nam | news-100260917203001265 |
| news-100260918080821054 :: Vụ vận chuyển ma túy của Cái Quang Huy | news-100260918080821054 |

`data/drug_news/news-100260917203001265.md:14` và footer `data/drug_news/news-100260918080821054.md:92` chứa cùng đoạn:

> Từ mối quen biết khi cùng làm bếp tại một nhà hàng ở Berlin (Đức), Cái Quang Huy bị cáo buộc hai lần vận chuyển ma túy về Việt Nam qua sân bay Nội Bài. Huy đang bỏ trốn vẫn phải chịu trách nhiệm hình sự tổng số ma túy gồm hơn 9,6kg MDMA và gần 406g Ketamine.

**Nguyên nhân.** Extraction được nhắc không trộn tin liên quan vào vụ chính, nhưng vẫn có thể xuất tin footer thành một Case riêng. `MERGE` theo `doc_id :: caption` cố ý không gộp hai nguồn, nên cùng sự kiện ở footer và bài gốc thành hai node. `UNIQUE` chỉ bảo đảm khóa không trùng, không xử lý identity sự kiện.

**Tác hại đã thấy.** Count vụ của Huy bị đếm trùng, context aggregation mang thêm mô tả nguồn; **không** khẳng định Q6 đã liệt kê Huy hai lần vì đáp án thật đã gộp tên. Tổng 15 Case cũng không thể hiểu là 15 vụ độc lập đã xác minh.

**Đề xuất và đánh đổi.** Tách vùng bài chính/tin liên quan trước extraction, yêu cầu không tạo Case từ footer; về lâu dài thêm ID sự kiện ổn định cùng nhiều nguồn chứng minh. Dự kiến giảm facts trùng và prompt token aggregation, nhưng có thể bỏ thông tin hữu ích hoặc gộp nhầm hai vụ giống nhau; entity resolution thêm chi phí và logic kiểm chứng. Không sửa input `data/` để che lỗi.

### E6 — Charge cá nhân bị rỗng khi người có nhiều tội

**Hiện tượng.** `INVOLVED_IN.charge` của Lê Văn Đông trong bài `news-100260930085028036` rỗng, trong khi nguồn nêu cả tổ chức sử dụng và tàng trữ. Case có đủ hai cầu nối pháp lý nhưng truy vấn context về đúng người không lấy được Điều 249/255.

**Bằng chứng nguồn.** `data/drug_news/news-100260930085028036.md:24` nêu:

> Bị cáo thừa nhận tổ chức sử dụng trái phép chất ma túy tại Sầm Sơn và tàng trữ nhiều loại ma túy bị cơ quan điều tra thu giữ.

Trong Browser đặt `:param name => 'Lê Văn Đông'` và `:param doc_id => 'news-100260930085028036'`, rồi chạy:

```cypher
MATCH (person:Person {name: $name})-[participation:INVOLVED_IN]->
      (case_node:Case {doc_id: $doc_id})
MATCH (case_node)-[:CHARGED_WITH]->(crime:Crime)<-[:DEFINES]-(article:Article)
RETURN person.name AS person, participation.charge AS personal_charge,
       participation.unlinked_charge AS unlinked_charge,
       crime.name AS case_charge, article.id AS article
ORDER BY article;
```

| person | personal_charge | unlinked_charge | case_charge | article |
| --- | --- | --- | --- | --- |
| Lê Văn Đông | chuỗi rỗng | tổ chức sử dụng trái phép chất ma túy, tàng trữ trái phép chất ma túy | tàng trữ trái phép chất ma túy | Điều 249 BLHS |
| Lê Văn Đông | chuỗi rỗng | tổ chức sử dụng trái phép chất ma túy, tàng trữ trái phép chất ma túy | tổ chức sử dụng trái phép chất ma túy | Điều 255 BLHS |

Gọi trực tiếp `graph.context()` qua driver đang kết nối instance lab:

```python
facts = graph.context(
    "Lê Văn Đông bị xét xử về những tội gì, căn cứ điều luật nào?",
    ["news-100260930085028036"],
)
print([fact for fact in facts if "Điều 249" in fact or "Điều 255" in fact])
```

Kết quả: `[]`. Tuy nhiên context vẫn giữ diagnostic có nguồn:

> [news-100260930085028036] Lê Văn Đông trong vụ 'Bệnh nhân ‘tâm thần’ kể cuộc chơi ma túy trên bãi biển cùng điều dưỡng Viện Pháp y tâm thần': role: bị cáo; tội trích xuất chưa nối được với KB luật: tổ chức sử dụng trái phép chất ma túy, tàng trữ trái phép chất ma túy

**Nguyên nhân.** Schema extraction dùng một chuỗi `charge` cho từng người. LLM ghép hai tội đúng vào một chuỗi; `link_entity()` không map chuỗi ghép tới một Crime canonical. Nhánh giữ `unlinked_charge` tránh mất bằng chứng, nhưng bộ lọc legal context chỉ nhận tội cá nhân khớp chính xác nên loại cả hai điều. Không phải thiếu Article trong graph, và không nên sửa bằng cách tự gán mọi tội của Case cho mọi người.

**Đề xuất và đánh đổi.** Dùng danh sách tội cá nhân có cấu trúc, link từng phần độc lập và sửa Cypher kiểm membership thay cho equality. Dự kiến cải thiện recall pháp lý ở người có nhiều tội; phải giữ provenance và test người không bị truy tố/cán bộ. Rủi ro là LLM thêm tội không có trong nguồn, làm sai cáo buộc cá nhân; schema, prompt, test và retrieval đều phức tạp hơn. Sentence rỗng ở phiên tòa đang diễn ra không phải lỗi và không được điền bằng khung luật.

## 4. Kết luận

GraphRAG đáng dùng khi câu hỏi thường xuyên cần nối **người/mức án ở báo → tội → điều/khoản ở luật**, hoặc tổng hợp nhiều vụ ngoài top-k. Trên Q3–Q5, recall tăng 0,20 → 1,00 và judge 0,33 → 2,00, đổi lấy indexing USD 8,79× và querying USD 6,54×. Lợi ích ở đây là căn cứ đầy đủ hơn, không phải tiết kiệm tiền.

Flat RAG đủ tốt khi đáp án nằm trong một chunk luật hoặc một bài báo: Q1–Q2 đều đạt recall 1,00 / judge 2 với prompt nhỏ hơn và latency từng câu thấp hơn. Với khối lượng câu hỏi ít hoặc ít truy vấn xuyên KB, overhead dựng/vận hành Neo4j, extraction và kiểm chứng pháp lý có thể không đáng.

Theo các USD đã làm tròn, nếu dùng chung mô hình chi phí với `N` câu hỏi:

```text
Flat(N)  = 0.00112 + 0.00013 × N
Graph(N) = 0.00984 + 0.00085 × N
```

Graph đắt hơn ở cả one-off và mỗi query, nên **không có điểm hòa vốn về USD với N ≥ 0** trong phép đo này. Các công thức không bao gồm judge, vận hành Docker/Neo4j hoặc giá gateway thực tế. Muốn tối ưu tiếp, nên ưu tiên lọc khoản/facts theo câu hỏi và loại duplicate trước khi tăng số lần gọi LLM; phải đo lại cả recall lẫn chi phí để tránh cắt mất căn cứ.

Hệ thống mạnh hơn nhưng cũng có lỗi identity/provenance, đa tội cá nhân và dao động LLM. Recall 1,00 trên sáu câu không chứng minh mọi trường hợp đúng: E3/E6 và judge Q6 = 1 là các giới hạn đã quan sát. Không dùng output này làm quyết định pháp lý thực tế.

## 5. Tự kiểm

Output thật của unit tests (48 test gốc và 38 test bổ sung, không cần API):

```text
$ .\.venv\Scripts\python.exe -m pytest tests/test_base.py tests/test_graph.py -q
48 passed in 0.10s

$ .\.venv\Scripts\python.exe -m pytest tests/ -q
86 passed, 10 subtests passed in 0.18s

$ .\.venv\Scripts\python.exe -m pip check
No broken requirements found.
```

Output thật của lần `--check` thành công, exit code 0:

```text
[OK] Dữ liệu: 18 điều luật, 20 bài báo
[OK] KG-1 link_entity
[OK] Neo4j kết nối được
[provider] chat = openai:gpt-4o-mini | embedding = openai:text-embedding-3-small
[OK] KG-2 build_graph: 148 node / 293 cạnh, đường xuyên 2 KB dài 2 cạnh
[OK] KG-3 context: 23 dữ kiện, có Điều 251
[OK] KG-4 GraphRAGAgent.answer
[OK] Chi phí check: 1 lần gọi LLM, $0.00082. Graph nhỏ (luật + 1 bài) vẫn còn trong Neo4j để bạn xem; chạy --judge để dựng graph đầy đủ.
```

Đã chạy theo thứ tự **tests → check → full judge → chụp ảnh**. Check tạo graph nhỏ; full benchmark sau đó reset/dựng lại 202 node / 382 cạnh. Không chạy lại check sau benchmark để tránh thay graph ảnh bằng graph nhỏ. Code không đổi sau benchmark; các truy vấn lỗi chỉ đọc. `bench_kg.py`, bộ test gốc, `data/` và base RAG không bị sửa.

| Ảnh thật | Minh chứng |
| --- | --- |
| [`img/kg_count.png`](img/kg_count.png) | 7 label; Clause 99, Person 35, Article 18, Case 15, Substance 15, Crime 13, Location 7. |
| [`img/kg_cross_kb.png`](img/kg_cross_kb.png) | 25 đường Person → Case → Crime ← Article, tab Graph và Results overview: 29 node / 33 cạnh trong kết quả truy vấn. |
| [`img/kg_my_case.png`](img/kg_my_case.png) | Người tự chọn **Cái Quang Huy**, khác Lê Minh Thành: tới Điều 250 BLHS, có MDMA/Ketamine và Hà Nội; Results overview 7 node / 6 cạnh. |

Ba ảnh là capture nguyên cửa sổ Chrome/Neo4j Browser trên graph thật, không crop/chỉnh/render giả. Q-D lọc `participation.charge = crime.name` để tránh gán tội của người khác. Truy vấn tái hiện ảnh và nhóm chẩn đoán ở [`GRAPH_DIAGNOSTICS.md`](GRAPH_DIAGNOSTICS.md).

### Vấn đề gặp phải và phạm vi bàn giao

- Lúc đầu thiếu API key; sau khi người dùng điền riêng `.env`, xác nhận model/gateway và ngân sách thì build/check/judge đều chạy thành công. Không thay benchmark live bằng fixture.
- Gateway embedding chậm; giữ nguyên runner/cấu hình hai pipeline để phép so sánh công bằng, không sửa bảng giá hay output.
- `.env`/`.venv` không thuộc bài nộp. Người chạy lại cần tự cấu hình key, endpoint và Neo4j; không phụ thuộc credential hay graph còn sót của máy này.
- Rà soát cuối: `git diff --check` pass; file được track, output/ảnh mới và toàn bộ lịch sử Git không khớp key hiện tại hay các mẫu token/private key phổ biến. `.env`/`.venv` bị ignore và không được track. Scan theo mẫu không bảo đảm nhận diện mọi loại bí mật.
- Không triển khai bonus ontology mới; không tạo benchmark HINT giả hoặc nhận +15 khi chưa có so sánh trước/sau.
- Repo bài làm: https://github.com/Neon310304/K4-DAY19-TranQuocVuong-2A202602522. Người dùng đã yêu cầu commit/push bản hoàn chỉnh; việc nộp link VLearn chưa được xác nhận.

### Checklist có bằng chứng

- [x] KG-1 đến KG-4 hoàn thiện; không còn entry point bắt buộc ném `NotImplementedError`.
- [x] 48 test gốc và 38 test bổ sung pass; base không bị sửa.
- [x] Live check đủ 7 `[OK]`; full judge sinh file đủ 3 phần và 12 đáp án có điểm thật.
- [x] Ontology đủ 8 mục, có bridge/provenance/đường đi Q1–Q6, khớp graph cuối.
- [x] Báo cáo có hai bảng chi phí, từng câu, E3/E6 có nguồn và Cypher, kết luận và tự kiểm.
- [x] Ba ảnh Neo4j Browser thật đúng tên file, thấy query và kết quả.
- [ ] Bonus ontology riêng — không chọn thực hiện.
- [ ] Xác nhận link đã nộp trên VLearn — người dùng thực hiện.
