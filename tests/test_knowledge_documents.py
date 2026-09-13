import tempfile
import unittest
from pathlib import Path

from app.db_manager import DBManager, KnowledgeDocumentInUse


class KnowledgeDocumentParserTests(unittest.TestCase):
    def test_markdown_headings_bom_and_code_fence_are_deterministic(self):
        from app.knowledge_documents import KnowledgeDocumentParser

        content = "\ufeff# 概览\r\n合成说明。\r\n```text\r\n# 不是标题\r\n```\r\n## 细节\r\n合成细节。".encode("utf-8")
        parsed = KnowledgeDocumentParser.parse_bytes("synthetic.md", content)
        self.assertEqual([section.ordinal for section in parsed.sections], [1, 2])
        self.assertEqual(parsed.sections[1].heading_path, "概览 / 细节")
        self.assertIn("# 不是标题", parsed.sections[0].content)
        self.assertEqual(parsed.content_sha256, KnowledgeDocumentParser.parse_bytes("again.md", content).content_sha256)

    def test_text_is_split_without_exceeding_fact_limit(self):
        from app.knowledge_documents import KnowledgeDocumentParser

        parsed = KnowledgeDocumentParser.parse_bytes("notes.txt", (("甲" * 500) + "。" + ("乙" * 500)).encode())
        self.assertGreater(len(parsed.sections), 1)
        self.assertTrue(all(1 <= len(section.content) <= 800 for section in parsed.sections))

    def test_invalid_inputs_are_rejected(self):
        from app.knowledge_documents import KnowledgeDocumentError, KnowledgeDocumentParser

        for filename, content, code in (
            ("empty.txt", b" ", "knowledge_document_empty"),
            ("bad.txt", b"\xff", "knowledge_document_encoding"),
            ("bad.pdf", b"synthetic", "knowledge_document_type"),
            ("nul.md", b"hello\x00", "knowledge_document_invalid"),
            ("big.md", b"x" * (512 * 1024 + 1), "knowledge_document_too_large"),
        ):
            with self.subTest(filename=filename), self.assertRaises(KnowledgeDocumentError) as caught:
                KnowledgeDocumentParser.parse_bytes(filename, content)
            self.assertEqual(caught.exception.error_code, code)

    def test_excessive_tiny_sections_are_rejected(self):
        from app.knowledge_documents import KnowledgeDocumentError, KnowledgeDocumentParser

        content = ("x\n\n" * 1001).encode()
        with self.assertRaises(KnowledgeDocumentError) as caught:
            KnowledgeDocumentParser.parse_bytes("many.txt", content)
        self.assertEqual(caught.exception.error_code, "knowledge_document_too_many_sections")


class KnowledgeDocumentDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = DBManager(str(Path(self.tmp.name) / "documents.db"))
        self.base = self.db.create_knowledge_base("合成文档库", base_key="synthetic-docs")

    def tearDown(self):
        self.db.conn.close()
        self.tmp.cleanup()

    def test_upload_import_usage_and_delete_are_closed_loop(self):
        uploaded = self.db.create_knowledge_document(
            self.base["id"], "guide.md", "# 标题\n合成事实。".encode(), expected_version=1
        )
        self.assertFalse(uploaded["duplicate"])
        document = uploaded["document"]
        self.assertEqual(document["status"], "parsed")
        self.assertEqual(document["linked_entry_count"], 0)

        imported = self.db.import_knowledge_document_sections(
            self.base["id"], document["id"], [document["sections"][0]["id"]], expected_version=2
        )
        self.assertEqual(imported["version"], 3)
        detail = self.db.get_knowledge_document(self.base["id"], document["id"])
        self.assertEqual(detail["status"], "imported")
        self.assertEqual(detail["runtime_enabled_count"], 1)
        self.assertEqual(self.db.get_knowledge_base(self.base["id"])["facts"][0]["source_ids"], [document["source_id"]])

    def test_same_bytes_are_idempotent(self):
        first = self.db.create_knowledge_document(self.base["id"], "one.txt", b"synthetic", expected_version=1)
        second = self.db.create_knowledge_document(self.base["id"], "two.txt", b"synthetic", expected_version=2)
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["document"]["id"], second["document"]["id"])
        self.assertEqual(second["version"], 2)

    def test_deleting_imported_fact_restores_document_to_parsed(self):
        uploaded = self.db.create_knowledge_document(
            self.base["id"], "guide.md", b"# Heading\nSynthetic fact.", expected_version=1
        )
        document = uploaded["document"]
        imported = self.db.import_knowledge_document_sections(
            self.base["id"], document["id"], [document["sections"][0]["id"]], expected_version=2
        )

        self.db.delete_knowledge_fact(
            self.base["id"], imported["imported_fact_ids"][0], expected_version=3
        )

        detail = self.db.get_knowledge_document(self.base["id"], document["id"])
        self.assertEqual(detail["status"], "parsed")
        self.assertEqual(detail["imported_section_count"], 0)

    def test_document_source_cannot_be_deleted_as_a_manual_source(self):
        uploaded = self.db.create_knowledge_document(
            self.base["id"], "guide.md", b"Synthetic fact.", expected_version=1
        )

        with self.assertRaises(KnowledgeDocumentInUse):
            self.db.delete_knowledge_source(
                self.base["id"], uploaded["document"]["source_id"], expected_version=2
            )


if __name__ == "__main__":
    unittest.main()
