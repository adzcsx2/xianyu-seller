# 文档更新日志

> 本文档记录项目文档的更新历史，详情以对应的更新记录为准。

---

## 2026-09-10 - 项目文档基线与 AI 安全边界

**变更概述**：补齐项目概览、架构、界面、接口、依赖和统一索引；根据当前源码记录功能开关、AI 配置来源、模型服务 URL 校验和密钥展示边界，并重建 API 源码索引。

| 文档 | 变更类型 | 简介 |
| --- | --- | --- |
| `README.md` | 更新导航 | 增加文档入口和最近更新。 |
| `docs/README.md` | 新增 | 建立分类目录、阅读顺序和文档约定。 |
| `docs/guide/PROJECT_OVERVIEW.md` | 新增 | 记录项目定位、入口、目录和运行链路。 |
| `docs/modules/ARCHITECTURE.md` | 新增 | 记录服务分层、功能开关、AI 配置和部署拓扑。 |
| `docs/modules/INTERFACES.md` | 新增 | 记录前端页面、开关可见性和用户旅程。 |
| `docs/references/API.md` | 新增 | 记录认证、功能开关、AI 模型和接口分组。 |
| `docs/references/DEPENDENCIES.md` | 新增 | 记录依赖、配置来源和 Docker 变体。 |
| `docs/deployment.md` | 更新安全 | 补充 AI 地址校验、模型列表权限和密钥展示规则。 |
| `docs/MIGRATION.md` | 更新迁移 | 补充 AI 环境变量覆盖和密钥边界。 |
| `.ai/index/backend-apis.json` | 重建索引 | 按当前源码校正为 255 条路由并加入 `/ai-models`。 |

[查看详情](../update-list/update-2026-09-10.md)

---

[← 返回主文档](../../README.md)
