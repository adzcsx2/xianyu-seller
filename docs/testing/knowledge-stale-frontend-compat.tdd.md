# 知识库旧前端空白修复 — TDD 证据

## 来源与用户旅程

- 来源：2026-09-08 用户截图与本地容器请求日志，没有单独的计划文件。
- 旅程：作为仍打开旧版单页应用的管理员，我重新进入知识库时，已绑定商品仍应看到公开问答，而不是因后端升级显示空白。
- 旅程：作为刷新或重新打开页面的管理员，浏览器必须重新校验 SPA 入口文件，避免继续使用过期入口。

## RED

- 命令：`python -m unittest` 定向运行 4 个知识库兼容与缓存测试。
- 结果：4 个目标均失败；旧 GET 返回 `410`，越权和不存在商品也被错误地统一成 `410`，首页缺少 `Cache-Control: no-cache, no-store, must-revalidate`。
- 检查点：`bd6200c test: 复现知识库旧前端空白问题`。

## GREEN

- 实现：把商品绑定的全局知识库公开问答投影成旧前端可读取的文档；未绑定商品返回空文档；读取前先恢复账号与商品范围校验。
- 实现：所有由 `serve_frontend()` 返回的 SPA 入口增加 `Cache-Control`、`Pragma` 和 `Expires` 禁止缓存。
- 同一组 4 个定向测试：`Ran 4 tests ... OK`。
- 检查点：`f1e4d61 fix: 兼容旧知识库页面并禁用入口缓存`。
- 重构检查点：`049da9d refactor: 明确知识库兼容路由测试语义`。

## 测试规格

| 保证 | 测试 | 类型 | 结果 |
|---|---|---|---|
| 绑定的全局库可通过旧 GET 读取公开问答 | `test_global_create_binding_duplicate_and_legacy_route_projection` | API 集成 | PASS |
| 未绑定商品返回版本 0 的空文档 | `test_get_empty_document_has_version_zero_and_no_sources` | API 集成 | PASS |
| 旧 GET 仍执行 403/404 范围校验，旧写接口继续退役 | `test_legacy_get_checks_scope_while_legacy_put_stays_retired` | API 集成 | PASS |
| SPA 入口明确禁止浏览器缓存 | `test_frontend_document_disables_browser_cache` | HTTP 集成 | PASS |

## 完整验证与覆盖率

- `python -m unittest discover -s tests -p 'test_*.py' -q`：386 tests，PASS。
- `node node_modules/typescript/bin/tsc --noEmit`：PASS。
- `node node_modules/vite/bin/vite.js build`：PASS，2369 modules transformed。
- `coverage run --branch --source=app ...`：本次生产改动对应可执行语句 25 行，执行 22 行，行覆盖率 88%。未覆盖的是前端文件缺失兜底与兼容投影内部异常兜底；主成功路径、空绑定、403、404 均已覆盖。
- 仓库没有全局 80% 覆盖门槛；`app/reply_server.py` 是约一万行的集中式历史路由文件，定向测试下整文件覆盖率为 15%，不作为本次改动覆盖率。

## 合并证据

若后续压缩提交，请在合并说明中保留上述 RED/GREEN/重构检查点与 386 个测试通过记录。
