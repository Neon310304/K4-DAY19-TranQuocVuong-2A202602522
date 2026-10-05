import unittest
from unittest.mock import Mock

from src.graph import GraphRAGAgent, Neo4jGraph


class TestGraphContext(unittest.TestCase):
    def setUp(self):
        self.graph = object.__new__(Neo4jGraph)
        self.graph.seed_facts = Mock(return_value=(["case-seed"], ["Seed edge", "Seed edge"]))
        self.cases = [{"id": "case-seed", "name": "news-test :: Vụ thử nghiệm", "doc_id": "news-test",
                       "source_title": "Vụ thử nghiệm", "summary": "Tóm tắt thử nghiệm, lượng MDMA 5 gam.",
                       "people": [{"name": "Nguyễn Văn An", "role": "bị cáo", "charge": "mua bán",
                                   "sentence": "36 tháng tù", "aliases": [], "focused": True}]}]
        self.case_clauses = [{"article_id": "Điều 251 BLHS", "title": "Tội mua bán trái phép chất ma túy",
                              "doc_id": "blhs-dieu-251", "number": 1, "priority": 1,
                              "text": "phạt tù từ 02 năm đến 07 năm", "penalty": "phạt tù"}]
        self.direct_clauses = []

        def run(statement, **params):
            if "MATCH (article:Article)-[:HAS_CLAUSE]" in statement:
                return self.direct_clauses
            if "HAS_CLAUSE" in statement:
                return self.case_clauses
            return self.cases

        self.graph.run = Mock(side_effect=run)

    def test_multi_hop_context_contains_legal_basis_case_and_person(self):
        facts = self.graph.context("Nguyễn Văn An bị tuyên án gì?", ["news-test"])
        text = "\n".join(facts)
        self.assertIn("Điều 251 BLHS", text)
        self.assertIn("02 năm đến 07 năm", text)
        self.assertIn("Tóm tắt thử nghiệm", text)
        self.assertIn("36 tháng tù", text)
        self.assertIn("news-test", text)
        self.assertIn("blhs-dieu-251", text)
        self.graph.seed_facts.assert_called_once_with("Nguyễn Văn An bị tuyên án gì?", ["news-test"])

    def test_deduplicates_clause_and_seed_facts(self):
        self.direct_clauses = list(self.case_clauses)
        facts = self.graph.context("Điều 251 BLHS", ["news-test"])
        self.assertEqual(sum("Điều 251 BLHS" in fact for fact in facts), 1)
        self.assertEqual(facts.count("Seed edge"), 1)

    def test_legal_basis_is_prioritized_before_truncation(self):
        facts = self.graph.context("Khung phạt cơ bản?", ["news-test"], max_facts=1)
        self.assertEqual(len(facts), 1)
        self.assertIn("Điều 251 BLHS", facts[0])

    def test_zero_or_negative_budget_does_not_query(self):
        self.assertEqual(self.graph.context("Câu hỏi", [], max_facts=0), [])
        self.assertEqual(self.graph.context("Câu hỏi", [], max_facts=-1), [])
        self.graph.seed_facts.assert_not_called()
        self.graph.run.assert_not_called()

    def test_missing_seeds_and_no_explicit_article_returns_empty(self):
        self.graph.seed_facts.return_value = ([], [])
        self.assertEqual(self.graph.context("Không có dữ liệu", []), [])
        self.graph.run.assert_not_called()

    def test_explicit_article_and_clause_without_vector_hits(self):
        self.graph.seed_facts.return_value = ([], [])
        self.direct_clauses = list(self.case_clauses)
        facts = self.graph.context("Khoản 1 Điều 251 BLHS quy định gì?", [])
        self.assertIn("Điều 251 BLHS", facts[0])
        params = self.graph.run.call_args.kwargs
        self.assertEqual(params["article_numbers"], ["251"])
        self.assertEqual(params["clause_numbers"], [1])
        self.assertEqual(params["law_filter"], "BLHS")

    def test_definition_retains_text_without_penalty(self):
        self.cases = []
        self.direct_clauses = [{"article_id": "Điều 2 Luật PCMT", "title": "Giải thích từ ngữ",
                                "doc_id": "pcmt-dieu-2", "number": 4, "priority": 2,
                                "text": "Tiền chất dùng trong điều chế, sản xuất chất ma túy.", "penalty": ""}]
        facts = self.graph.context("Theo Luật PCMT, tiền chất là gì?", ["pcmt-dieu-2"])
        self.assertIn("điều chế, sản xuất", "\n".join(facts))
        self.assertEqual(self.graph.run.call_args.kwargs["law_filter"], "Luật PCMT")

    def test_maximum_penalty_requests_clauses_without_substance_edges(self):
        self.graph.context("Hành vi bị phạt tối đa bao nhiêu?", ["news-test"])
        legal_calls = [call for call in self.graph.run.call_args_list if "maximum" in call.kwargs]
        self.assertTrue(legal_calls)
        self.assertTrue(all(call.kwargs["maximum"] for call in legal_calls))

    def test_aggregation_expands_substance_beyond_vector_seeds(self):
        self.graph.seed_facts.return_value = ([], [])
        facts = self.graph.context("Những vụ việc nào liên quan MDMA?", [])
        self.assertIn("Tóm tắt thử nghiệm", "\n".join(facts))
        self.assertNotIn("Điều 251", "\n".join(facts))
        self.assertTrue(self.graph.run.call_args.kwargs["aggregate"])
        self.assertEqual(self.graph.run.call_args.kwargs["substances"], ["MDMA"])

    def test_aggregation_does_not_append_unrelated_vector_seed_edges(self):
        self.graph.seed_facts.return_value = (["unrelated-case"], ["Unrelated seed edge"])
        facts = self.graph.context("Các vụ án nào liên quan MDMA?", ["unrelated-news"])
        self.assertNotIn("Unrelated seed edge", facts)

    def test_substance_facts_preserve_quantity_qualifiers(self):
        self.cases[0]["substances"] = [{"name": "MDMA", "amount": "hơn 5 gam"}]
        text = "\n".join(self.graph.context("Những vụ việc nào có MDMA?", []))
        self.assertIn("liên quan chất MDMA", text)
        self.assertIn("lượng theo nguồn: hơn 5 gam", text)

    def test_penalty_fallback_and_alias_are_readable(self):
        self.case_clauses[0]["text"] = ""
        self.cases[0]["people"][0]["aliases"] = ["Biệt danh An"]
        text = "\n".join(self.graph.context("Khung phạt?", ["news-test"]))
        self.assertIn("khoản 1: phạt tù", text)
        self.assertIn("Biệt danh An", text)

    def test_unlinked_charge_diagnostics_are_sourced_and_not_legal_facts(self):
        self.case_clauses = []
        unknown_charge = "lừa đảo chiếm đoạt tài sản"
        self.cases[0]["unlinked_charges"] = [unknown_charge]
        person = self.cases[0]["people"][0]
        person["charge"] = ""
        person["unlinked_charge"] = unknown_charge
        text = "\n".join(self.graph.context("Nguyễn Văn An phạm tội gì?", ["news-test"]))
        self.assertIn(unknown_charge, text)
        self.assertIn("chưa nối được với KB luật", text)
        self.assertIn("news-test", text)
        self.assertNotIn("Điều 251", text)


class TestGraphRAGRetrieval(unittest.TestCase):
    def test_deduplicates_original_doc_ids_and_keeps_all_chunks(self):
        store = Mock()
        store.search.return_value = [
            {"id": "news-1#0#1", "content": "Đoạn đầu", "metadata": {"doc_id": "news-1"}},
            {"id": "news-1#1#2", "content": "Đoạn sau", "metadata": {"doc_id": "news-1"}},
            {"id": "law-1#0#3", "content": "Văn bản luật", "metadata": {"doc_id": "law-1"}},
        ]
        graph = Mock()
        graph.context.return_value = ["Dữ kiện graph"]
        llm = Mock(side_effect=lambda prompt: prompt)
        answer = GraphRAGAgent(store, graph, llm).answer("Câu hỏi thử", top_k=3)
        store.search.assert_called_once_with("Câu hỏi thử", top_k=3)
        graph.context.assert_called_once_with("Câu hỏi thử", ["news-1", "law-1"])
        self.assertIn("- Dữ kiện graph", answer)
        self.assertIn("[1] Đoạn đầu", answer)
        self.assertIn("[2] Đoạn sau", answer)
        self.assertIn("[3] Văn bản luật", answer)
        llm.assert_called_once()

    def test_no_vector_hits_still_allows_graph_context(self):
        store = Mock()
        store.search.return_value = []
        graph = Mock()
        graph.context.return_value = ["Dữ kiện theo tên hoặc alias"]
        agent = GraphRAGAgent(store, graph, lambda prompt: prompt)
        self.assertIn("Dữ kiện theo tên hoặc alias", agent.answer("Câu hỏi"))
        graph.context.assert_called_once_with("Câu hỏi", [])

    def test_returns_llm_response_not_the_prompt(self):
        store = Mock()
        store.search.return_value = []
        graph = Mock()
        graph.context.return_value = []
        agent = GraphRAGAgent(store, graph, lambda prompt: "Câu trả lời")
        self.assertEqual(agent.answer("Câu hỏi"), "Câu trả lời")


if __name__ == "__main__":
    unittest.main()
