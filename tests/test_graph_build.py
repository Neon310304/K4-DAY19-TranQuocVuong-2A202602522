import copy
import json
import unicodedata
import unittest

from src.graph import build_graph, extract_news_cases, link_entity
from src.models import Document


class RecordingGraph:
    def __init__(self):
        self.constraint_calls = 0
        self.articles = []
        self.cases = []

    def suggested_constraints(self):
        self.constraint_calls += 1

    def add_law_article(self, article):
        self.articles.append(copy.deepcopy(article))

    def add_news_case(self, case, doc):
        self.cases.append((copy.deepcopy(case), doc.id))


class TestLinkEntityEdgeCases(unittest.TestCase):
    def test_empty_known(self):
        self.assertIsNone(link_entity("mua bán trái phép chất ma túy", []))

    def test_whitespace_and_empty_canonical(self):
        self.assertIsNone(link_entity("   ", ["tên chuẩn"]))
        self.assertIsNone(link_entity("tên bất kỳ", [""]))

    def test_custom_normalizer(self):
        self.assertEqual(link_entity(" mdma ", ["MDMA"], normalize=lambda value: value.strip().casefold()), "MDMA")

    def test_duplicate_normalized_names_keep_first_original(self):
        known = ["Tội Mua bán trái phép chất ma túy", "mua bán trái phép chất ma túy"]
        self.assertEqual(link_entity("mua bán trái phép chất ma túy", known), known[0])


class TestBuildGraph(unittest.TestCase):
    def setUp(self):
        self.graph = RecordingGraph()
        self.crime = "mua bán trái phép chất ma túy"
        self.law = Document(
            id="blhs-dieu-251",
            content="Điều 251. Tội mua bán trái phép chất ma túy\n\n"
                    "1. Người nào mua bán trái phép chất ma túy, thì bị phạt tù từ 02 năm đến 07 năm.\n\n"
                    "2. MDMA có khối lượng từ 05 gam đến dưới 30 gam.",
            metadata={"article": "Điều 251 BLHS", "law": "BLHS",
                      "title": "Điều 251 BLHS. Tội mua bán trái phép chất ma túy"},
        )
        self.news = Document("news-test-1", "Bài báo giả lập cho unit test.", {"title": "Vụ án thử nghiệm"})
        self.case = {
            "name": "Vụ án thử nghiệm", "summary": "Tóm tắt giả lập.", "date": "", "location": " Hà Nội ",
            "charges": ["Tội Mua bán trái phép chất ma tuý"],
            "substances": [{"name": "mdma", "amount": "hơn 5 gam"}],
            "people": [{"name": " Nguyễn Văn An ", "aliases": ["An", "An"], "role": "bị cáo",
                        "sentence": "12 tháng tù", "charge": "Tội Mua bán trái phép chất ma tuý"}],
        }
        self.calls = []

    def llm(self, prompt, json_mode=False):
        self.calls.append((prompt, json_mode))
        return json.dumps({"cases": [self.case]}, ensure_ascii=False)

    def extract(self, payload):
        return extract_news_cases(self.news, lambda prompt, json_mode=False: json.dumps(payload), [self.crime])

    def test_build_writes_laws_first_and_preserves_provenance(self):
        self.assertIsNone(build_graph(self.graph, [self.law], [self.news], self.llm))
        self.assertEqual(self.graph.constraint_calls, 1)
        article = self.graph.articles[0]
        self.assertEqual(article["doc_id"], self.law.id)
        self.assertEqual(article["id"], "Điều 251 BLHS")
        self.assertEqual([clause["number"] for clause in article["clauses"]], [1, 2])
        case, doc_id = self.graph.cases[0]
        self.assertEqual(doc_id, self.news.id)
        self.assertEqual(case["name"], "news-test-1 :: Vụ án thử nghiệm")
        self.assertEqual(case["charges"], [article["crime"]])

    def test_json_mode_and_canonical_names_are_passed_to_llm(self):
        build_graph(self.graph, [self.law], [self.news], self.llm)
        self.assertEqual(len(self.calls), 1)
        prompt, json_mode = self.calls[0]
        self.assertTrue(json_mode)
        self.assertIn(self.crime, prompt)
        self.assertIn(self.news.content, prompt)

    def test_extraction_supports_the_single_argument_hint_adapter(self):
        cases = extract_news_cases(self.news, lambda prompt: self.llm(prompt, json_mode=True), [self.crime])
        self.assertEqual(cases[0]["charges"], [self.crime])
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(self.calls[0][1])

    def test_case_names_are_scoped_to_original_documents(self):
        other_news = Document("news-test-2", self.news.content, self.news.metadata)
        build_graph(self.graph, [self.law], [self.news, other_news], self.llm)
        self.assertEqual(len(self.calls), 2)
        self.assertNotEqual(self.graph.cases[0][0]["name"], self.graph.cases[1][0]["name"])
        self.assertEqual([doc_id for case, doc_id in self.graph.cases], ["news-test-1", "news-test-2"])

    def test_law_only_build_does_not_call_llm(self):
        build_graph(self.graph, [self.law], [], self.llm)
        self.assertEqual(self.calls, [])
        self.assertEqual(len(self.graph.articles), 1)

    def test_valid_empty_cases_for_educational_article(self):
        build_graph(self.graph, [self.law], [self.news],
                    lambda prompt, json_mode=False: '{"cases": []}')
        self.assertEqual(self.graph.cases, [])

    def test_invalid_json_is_not_silently_ignored(self):
        with self.assertRaisesRegex(ValueError, "news-test-1.*JSON"):
            build_graph(self.graph, [self.law], [self.news],
                        lambda prompt, json_mode=False: "invalid JSON")
        self.assertEqual(self.graph.cases, [])

    def test_missing_or_invalid_cases_list(self):
        for payload in ([], {}, {"cases": None}, {"cases": {}}, {"cases": "invalid"}):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, "cases"):
                    self.extract(payload)

    def test_case_entries_must_be_objects(self):
        with self.assertRaisesRegex(ValueError, "case phải là object"):
            self.extract({"cases": ["invalid"]})

    def test_nested_collections_must_be_lists(self):
        for field in ("charges", "people", "substances"):
            case = copy.deepcopy(self.case)
            case[field] = "invalid"
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, field):
                    self.extract({"cases": [case]})

    def test_nested_entries_and_aliases_are_validated(self):
        for field in ("people", "substances"):
            case = copy.deepcopy(self.case)
            case[field] = ["invalid"]
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "phải là object"):
                    self.extract({"cases": [case]})
        case = copy.deepcopy(self.case)
        case["people"][0]["aliases"] = "An"
        with self.assertRaisesRegex(ValueError, "aliases"):
            self.extract({"cases": [case]})

    def test_text_fields_do_not_accept_arbitrary_objects(self):
        case = copy.deepcopy(self.case)
        case["summary"] = {"invalid": "object"}
        with self.assertRaisesRegex(ValueError, "summary"):
            self.extract({"cases": [case]})
        case = copy.deepcopy(self.case)
        case["charges"] = [123]
        with self.assertRaisesRegex(ValueError, "charges"):
            self.extract({"cases": [case]})

    def test_unknown_charges_are_not_created_or_inherited(self):
        self.case["charges"].append("lừa đảo chiếm đoạt tài sản")
        self.case["people"][0]["charge"] = "lừa đảo chiếm đoạt tài sản"
        case = self.extract({"cases": [self.case]})[0]
        self.assertEqual(case["charges"], [self.crime])
        self.assertEqual(case["people"][0]["charge"], "")

    def test_unlinked_charges_are_retained_without_inventing_legal_edges(self):
        unknown_charge = "lừa đảo chiếm đoạt tài sản"
        self.case["charges"] = [unknown_charge, "  " + unknown_charge + "  ", ""]
        self.case["people"][0]["charge"] = unknown_charge
        build_graph(self.graph, [self.law], [self.news], self.llm)
        case, doc_id = self.graph.cases[0]
        self.assertEqual(doc_id, self.news.id)
        self.assertEqual(case["charges"], [])
        self.assertEqual(case["unlinked_charges"], [unknown_charge])
        self.assertEqual(case["people"][0]["charge"], "")
        self.assertEqual(case["people"][0]["unlinked_charge"], unknown_charge)

    def test_linked_and_absent_charges_do_not_create_false_diagnostics(self):
        case = self.extract({"cases": [self.case]})[0]
        self.assertEqual(case["unlinked_charges"], [])
        self.assertEqual(case["people"][0]["unlinked_charge"], "")
        self.case["charges"] = ["", "   "]
        self.case["people"][0]["charge"] = ""
        case = self.extract({"cases": [self.case]})[0]
        self.assertEqual(case["unlinked_charges"], [])
        self.assertEqual(case["people"][0]["unlinked_charge"], "")

    def test_names_aliases_and_amounts_are_normalized_without_inference(self):
        self.case["people"][0]["name"] = unicodedata.normalize("NFD", " Nguyễn Văn An ")
        self.case["substances"].append({"name": "Etomidate", "amount": "nghi là 3 gam"})
        case = self.extract({"cases": [self.case]})[0]
        self.assertEqual(case["people"][0]["name"], "Nguyễn Văn An")
        self.assertEqual(case["people"][0]["aliases"], ["An"])
        self.assertEqual(case["substances"][0], {"name": "MDMA", "amount": "hơn 5 gam"})
        self.assertEqual(case["substances"][1], {"name": "Etomidate", "amount": "nghi là 3 gam"})

    def test_missing_optional_fields_and_empty_names(self):
        case = self.extract({"cases": [{"people": [{}], "substances": [{}]}]})[0]
        self.assertEqual(case["people"], [])
        self.assertEqual(case["substances"], [])
        self.assertEqual(case["summary"], "")
        self.assertEqual(case["date"], "")

    def test_missing_case_caption_falls_back_to_document_title(self):
        self.case["name"] = None
        build_graph(self.graph, [self.law], [self.news], self.llm)
        self.assertEqual(self.graph.cases[0][0]["name"], "news-test-1 :: Vụ án thử nghiệm")


if __name__ == "__main__":
    unittest.main()
