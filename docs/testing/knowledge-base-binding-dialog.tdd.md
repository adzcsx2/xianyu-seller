# 知识库绑定弹窗易用性修复 — TDD 证据

## 问题与结论

- 2026-09-08 用户反馈“添加知识库无法正常添加”。
- 运行数据确认：当前 Passistant 商品已经绑定唯一的 Passistant 知识库；后端防重复约束正常，未发生添加失败。
- 根因是两个入口都叫“添加知识库”，且绑定弹窗只显示禁用的“已添加”，没有说明当前商品、可添加数量或下一步操作。

## RED

- 新增前端契约测试，要求绑定弹窗显示当前商品语义、可添加数量、完整的防重复说明、明确的“已添加到当前商品”状态和“新建知识库”入口。
- 旧实现因缺少 `availableBaseCount` 及上述文案而失败。
- RED 检查点：`84fe877 test: 复现知识库全部已绑定的添加困惑`。

## GREEN

- 绑定弹窗标题改为“添加到当前商品”，避免与创建全局知识库混淆。
- 弹窗显示当前商品和实时可添加数量；全部已绑定时显示“不能重复添加”的状态说明。
- 已绑定列表项继续保持禁用，状态改为“已添加到当前商品”。
- 弹窗新增“新建知识库”入口；创建弹窗标题同步改为“新建知识库”。
- GREEN 检查点：`33a9088 fix: 说明知识库已绑定状态并提供新建入口`。
- 生产构建检查点：`ef8659a build: 更新知识库添加弹窗产物`。
- 用户追加要求当前区域标题必须能识别具体商品。RED 检查点 `db13eea test: 要求当前项目知识库标题包含商品名`；GREEN 检查点 `e073bd9 fix: 在当前项目知识库标题显示商品名`，标题格式为“商品名 · 当前项目知识库”。

## 验证证据

- `python -m unittest discover -s tests -p test_global_runtime_contract.py -q`：17 tests，PASS。
- `node node_modules/typescript/bin/tsc --noEmit`：PASS。
- `node scripts/clean-build-output.mjs` + `node node_modules/vite/bin/vite.js build`：PASS，2369 modules transformed。
- `python -m unittest discover -s tests -q`：398 tests，PASS。
- 运行容器：`healthy`；首页返回 HTTP 200，`Cache-Control` 为 `no-store, must-revalidate, no-cache`。
- 运行中数据库仍只有原有的一条 Passistant 商品绑定，本次验证没有创建、删除或重复写入知识库。
- 隔离构建并部署提交 `871cdc4` 后，浏览器实际引用的 `KnowledgeBase-cqljc1OU.js` 同时包含“商品名 · 当前项目知识库”“添加到当前商品”“已添加到当前商品”和防重复说明。
- 桌面浏览器自动化驱动缺少本机运行模块；本次没有可比较的视觉基线，因此视觉回归结论为 INCONCLUSIVE，不作为功能通过依据。
