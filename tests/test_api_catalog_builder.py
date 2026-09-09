import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class ApiCatalogBuilderTests(unittest.TestCase):
    """验证 API 索引器不会把注释误当路由，并保留可追溯元数据。"""

    BUILDER = (
        Path(__file__).resolve().parents[1]
        / ".ai"
        / "tools"
        / "api-first"
        / "build-api-index.ps1"
    )

    def _build_fixture(self) -> dict:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            route_file = workspace / "app" / "routes.py"
            route_file.parent.mkdir()
            route_file.write_text(
                "\n".join(
                    [
                        "from fastapi import APIRouter, Depends",
                        "",
                        "router = APIRouter(prefix='/api')",
                        "",
                        "@router.get('/items', response_model=ItemResponse)",
                        "def list_items(current_user: dict = Depends(get_current_user)):",
                        "    return {'items': []}",
                        "",
                        "# @router.post('/commented')",
                        "def commented_route():",
                        "    return None",
                        "",
                        "@router.get('/{path:path}')",
                        "async def catch_all_route(path: str):",
                        "    return None",
                        "",
                        "app.include_router(router, prefix='/v1')",
                    ]
                ),
                encoding="utf-8",
            )
            output = workspace / "index.json"
            completed = subprocess.run(
                [
                    "pwsh.exe",
                    "-NoProfile",
                    "-File",
                    str(self.BUILDER),
                    "-WorkspaceRoot",
                    str(workspace),
                    "-OutputPath",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("API_INDEX_BUILT", completed.stdout)
            return json.loads(output.read_text(encoding="utf-8"))

    def test_catalog_skips_comments_composes_prefix_and_normalizes_catch_all(self):
        document = self._build_fixture()
        routes = {(route["method"], route["path"]): route for route in document["routes"]}

        self.assertIn(("GET", "/v1/api/items"), routes)
        self.assertNotIn(("POST", "/commented"), routes)
        self.assertIn(("GET", "/v1/api/{path}"), routes)

    def test_catalog_records_handler_source_schema_and_auth(self):
        document = self._build_fixture()
        route = next(
            route
            for route in document["routes"]
            if route["method"] == "GET" and route["path"] == "/v1/api/items"
        )

        self.assertEqual(route["handler"], "list_items")
        self.assertEqual(route["request_schemas"], [])
        self.assertIn("ItemResponse", route["response_schemas"])
        self.assertNotEqual(route["auth_hint"], "unknown")
        self.assertEqual(route["sources"][0]["path"], "app/routes.py")
        self.assertGreater(route["sources"][0]["line"], 0)

    def test_checked_in_index_contains_product_knowledge_routes(self):
        index_path = Path(__file__).resolve().parents[1] / ".ai" / "index" / "backend-apis.json"
        document = json.loads(index_path.read_text(encoding="utf-8"))
        routes = {(route["method"], route["path"]): route for route in document["routes"]}
        expected = {
            ("GET", "/items/{cookie_id}/{item_id}/ai-knowledge"),
            ("PUT", "/items/{cookie_id}/{item_id}/ai-knowledge"),
            ("POST", "/items/{cookie_id}/{item_id}/ai-knowledge/import-passistant"),
            ("POST", "/items/{cookie_id}/{item_id}/ai-knowledge/preview"),
        }
        self.assertTrue(expected.issubset(routes))
        self.assertEqual(routes[("GET", "/items/{cookie_id}/{item_id}/ai-knowledge")]["handler"], "get_product_knowledge")
        self.assertEqual(routes[("PUT", "/items/{cookie_id}/{item_id}/ai-knowledge")]["handler"], "put_product_knowledge")


if __name__ == "__main__":
    unittest.main()
