# 全局知识库与 AI 回复风格 TDD 证据

## 范围

- 全局知识库及事实、来源、规则、问答 CRUD。
- 商品与知识库的显式绑定/解绑，Passistant 只迁移并绑定到目标商品。
- 全局纯回复风格与商品业务规则分离。
- 绑定知识的确定性检索、价格/议价规则、输出防护和 fail-closed。
- 两段式知识库页面、未保存保护、重复提交保护和生产构建。

## RED

在生产实现修正前先加入合同测试，并观察到以下预期失败：

- 内容路由暴露 `_kind` 查询覆盖入口。
- 空全局库仍回退旧 Passistant 商品知识。
- 规则配置接受字符串、未知字段、负金额和越界轮数。
- 商品删除遗留知识绑定。
- 运行时注入完整快照，买家可见事实无法命中，同分结果忽略绑定顺序。
- 普通商品被 Passistant 安全/价格规则污染。
- 损坏规则可能在固定回复之后才 fail-closed。
- 多库议价轮数没有使用最严格边界。
- 前端编辑器缺少 dirty 状态和父列表刷新合同。
- Passistant seed 与已完成旧迁移的运行库缺少五分钟试用规则。

复审阶段继续按 RED → GREEN 补充了迁移 marker 快速路径、账号删除绑定清理、旧规则配置归一化和组合关键词 `all` 语义用例。

## GREEN

最终定向门禁：

```text
test_global_knowledge_contract.py  23 passed
test_global_runtime_contract.py    15 passed
test_product_knowledge.py          28 passed
test_ai_reply.py                   13 passed
test_ai_reply_safety.py            39 passed
total                              118 passed
```

附加验证：

- TypeScript `tsc --noEmit` 通过。
- Vite 生产构建通过，2369 个模块完成转换。
- `python -m compileall -q app tests` 通过。
- `git diff --check -- app frontend tests static/index.html` 通过。
- 全量 Python：380 项全部通过。全量门禁曾暴露 Windows 浏览器 watchdog 未统一 `/` 与 `\\` 的路径匹配问题；补充规范化后，其 8 项测试及全量测试均通过。
- 当前 Python 环境未安装 `coverage.py`，因此本轮没有可报告的行覆盖率百分比；以定向合同、全量单测、类型检查和生产构建作为门禁证据。

## Checkpoint 说明

工作区在任务开始前已有多组未提交用户改动。为避免把用户改动混入自动提交，本轮保留完整 RED/GREEN 命令与结果，但未创建 checkpoint commit。
