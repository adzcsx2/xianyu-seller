# 文档索引

本目录按内容分类组织，覆盖项目指南、模块说明、接口参考、开发规则、计划、测试证据和更新记录。

## 目录结构

```text
docs/
├── checklist/                 # 发布与核对清单
├── community/                 # 社区图片与入口素材
├── design/                    # 设计文档
├── guide/                     # 使用与测试指南
├── modules/                   # 架构和界面模块说明
├── plan/                      # 按任务归档的计划文档
├── product/                   # 产品文档
├── references/                # 依赖、接口和 AI 开发规则
├── reports/                   # 验证报告和文档更新日志
├── screenshots/               # 界面截图
├── testing/                   # TDD 与自动化测试证据
└── update-list/               # 每次文档更新的详细记录
```

## 建议阅读顺序

**部署者**：先了解运行方式和数据边界。

1. [项目概览](guide/PROJECT_OVERVIEW.md)
2. [部署与排查](deployment.md)
3. [迁移说明](MIGRATION.md)

**开发者**：先掌握架构、接口事实源和测试入口。

1. [架构说明](modules/ARCHITECTURE.md)
2. [接口参考](references/API.md)
3. [全量接口目录](references/ai-rules/05-全量接口目录.md)
4. [自动化测试指南](guide/自动化测试指南.md)

## 指南文档

- [项目概览](guide/PROJECT_OVERVIEW.md) - 项目定位、入口和主要目录。
- [自动化测试指南](guide/自动化测试指南.md) - 测试套件、数据库隔离和质量检查。
- [部署与排查](deployment.md) - Docker、源码运行、滑块验证和故障处理。
- [迁移说明](MIGRATION.md) - 升级、配置迁移和回滚边界。

## 模块文档

- [架构说明](modules/ARCHITECTURE.md) - 服务分层、前后端边界、后台任务和数据流。
- [界面与功能开关](modules/INTERFACES.md) - 前端页面、独立开关和可见性规则。

## 参考文档

- [接口参考](references/API.md) - 稳定入口、认证和高风险接口摘要。
- [依赖与配置](references/DEPENDENCIES.md) - Python、前端、浏览器和部署配置。
- [AI 开发规则](references/ai-rules/README.md) - 现有 AI 协作规则目录。
- [全量接口目录](references/ai-rules/05-全量接口目录.md) - 源码索引和接口事实源。

## 报告和测试证据

- [文档更新日志](reports/CHANGELOG.md) - 文档变更摘要和详情链接。
- [更新详情（2026-09-13）](update-list/update-2026-09-13.md) - 本次审计的证据矩阵与实际文档差异。
- [历史更新详情（2026-09-10）](update-list/update-2026-09-10.md) - 项目文档基线与 AI 安全边界记录。
- [测试证据目录](testing/) - 功能修复、TDD 和自动化测试记录。
- [知识库文档闭环 TDD 证据](testing/knowledge-base-ai-qa.tdd.md) - 知识库上传、导入、来源关系和问答依据的测试记录。
- [系统日志增量刷新](testing/system-log-incremental-refresh.tdd.md) - 文件增量解析、分页和 30 秒刷新合同。
- [日志保留七天](testing/日志保留七天.tdd.md) - 应用日志、验证码日志和测试产物保留策略的测试记录。
- [计划目录](plan/) - 分阶段设计、执行和测试计划。

## 计划文档

- [知识库文档闭环与普通用户体验](plan/知识库文档闭环与普通用户体验-2026-09-13/) - 文档上传、解析、显式导入、来源关系、普通用户体验和完整验收计划。

## 约定

- 新增文档使用中文；分类目录使用英文，任务和报告主题目录可使用中文。
- 真实账号、Cookie、Token、订单、聊天记录、卡密、知识库内容和密钥不得进入文档。
- 接口变更先更新源码索引，再同步接口参考和相关用户文档。

---

[← 返回项目根目录](../README.md)
