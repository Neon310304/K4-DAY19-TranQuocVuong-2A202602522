"""Knowledge Graph (Neo4j) + GraphRAG over two drug-topic knowledge bases.

Contract (fixed — bench_kg.py and the tests rely on it):
    link_entity(name, known)                       -> one of `known` or None          (KG-1)
    build_graph(graph, law_docs, news_docs, llm_fn)   load both KBs into Neo4j      (KG-2)
        every node created from ONE document carries the property `doc_id`
    Neo4jGraph.context(question, doc_ids)         -> list[str] facts               (KG-3)
    GraphRAGAgent.answer(question, top_k)         -> str                           (KG-4)

Everything else in this file is a HINT: one possible ontology (below). Use it as is, change it,
or design your own — your own ontology + report/ONTOLOGY.md earns the bonus (see SUBMISSION.md).

Suggested ontology (Crime is the bridge between the law KB and the news KB):

    (:Article {id, title, law, doc_id})-[:DEFINES]->(:Crime {name})
    (:Article)-[:HAS_CLAUSE]->(:Clause {id, number, penalty, text})-[:MENTIONS]->(:Substance {name})
    (:Case {name, summary, date, doc_id})-[:CHARGED_WITH]->(:Crime)
    (:Case)-[:INVOLVES {amount}]->(:Substance)
    (:Case)-[:LOCATED_IN]->(:Location {name})
    (:Person {name, aliases})-[:INVOLVED_IN {role, sentence, charge}]->(:Case)
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable

from .models import Document
from .store import EmbeddingStore

# Canonical substance names: the ones BLHS Chương XX lists, plus common ones in Vietnamese news.
SUBSTANCES = ["Heroine", "Cocaine", "Methamphetamine", "Amphetamine", "MDMA", "XLR-11", "Ketamine",
              "cần sa", "thuốc phiện", "côca"]
CLAUSE_START = re.compile(r"^(\d+)\.\s", re.MULTILINE)
FOOTNOTE = re.compile(r"\[\d+\]")

def load_markdown_docs(folder: str | Path) -> list[Document]:
    """Read crawler output (.md with a flat `key: "value"` front matter) into Documents."""
    docs = []
    for path in sorted(Path(folder).glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        _, front, body = raw.split("---", 2)
        metadata = {k: json.loads(v) for k, v in re.findall(r'^(\w+): (".*")$', front, re.MULTILINE)}
        docs.append(Document(id=metadata.get("doc_id", path.stem), content=body.strip(), metadata=metadata))
    return docs

def normalize_crime(name: str) -> str:
    """'Tội Mua bán trái phép chất ma túy' -> 'mua bán trái phép chất ma túy'."""
    name = re.sub(r"\s+", " ", name.strip().strip("\"'“”").lower())
    return name.removeprefix("tội ").strip()

def link_entity(name: str, known: list[str], normalize: Callable[[str], str] = normalize_crime) -> str | None:
    """Map a free-text mention (e.g. a charge written by a journalist) onto one canonical name in `known`."""
    if not name or not known:
        return None
    normalized_name = normalize(name)
    if not normalized_name:
        return None
    canonical_names = {}
    for original_name in known:
        normalized_known = normalize(original_name)
        if normalized_known:
            canonical_names.setdefault(normalized_known, original_name)
    if normalized_name in canonical_names:
        return canonical_names[normalized_name]
    matches = difflib.get_close_matches(normalized_name, canonical_names, n=1, cutoff=0.8)
    return canonical_names[matches[0]] if matches else None

def find_substances(text: str) -> list[str]:
    lowered = text.lower()
    return [name for name in SUBSTANCES if name.lower() in lowered]

# ----------------------------------------------------------------------------------------------
# HINT — suggested ontology: extraction helpers
# ----------------------------------------------------------------------------------------------

def parse_law_article(doc: Document) -> dict[str, Any]:
    """Deterministic (regex) extraction for one 'Điều' — law text is regular enough to skip the LLM."""
    article_id = doc.metadata["article"]                       # "Điều 251 BLHS"
    title = doc.metadata["title"].split(". ", 1)[-1]           # "Tội mua bán trái phép chất ma túy"
    body = FOOTNOTE.sub("", doc.content)
    starts = list(CLAUSE_START.finditer(body))
    clauses = []
    for index, start in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(body)
        text = body[start.start():end].strip()
        first_line = text.splitlines()[0]
        penalty = re.search(r"\bbị ((?:phạt|tù|cảnh cáo).+?)(?::|$)", first_line)
        clauses.append({
            "id": f"{article_id} khoản {start.group(1)}",
            "number": int(start.group(1)),
            "penalty": penalty.group(1).rstrip(".") if penalty else "",
            "text": text,
            "substances": find_substances(text),
        })
    return {
        "id": article_id,
        "law": doc.metadata.get("law", ""),
        "title": title,
        "doc_id": doc.id,
        "crime": normalize_crime(title) if title.startswith("Tội ") else None,
        "clauses": clauses,
    }

NEWS_EXTRACTION_PROMPT = """Bạn trích xuất knowledge graph từ một bài báo tiếng Việt về ma túy.
Chỉ dùng thông tin có trong bài. Trả về JSON đúng dạng:
{{"cases": [{{
  "name": "tên ngắn của vụ việc, ví dụ: Vụ mua bán 36kg ma túy tại TP.HCM",
  "summary": "1-2 câu tóm tắt",
  "date": "ngày xảy ra/xét xử nếu có, dạng YYYY-MM-DD hoặc chuỗi rỗng",
  "location": "tỉnh/thành phố, chuỗi rỗng nếu không rõ",
  "charges": ["tội danh trong bài, dùng nguyên văn từ DANH SÁCH TỘI DANH nếu khớp"],
  "substances": [{{"name": "tên chất, dùng tên chuẩn trong DANH SÁCH CHẤT nếu khớp", "amount": "khối lượng nếu có"}}],
  "people": [{{"name": "họ tên", "aliases": ["biệt danh"], "role": "bị cáo|bị can|nghi phạm|người liên quan|cán bộ",
               "charge": "tội danh của người này trong bài, dùng tên chuẩn nếu khớp, hoặc chuỗi rỗng",
               "sentence": "mức án nếu có, ví dụ: tử hình, 8 năm tù"}}]
}}]}}
Bài không nói về vụ việc cụ thể (tuyên truyền, hội nghị...) thì trả về {{"cases": []}}.
Tội chưa có trong danh sách thì giữ tên trong bài, không đổi thành một tội khác để ép khớp.
Không gộp đoạn giới thiệu tin liên quan ở cuối bài vào vụ chính.
Giữ lượng chịu trách nhiệm của từng người trong summary nếu nguồn phân biệt.
Chỉ ghi sentence khi nguồn nêu mức án đã tuyên; không suy từ khung luật.
Phân biệt bị bắt, bị truy tố, đã bị kết án và bị hủy quyết định khởi tố.
Không gán tội của cả vụ cho người chỉ được nhắc tới hoặc đã được hủy khởi tố.
Không tự coi biệt ngữ như "kẹo", "thuốc lắc" là MDMA nếu nguồn chưa xác định chất.

DANH SÁCH TỘI DANH: {crimes}
DANH SÁCH CHẤT: {substances}

Tiêu đề: {title}
Nội dung:
{content}"""

def extract_news_cases(doc: Document, llm_fn: Callable[[str], str], known_crimes: list[str]) -> list[dict]:
    """LLM extraction for one news article; charges are re-linked to law-KB crimes in code."""
    def text_value(value: Any, field: str) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError(f"{doc.id}: {field} phải là chuỗi")
        return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value)).strip()

    def list_value(record: dict, field: str) -> list:
        value = record.get(field, [])
        if not isinstance(value, list):
            raise ValueError(f"{doc.id}: {field} phải là danh sách")
        return value

    prompt = NEWS_EXTRACTION_PROMPT.format(
        crimes="; ".join(known_crimes), substances=", ".join(SUBSTANCES),
        title=doc.metadata.get("title", ""), content=doc.content[:12000],
    )
    try:
        payload = json.loads(llm_fn(prompt))
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError(f"{doc.id}: LLM không trả JSON hợp lệ") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError(f"{doc.id}: JSON phải có trường cases dạng danh sách")

    canonical_substances = {substance.casefold(): substance for substance in SUBSTANCES}
    cases = []
    for raw_case in payload["cases"]:
        if not isinstance(raw_case, dict):
            raise ValueError(f"{doc.id}: mỗi case phải là object")
        case = {field: text_value(raw_case.get(field), field)
                for field in ("name", "summary", "date", "location")}
        charges = []
        unlinked_charges = []
        for raw_charge in list_value(raw_case, "charges"):
            charge_text = text_value(raw_charge, "charges")
            charge = link_entity(charge_text, known_crimes)
            if charge:
                charges.append(charge)
            elif charge_text:
                unlinked_charges.append(charge_text)
        case["charges"] = sorted(set(charges))
        case["unlinked_charges"] = list(dict.fromkeys(unlinked_charges))

        people = []
        for raw_person in list_value(raw_case, "people"):
            if not isinstance(raw_person, dict):
                raise ValueError(f"{doc.id}: mỗi person phải là object")
            person = {field: text_value(raw_person.get(field), field)
                      for field in ("name", "role", "sentence", "charge")}
            charge_text = person["charge"]
            person["charge"] = link_entity(charge_text, known_crimes) or ""
            person["unlinked_charge"] = charge_text if not person["charge"] else ""
            aliases = [text_value(alias, "aliases") for alias in list_value(raw_person, "aliases")]
            person["aliases"] = list(dict.fromkeys(alias for alias in aliases if alias))
            if person["name"]:
                people.append(person)
        case["people"] = people

        substances = []
        for raw_substance in list_value(raw_case, "substances"):
            if not isinstance(raw_substance, dict):
                raise ValueError(f"{doc.id}: mỗi substance phải là object")
            substance = {field: text_value(raw_substance.get(field), field)
                         for field in ("name", "amount")}
            substance["name"] = canonical_substances.get(substance["name"].casefold(), substance["name"])
            if substance["name"]:
                substances.append(substance)
        case["substances"] = substances
        cases.append(case)
    return cases

# ----------------------------------------------------------------------------------------------
# Neo4j
# ----------------------------------------------------------------------------------------------

class Neo4jGraph:
    """Thin wrapper over the official neo4j driver."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        from neo4j import GraphDatabase

        self.driver = GraphDatabase.driver(uri, auth=(user, password), notifications_min_severity="OFF")
        self.driver.verify_connectivity()

    def close(self) -> None:
        self.driver.close()

    def run(self, cypher: str, **params: Any) -> list[dict]:
        records, _, _ = self.driver.execute_query(cypher, params)
        return [record.data() for record in records]

    def reset(self) -> None:
        """Delete every node, relationship and constraint (bench_kg.py calls this before build_graph)."""
        self.run("MATCH (n) DETACH DELETE n")
        for row in self.run("SHOW CONSTRAINTS YIELD name RETURN name"):
            self.run(f"DROP CONSTRAINT `{row['name']}` IF EXISTS")

    def stats(self) -> dict[str, int]:
        nodes = self.run("MATCH (n) RETURN count(n) AS n")[0]["n"]
        rels = self.run("MATCH ()-[r]->() RETURN count(r) AS n")[0]["n"]
        return {"nodes": nodes, "relationships": rels}

    def seed_facts(self, question: str, doc_ids: list[str], skip_labels: tuple[str, ...] = (),
                   limit: int = 60) -> tuple[list[str], list[str]]:
        """Ontology-independent first step: seed nodes + their 1-hop edges as text facts.

        Seeds = nodes whose `doc_id` is in doc_ids, or whose `name`/`aliases` appear in the question.
        Returns (seed elementIds, facts). Nodes with a label in skip_labels are left out of the facts.
        """
        seeds = self.run(
            """
            MATCH (n)
            WHERE n.doc_id IN $doc_ids
               OR (n.name IS :: STRING AND size(n.name) >= 3 AND toLower($q) CONTAINS toLower(n.name))
               OR any(a IN coalesce(n.aliases, []) WHERE size(a) >= 3 AND toLower($q) CONTAINS toLower(a))
            RETURN elementId(n) AS id
            """,
            q=question, doc_ids=doc_ids,
        )
        seed_ids = [row["id"] for row in seeds]
        edges = self.run(
            """
            MATCH (s)-[r]-(m)
            WHERE elementId(s) IN $ids
              AND none(l IN labels(s) + labels(m) WHERE l IN $skip)
            WITH DISTINCT r LIMIT $limit
            WITH startNode(r) AS a, r, endNode(r) AS b
            RETURN labels(a)[0] AS a_label, coalesce(a.name, a.id) AS a_name, type(r) AS rel,
                   properties(r) AS props, labels(b)[0] AS b_label, coalesce(b.name, b.id) AS b_name
            """,
            ids=seed_ids, skip=list(skip_labels), limit=limit,
        )
        facts = []
        for e in edges:
            props = ", ".join(f"{k}: {v}" for k, v in e["props"].items() if v)
            facts.append(f"({e['a_label']}: {e['a_name']}) -[{e['rel']}{' {' + props + '}' if props else ''}]-> "
                         f"({e['b_label']}: {e['b_name']})")
        return seed_ids, facts

    # ---------------------------------------------------------------- HINT — suggested ontology: writes

    def suggested_constraints(self) -> None:
        for label, key in [("Article", "id"), ("Clause", "id"), ("Crime", "name"), ("Case", "name"),
                           ("Substance", "name"), ("Person", "name"), ("Location", "name")]:
            self.run(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.{key} IS UNIQUE")

    def add_law_article(self, article: dict) -> None:
        self.run(
            """
            MERGE (a:Article {id: $id}) SET a.title = $title, a.law = $law, a.doc_id = $doc_id
            FOREACH (crime IN CASE WHEN $crime IS NULL THEN [] ELSE [$crime] END |
                MERGE (c:Crime {name: crime}) MERGE (a)-[:DEFINES]->(c))
            WITH a
            UNWIND $clauses AS clause
            MERGE (cl:Clause {id: clause.id})
              SET cl.number = clause.number, cl.penalty = clause.penalty, cl.text = clause.text, cl.doc_id = $doc_id
            MERGE (a)-[:HAS_CLAUSE]->(cl)
            FOREACH (s IN clause.substances | MERGE (sub:Substance {name: s}) MERGE (cl)-[:MENTIONS]->(sub))
            """,
            **article,
        )

    def add_news_case(self, case: dict, doc: Document) -> None:
        self.run(
            """
            MERGE (k:Case {name: $name})
              SET k.summary = $summary, k.date = $date, k.doc_id = $doc_id, k.source_title = $title
              SET k.unlinked_charges = $unlinked_charges
            FOREACH (loc IN CASE WHEN $location = '' THEN [] ELSE [$location] END |
                MERGE (l:Location {name: loc}) MERGE (k)-[:LOCATED_IN]->(l))
            FOREACH (crime IN $charges | MERGE (c:Crime {name: crime}) MERGE (k)-[:CHARGED_WITH]->(c))
            FOREACH (s IN $substances | MERGE (sub:Substance {name: s.name}) MERGE (k)-[r:INVOLVES]->(sub)
                SET r.amount = s.amount)
            FOREACH (person_data IN $people | MERGE (person:Person {name: person_data.name})
                SET person.aliases = reduce(aliases = coalesce(person.aliases, []),
                    alias IN coalesce(person_data.aliases, []) |
                    CASE WHEN alias IN aliases THEN aliases ELSE aliases + [alias] END)
                MERGE (person)-[participation:INVOLVED_IN]->(k)
                  SET participation.role = person_data.role, participation.charge = person_data.charge,
                      participation.sentence = person_data.sentence,
                      participation.unlinked_charge = coalesce(person_data.unlinked_charge, ''))
            """,
            name=case.get("name") or doc.metadata.get("title", doc.id),
            summary=case.get("summary", ""), date=case.get("date", ""), location=case.get("location", ""),
            charges=case.get("charges", []), people=[p for p in case.get("people", []) if p.get("name")],
            unlinked_charges=case.get("unlinked_charges", []),
            substances=[s for s in case.get("substances", []) if s.get("name")],
            doc_id=doc.id, title=doc.metadata.get("title", ""),
        )

    # ---------------------------------------------------------------- KG-3

    def context(self, question: str, doc_ids: list[str], max_facts: int = 60) -> list[str]:
        """Bounded facts from the Crime bridge, or global case aggregation by substance."""
        if max_facts <= 0:
            return []
        seed_ids, seed_edges = self.seed_facts(question, doc_ids)
        lowered = question.lower()
        substances = find_substances(question)
        aggregate = bool(substances) and bool(re.search(r"(?:những|các)\s+vụ|vụ\s+(?:việc|án)\s+nào", lowered))
        maximum = any(term in lowered for term in ("tối đa", "cao nhất", "nặng nhất"))
        article_numbers = re.findall(r"[Đđ]iều\s+(\d+)", question)
        clause_numbers = [int(number) for number in re.findall(r"[Kk]hoản\s+(\d+)", question)]
        law_filter = ""
        if "blhs" in lowered or "bộ luật hình sự" in lowered:
            law_filter = "BLHS"
        elif "luật pcmt" in lowered or "phòng, chống ma túy" in lowered:
            law_filter = "Luật PCMT"

        cases = self.run(
            """
            MATCH (case_node:Case)
            WHERE (($aggregate AND EXISTS {
                MATCH (case_node)-[:INVOLVES]->(substance:Substance)
                WHERE substance.name IN $substances
            }) OR (NOT $aggregate AND (elementId(case_node) IN $ids OR EXISTS {
                MATCH (seed)--(case_node) WHERE elementId(seed) IN $ids
            }))) AND ($aggregate OR NOT EXISTS {
                MATCH (named_person:Person) WHERE elementId(named_person) IN $ids
            } OR EXISTS {
                MATCH (named_person:Person)-[:INVOLVED_IN]->(case_node)
                WHERE elementId(named_person) IN $ids
            })
            OPTIONAL MATCH (person:Person)-[participation:INVOLVED_IN]->(case_node)
            WITH case_node, collect({name: person.name, aliases: person.aliases,
                role: participation.role, sentence: participation.sentence, charge: participation.charge,
                unlinked_charge: participation.unlinked_charge,
                focused: elementId(person) IN $ids}) AS people,
                max(CASE WHEN elementId(person) IN $ids THEN 1 ELSE 0 END) AS focus
            OPTIONAL MATCH (case_node)-[involvement:INVOLVES]->(case_substance:Substance)
            WITH case_node, people, focus,
                collect({name: case_substance.name, amount: involvement.amount}) AS substances
            RETURN elementId(case_node) AS id, case_node.name AS name, case_node.summary AS summary,
                case_node.doc_id AS doc_id, case_node.source_title AS source_title,
                coalesce(case_node.unlinked_charges, []) AS unlinked_charges, people, substances
            ORDER BY focus DESC, doc_id, name
            """,
            ids=seed_ids, aggregate=aggregate, substances=substances,
        ) if seed_ids or aggregate else []
        case_ids = [case["id"] for case in cases]
        legal_rows = []
        if case_ids and not aggregate:
            legal_rows.extend(self.run(
                """
                MATCH (case_node:Case)-[:CHARGED_WITH]->(crime:Crime)<-[:DEFINES]-(article:Article)
                    -[:HAS_CLAUSE]->(clause:Clause)
                WHERE elementId(case_node) IN $case_ids
                  AND (NOT EXISTS {
                      MATCH (named_person:Person)-[:INVOLVED_IN]->(case_node)
                      WHERE elementId(named_person) IN $ids
                  } OR EXISTS {
                      MATCH (named_person:Person)-[participation:INVOLVED_IN]->(case_node)
                      WHERE elementId(named_person) IN $ids AND participation.charge = crime.name
                  })
                  AND ($maximum OR clause.number = 1 OR clause.number IN $clause_numbers OR EXISTS {
                      MATCH (case_node)-[:INVOLVES]->(:Substance)<-[:MENTIONS]-(clause)
                  })
                RETURN DISTINCT article.id AS article_id, article.title AS title, article.doc_id AS doc_id,
                    clause.number AS number, clause.penalty AS penalty, clause.text AS text,
                    CASE WHEN $maximum AND (clause.penalty CONTAINS 'chung thân'
                        OR clause.penalty CONTAINS 'tử hình') THEN 0
                        WHEN clause.number = 1 THEN 1 ELSE 2 END AS priority
                ORDER BY priority, article_id, number
                """,
                case_ids=case_ids, ids=seed_ids, maximum=maximum, clause_numbers=clause_numbers,
            ))
        if not aggregate and (seed_ids or article_numbers):
            legal_rows.extend(self.run(
                """
                MATCH (article:Article)-[:HAS_CLAUSE]->(clause:Clause)
                WHERE (elementId(article) IN $ids OR EXISTS {
                    MATCH (article)-[:HAS_CLAUSE]->(seed_clause:Clause)
                    WHERE elementId(seed_clause) IN $ids
                } OR any(number IN $article_numbers WHERE article.id STARTS WITH 'Điều ' + number + ' '))
                  AND ($law_filter = '' OR article.law = $law_filter)
                  AND ($maximum OR clause.number = 1 OR clause.number IN $clause_numbers
                    OR NOT EXISTS { MATCH (article)-[:DEFINES]->(:Crime) }
                    OR EXISTS {
                        MATCH (clause)-[:MENTIONS]->(substance:Substance)
                        WHERE substance.name IN $substances
                    })
                RETURN DISTINCT article.id AS article_id, article.title AS title, article.doc_id AS doc_id,
                    clause.number AS number, clause.penalty AS penalty, clause.text AS text,
                    CASE WHEN $maximum AND (clause.penalty CONTAINS 'chung thân'
                        OR clause.penalty CONTAINS 'tử hình') THEN 0
                        WHEN clause.number = 1 THEN 1 ELSE 2 END AS priority
                ORDER BY priority, article_id, number
                """,
                ids=seed_ids, article_numbers=article_numbers, clause_numbers=clause_numbers,
                substances=substances, maximum=maximum, law_filter=law_filter,
            ))
        facts = []
        for clause in legal_rows:
            text = clause.get("text") or clause.get("penalty")
            if text:
                facts.append(f"[{clause['article_id']} - {clause['title']}; nguồn: {clause['doc_id']}] "
                             f"khoản {clause['number']}: {text}")
        people_facts = []
        substance_facts = []
        for case in cases:
            source = case.get("doc_id") or case["name"]
            title = case.get("source_title") or case["name"]
            if case.get("summary"):
                facts.append(f"[{source}] Vụ việc '{title}': {case['summary']}")
            if case.get("unlinked_charges"):
                facts.append(f"[{source}] Vụ '{title}': tội trích xuất chưa nối được với KB luật: "
                             + "; ".join(case["unlinked_charges"]))
            for substance in sorted((substance for substance in case.get("substances", []) if substance.get("name")),
                                    key=lambda substance: substance["name"]):
                amount = f"; lượng theo nguồn: {substance['amount']}" if substance.get("amount") else ""
                substance_facts.append(f"[{source}] Vụ '{title}' liên quan chất {substance['name']}{amount}")
            people = sorted((person for person in case.get("people", []) if person.get("name")),
                            key=lambda person: (not person.get("focused"), person["name"]))
            for person in people:
                details = [f"{field}: {person[field]}" for field in ("role", "charge", "sentence")
                           if person.get(field)]
                if person.get("unlinked_charge"):
                    details.append("tội trích xuất chưa nối được với KB luật: " + person["unlinked_charge"])
                if person.get("aliases"):
                    details.append("biệt danh: " + ", ".join(person["aliases"]))
                people_facts.append(f"[{source}] {person['name']} trong vụ '{title}': " + "; ".join(details))
        edges = [] if aggregate else sorted(seed_edges)
        return list(dict.fromkeys(facts + substance_facts + people_facts + edges))[:max_facts]

# ---------------------------------------------------------------------------------------------- KG-2

def build_graph(graph: Neo4jGraph, law_docs: list[Document], news_docs: list[Document],
                llm_fn: Callable[..., str]) -> None:
    """Load both KBs into an empty graph. llm_fn(prompt, json_mode=False) -> str (metered OpenAI chat)."""
    def json_llm(prompt: str) -> str:
        return llm_fn(prompt, json_mode=True)

    articles = [parse_law_article(doc) for doc in law_docs]
    known_crimes = list(dict.fromkeys(article["crime"] for article in articles if article["crime"]))
    graph.suggested_constraints()
    for article in articles:
        graph.add_law_article(article)
    for doc in news_docs:
        for case in extract_news_cases(doc, json_llm, known_crimes):
            caption = case["name"] or doc.metadata.get("title") or doc.id
            caption = re.sub(r"\s+", " ", unicodedata.normalize("NFC", caption)).strip()
            case["name"] = f"{doc.id} :: {caption}"
            graph.add_news_case(case, doc)

# ---------------------------------------------------------------------------------------------- KG-4

GRAPH_PROMPT = """Trả lời câu hỏi chỉ dựa trên ngữ cảnh (đoạn văn bản và dữ kiện từ knowledge graph).
Nêu rõ số Điều luật khi có. Nếu ngữ cảnh không đủ, nói không đủ thông tin.

Dữ kiện knowledge graph:
{facts}

Đoạn văn bản:
{chunks}

Câu hỏi: {question}
Trả lời:"""

class GraphRAGAgent:
    """Hybrid GraphRAG: the same vector top-k as flat RAG, plus facts expanded from the graph."""

    def __init__(self, store: EmbeddingStore, graph: Neo4jGraph, llm_fn: Callable[[str], str]) -> None:
        self.store = store
        self.graph = graph
        self.llm_fn = llm_fn

    def answer(self, question: str, top_k: int = 3) -> str:
        chunks = self.store.search(question, top_k=top_k)
        doc_ids = list(dict.fromkeys(chunk["metadata"]["doc_id"] for chunk in chunks))
        facts = self.graph.context(question, doc_ids)
        context = "\n\n".join(f"[{index}] {chunk['content']}" for index, chunk in enumerate(chunks, start=1))
        prompt = GRAPH_PROMPT.format(question=question, chunks=context,
                                     facts="\n".join(f"- {fact}" for fact in facts))
        return self.llm_fn(prompt)
