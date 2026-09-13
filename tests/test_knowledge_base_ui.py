"""知识库普通用户闭环 E2E；全部数据为浏览器内合成 fixture。"""

import json
import re
import socket
import threading
import time
import unittest

import uvicorn
from playwright.sync_api import expect, sync_playwright

from app import reply_server


class KnowledgeBaseUiTests(unittest.TestCase):
    def test_upload_preview_import_and_evidence_are_observable(self):
        token = "knowledge-ui-synthetic-token"
        reply_server.SESSION_TOKENS[token] = {
            "user_id": 7, "username": "synthetic", "timestamp": time.time()
        }
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(
            uvicorn.Config(reply_server.app, lifespan="off", log_level="error")
        )
        server_thread = threading.Thread(
            target=server.run, kwargs={"sockets": [listener]}, daemon=True
        )
        document = None
        base_version = 1

        def base_detail():
            source = {
                "id": "source-manual", "knowledge_base_id": "base-1",
                "source_key": "source-manual", "title": "README.md：产品简介",
                "reference": "仅标题记录", "url": "", "notes": "",
                "source_kind": "manual", "document_id": None,
                "document_status": "metadata_only", "linked_entry_count": 0,
                "runtime_enabled_count": 0, "usage": [],
            }
            facts = []
            documents = []
            if document:
                source = {
                    **source, "id": "source-document", "source_key": "source-document",
                    "title": "guide.md", "source_kind": "document",
                    "document_id": "document-1", "document_status": document["status"],
                    "linked_entry_count": 1 if document["status"] == "imported" else 0,
                    "runtime_enabled_count": 1 if document["status"] == "imported" else 0,
                    "usage": [{"kind": "fact", "content_id": "fact-1", "label": "产品简介", "enabled": True}] if document["status"] == "imported" else [],
                }
                documents = [{key: value for key, value in document.items() if key != "sections"}]
                if document["status"] == "imported":
                    facts = [{
                        "id": "fact-1", "knowledge_base_id": "base-1",
                        "fact_key": "document-synthetic-1", "category": "document",
                        "title": "产品简介", "content": "这是一条合成公开说明。",
                        "source_ids": ["source-document"], "priority": 0, "enabled": True,
                    }]
            return {
                "id": "base-1", "base_key": "synthetic", "name": "合成知识库",
                "description": "普通用户测试", "version": base_version, "enabled": True,
                "schema_version": 3, "seed_version": None, "checksum": "",
                "fact_count": len(facts), "source_count": 1, "rule_count": 0,
                "qa_count": 0, "document_count": len(documents), "binding_count": 0,
                "facts": facts, "sources": [source], "rules": [], "qa_entries": [],
                "documents": documents,
            }

        def route_api(route):
            nonlocal document, base_version
            request = route.request
            path = request.url.removeprefix(origin)
            if path == "/system-settings/public":
                body = {"admin_login_enabled": "true"}
            elif path == "/verify":
                body = {"authenticated": True, "user_id": 7, "username": "synthetic", "is_admin": True}
            elif path == "/feature-flags":
                body = {"revision": 1, "configured": {}, "effective": {"feature_knowledge_base_enabled": True, "feature_ai_reply_enabled": True}, "runtime_apply": None}
            elif path == "/cookies/details":
                body = [{"id": "account-1", "nickname": "合成账号", "enabled": True, "value": ""}]
            elif path == "/items":
                body = {"items": [{"cookie_id": "account-1", "item_id": "item-1", "item_title": "合成商品"}]}
            elif path == "/knowledge-bases":
                summary = {key: value for key, value in base_detail().items() if key not in {"facts", "sources", "rules", "qa_entries", "documents"}}
                body = {"knowledge_bases": [summary]}
            elif path == "/items/account-1/item-1/knowledge-bindings":
                body = {"bindings": []}
            elif path == "/knowledge-bases/base-1" and request.method == "GET":
                body = base_detail()
            elif path == "/knowledge-bases/base-1/documents" and request.method == "POST":
                base_version += 1
                document = {
                    "id": "document-1", "knowledge_base_id": "base-1", "source_id": "source-document",
                    "original_filename": "guide.md", "media_type": "text/markdown", "encoding": "utf-8",
                    "byte_size": 40, "content_sha256": "synthetic", "parser_version": "text-sections-v1",
                    "status": "parsed", "section_count": 1, "imported_section_count": 0,
                    "linked_entry_count": 0, "runtime_enabled_count": 0, "usage": [],
                    "created_at": "2026-09-13", "updated_at": "2026-09-13",
                    "sections": [{"id": "section-1", "ordinal": 1, "heading_path": "产品简介", "anchor": "section-1", "content": "这是一条合成公开说明。", "content_sha256": "section-synthetic", "imported": False}],
                }
                body = {"document": document, "duplicate": False, "version": base_version}
            elif path == "/knowledge-bases/base-1/documents/document-1" and request.method == "GET":
                body = document
            elif path == "/knowledge-bases/base-1/documents/document-1/imports":
                base_version += 1
                document["status"] = "imported"
                document["imported_section_count"] = 1
                document["sections"][0]["imported"] = True
                body = {"document_id": "document-1", "imported_fact_ids": ["fact-1"], "version": base_version}
            elif path == "/knowledge-bases/base-1/ask":
                body = {"knowledge_base_id": "base-1", "knowledge_base_name": "合成知识库", "model_name": "synthetic-model", "answer": "合成回答", "provided_evidence": [{"content_type": "fact", "content_key": "document-synthetic-1", "source_title": "guide.md", "document_status": "imported"}]}
            else:
                route.continue_()
                return
            route.fulfill(content_type="application/json", body=json.dumps(body, ensure_ascii=False))

        try:
            with sync_playwright() as playwright:
                server_thread.start()
                for _ in range(100):
                    if server.started:
                        break
                    time.sleep(0.02)
                self.assertTrue(server.started)
                browser = playwright.chromium.launch(headless=True)
                try:
                    page = browser.new_page(viewport={"width": 1440, "height": 1000})
                    page.add_init_script(
                        "localStorage.setItem('auth_token', " + json.dumps(token) + ");"
                        "localStorage.setItem('active_page', 'knowledge-base');"
                    )
                    page.route(origin + "/**", route_api)
                    page.goto(origin)
                    expect(page.get_by_text("全部知识库", exact=True)).to_be_visible(timeout=10000)
                    page.get_by_role("button", name="编辑知识库 合成知识库").click()
                    expect(page.get_by_text("尚未上传文档。", exact=False)).to_be_visible()
                    page.get_by_role("button", name=re.compile(r"^来源引用")).click()
                    expect(page.get_by_text("仅引用记录 · 未上传文件", exact=False)).to_be_visible()

                    page.locator('input[type="file"]').set_input_files({
                        "name": "guide.md", "mimeType": "text/markdown",
                        "buffer": b"# synthetic\npublic test text",
                    })
                    expect(page.get_by_text("已上传，尚未进入 AI", exact=False)).to_be_visible()
                    page.get_by_text("guide.md", exact=True).first.click()
                    page.get_by_text("产品简介", exact=True).click()
                    page.get_by_role("button", name="导入所选章节", exact=True).click()
                    page.get_by_role("alertdialog").get_by_role(
                        "button", name="导入所选章节", exact=True
                    ).click()
                    expect(page.get_by_text("全部章节已导入", exact=False)).to_be_visible()
                    page.get_by_role("button", name=re.compile(r"^来源引用")).click()
                    page.get_by_text("查看关联条目", exact=True).click()
                    expect(page.get_by_text("事实：产品简介", exact=True)).to_be_visible()

                    page.get_by_label("向当前知识库提问").fill("合成问题")
                    page.get_by_role("button", name="提问", exact=True).click()
                    expect(page.get_by_text("本次提供给 AI 的依据", exact=True)).to_be_visible()
                    expect(page.get_by_text("guide.md · 事实 · 文档已导入", exact=True)).to_be_visible()
                finally:
                    browser.close()
        finally:
            server.should_exit = True
            if server_thread.ident:
                server_thread.join(10)
            listener.close()
            reply_server.SESSION_TOKENS.pop(token, None)


if __name__ == "__main__":
    unittest.main()
