# Truy vấn ảnh và chẩn đoán GraphRAG

**Trạng thái:** Chưa phải minh chứng đã chạy benchmark. Graph lưu bền vững hiện có 0 node do thiếu cấu hình API; chưa thể chụp ba ảnh hợp lệ hoặc kết luận hai lỗi E1–E6. Các truy vấn này dùng ontology HINT đang được triển khai trong `src/graph.py`.

## 1. Điều kiện trước khi chụp

1. Lưu key trực tiếp trong `.env`, không gửi key qua chat hoặc đưa vào Git.
2. Với gateway tương thích OpenAI như YesScale, dùng `OPENAI_API_KEY`, `LLM_PROVIDER=openai`, `OPENAI_BASE_URL` đúng API endpoint và `OPENAI_CHAT_MODEL` hợp lệ. Không đặt `LLM_PROVIDER=yescale` vì repo không có provider mang tên này.
3. Benchmark cần embedding thật: đặt `OPENAI_EMBEDDING_MODEL` nếu gateway hỗ trợ `/embeddings`, hoặc chọn OpenRouter/Gemini bằng `EMBEDDING_PROVIDER` cùng key/model tương ứng. Không thay bằng mock embedding để nộp benchmark.
4. Xác nhận ngân sách theo giá provider thực tế. USD trong runner là ước tính theo bảng giá cục bộ, không phải hóa đơn YesScale; model chưa có giá có thể hiển thị 0 dù API có thu phí.
5. Chỉ dùng instance Neo4j dành riêng cho lab: runner reset toàn bộ node, relationship và constraint. Không chạy trên database dùng chung hoặc có dữ liệu cần giữ.
6. Chạy test/check rồi chạy full `python bench_kg.py --judge`. `--check` và `--build --limit 2` để lại graph nhỏ, không dùng graph đó làm ảnh full benchmark.

Chỉ tiếp tục khi file `ket_qua_benchmark_kg.txt` được sinh từ code cuối, có Indexing/Querying/Per question và đủ 12 câu trả lời với điểm judge thật.

## 2. Ba ảnh Neo4j Browser

Mở `http://localhost:7474`. Trước mỗi truy vấn ảnh, gõ `:clear`, rồi chạy riêng truy vấn cần chụp. Chụp cả cửa sổ trình duyệt, nhìn rõ ô query và kết quả; ảnh Graph phải thấy Results overview. Không crop/chỉnh ảnh, không dùng ảnh mẫu có watermark hoặc fixture test đã rollback.

### Q-A → `report/img/kg_count.png`

```cypher
MATCH (node)
RETURN labels(node)[0] AS label, count(*) AS node_count
ORDER BY node_count DESC;
```

Kiểm tra đủ label của ontology. Article phải có 18 node cho corpus đầy đủ; số node trích từ báo phụ thuộc kết quả LLM, không ép giống ảnh mẫu. Graph 0 node không đạt yêu cầu ảnh.

### Q-B → `report/img/kg_cross_kb.png`

```cypher
MATCH path=(:Person)-[:INVOLVED_IN]->(:Case)-[:CHARGED_WITH]->(:Crime)<-[:DEFINES]-(:Article)
RETURN path LIMIT 25;
```

Ảnh Graph cần thấy Person, Case, Crime, Article và các quan hệ nối chúng. Kết quả có đường đi chưa đủ chứng minh mọi người đều bị kết án theo mọi tội của vụ; charge cá nhân được lưu trên INVOLVED_IN.

### Chọn người khác Lê Minh Thành cho Q-D

```cypher
MATCH (person:Person)-[participation:INVOLVED_IN]->(case_node:Case)
      -[:CHARGED_WITH]->(crime:Crime)<-[:DEFINES]-(article:Article)
WHERE person.name <> 'Lê Minh Thành' AND participation.charge = crime.name
RETURN DISTINCT person.name AS name, person.aliases AS aliases, article.id AS article
ORDER BY name;
```

Chọn người thực sự có node và đọc lại bài gốc. Không chọn một biến thể tên của Lê Minh Thành để lách yêu cầu. Ghi tên người đã chọn vào `report/REPORT_KG.md`; hiện chưa có lựa chọn được xác minh.

### Q-D → `report/img/kg_my_case.png`

Trong Browser, đặt parameter bằng `:param person_name => 'họ tên đã chọn'`, sau đó `:clear` và chạy:

```cypher
MATCH path=(person:Person {name: $person_name})-[participation:INVOLVED_IN]->(case_node:Case)
           -[:CHARGED_WITH]->(crime:Crime)<-[:DEFINES]-(article:Article)
WHERE participation.charge = crime.name
OPTIONAL MATCH details=(case_node)-[:INVOLVES|LOCATED_IN]->()
RETURN path, details;
```

Điều kiện charge tránh gán tội của người khác trong cùng Case cho người được chọn. Ảnh cần thấy đường người → vụ → tội → điều luật, cùng chất/địa điểm khi có.

## 3. Soi E1–E6 và lưu bằng chứng

### E1 — Vụ không nối tới luật

```cypher
MATCH (case_node:Case)
WHERE NOT EXISTS {
    MATCH (case_node)-[:CHARGED_WITH]->(:Crime)<-[:DEFINES]-(:Article)
}
RETURN case_node.name AS case_name, case_node.doc_id AS doc_id, case_node.summary AS summary;
```

Với mỗi dòng, mở bài theo doc_id: nếu nguồn thực sự có tội thuộc KB mà không link thì mới là lỗi. Vụ ngoài phạm vi luật hoặc bài không đủ căn cứ pháp lý không được tự coi là cầu nối gãy. Graph chưa nạp không phải bằng chứng E1.

### E2 — Graph có khoản nhưng context/answer thiếu

Dùng cùng parameter person_name của vụ cần phân tích:

```cypher
MATCH (person:Person {name: $person_name})-[participation:INVOLVED_IN]->(case_node:Case)
      -[:CHARGED_WITH]->(crime:Crime)<-[:DEFINES]-(article:Article)-[:HAS_CLAUSE]->(clause:Clause)
WHERE participation.charge = crime.name
RETURN person.name AS person, article.id AS article, clause.number AS clause,
       clause.penalty AS penalty, clause.text AS text
ORDER BY article, clause;
```

Đối chiếu các khoản ở đây với `graph.context(question, doc_ids)` và câu trả lời nguyên văn trong benchmark. Thiếu căn cứ tối đa, lọc chỉ theo chất hoặc cắt max_facts quá sớm là giả thuyết cần kiểm chứng, không phải lỗi đã quan sát sẵn.

### E3 — Trùng entity

```cypher
MATCH (substance:Substance)
RETURN substance.name AS name
ORDER BY toLower(name);
```

```cypher
MATCH (person:Person)
RETURN person.name AS name, person.aliases AS aliases
ORDER BY toLower(name);
```

```cypher
MATCH (case_node:Case)
RETURN case_node.name AS name, case_node.doc_id AS doc_id, case_node.source_title AS source_title
ORDER BY source_title, doc_id;
```

Chứng minh hai node chỉ cùng một thực thể/vụ bằng nguồn, không chỉ vì tên giống nhau. Case được scope theo tài liệu có chủ đích để giữ provenance; cần chỉ ra tác hại cụ thể như đếm trùng hoặc trả danh sách vụ trùng, không mặc định mọi bản tin cùng vụ là lỗi.

### E4 — Recall và judge mâu thuẫn

Không suy từ điểm trung bình. Đọc đủ 12 câu trả lời ở Per question; với mỗi Q1–Q6, đối chiếu nguyên văn đáp án, các chuỗi must_include và judge 0/1/2. Chỉ rõ chuỗi nào không khớp hoặc câu nào judge đánh giá sai. Recall 0–1 và judge 0–2 khác thang, không gọi hai số khác nhau là lỗi khi chưa đọc nội dung.

### E5 — Câu trả lời aggregation lệch graph

```cypher
MATCH (case_node:Case)-[involvement:INVOLVES]->(:Substance {name: 'MDMA'})
OPTIONAL MATCH (person:Person)-[:INVOLVED_IN]->(case_node)
RETURN case_node.doc_id AS doc_id, case_node.source_title AS source_title,
       case_node.summary AS summary, involvement.amount AS amount,
       collect(DISTINCT person.name) AS people
ORDER BY doc_id;
```

So với Q6 GraphRAG: ghi nguồn/người/vụ bị bỏ hoặc bị thêm, rồi kiểm tra context để phân biệt lỗi retrieval với lỗi LLM. Kết quả Cypher ở cấp nguồn chưa tự động là số vụ thực tế duy nhất.

### E6 — Property rỗng

```cypher
MATCH (person:Person)-[participation:INVOLVED_IN]->(case_node:Case)
WHERE coalesce(participation.charge, '') = '' OR coalesce(participation.role, '') = ''
RETURN person.name AS person, participation.role AS role, participation.charge AS charge,
       participation.sentence AS sentence, case_node.doc_id AS doc_id,
       case_node.summary AS summary
ORDER BY doc_id, person;
```

Mở nguồn để phân biệt thiếu hợp lý với lỗi extraction. Cán bộ/người liên quan không nhất thiết có charge; người bị bắt hoặc đang truy tố không nhất thiết có sentence. Không tự điền khung án luật vào sentence để làm hết ô rỗng.

## 4. Mẫu ghi nhận mỗi lỗi

Chọn ít nhất hai nhóm lỗi khác nhau, chỉ sau khi có quan sát thật. Ghi vào mục 3 `report/REPORT_KG.md`:

1. **Hiện tượng:** Q nào, pipeline nào hoặc entity/property nào sai.
2. **Bằng chứng:** trích nguyên văn câu trả lời hoặc Cypher kèm các dòng kết quả và doc_id; không sửa lời đáp cho khớp nhận định.
3. **Nguyên nhân:** bước extraction/linking/ontology/retrieval/prompt/scorer nào gây lỗi, và cách loại trừ nguyên nhân khác.
4. **Đề xuất sửa:** sửa gì, ở đâu; tác động dự kiến đến recall/token/latency và rủi ro mới.

Rủi ro từ đọc code hoặc kết quả fixture giả lập chỉ là giả thuyết. Không dùng chúng thay hai lỗi trên graph/benchmark thật và không làm hỏng code để tạo minh chứng.
