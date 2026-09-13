# 文档更新日志

> 本文档记录项目文档的更新历史，详情以对应的更新记录为准。

---

## 2026-09-13 - 知识库、日志与验证链路文档同步

**变更概述**：根据当前源码和已提交改动，补充知识库文档导入、系统日志分页/刷新/七天保留、滑块严格票据校验与兼容运行时说明，并同步测试入口和文档索引。

| 文档 | 变更类型 | 简介 |
| --- | --- | --- |
| `README.md` | 更新导航与功能说明 | 增加最近更新入口，并保留知识库、滑块和系统日志的用户可见能力说明。 |
| `docs/README.md` | 更新索引 | 增加知识库与系统日志测试证据链接。 |
| `docs/guide/PROJECT_OVERVIEW.md` | 更新概览 | 补充知识库文档闭环、日志能力和滑块/日志工具归属。 |
| `docs/guide/自动化测试指南.md` | 更新测试说明 | 同步 E2E 模块、隔离产物目录和七天清理行为。 |
| `docs/modules/ARCHITECTURE.md` | 更新架构 | 增加知识库解析、日志增量收集/保留和滑块运行时链路。 |
| `docs/modules/INTERFACES.md` | 更新交互 | 增加账号验证和系统日志页面行为。 |
| `docs/references/API.md` | 更新接口参考 | 增加系统日志、人工验证、实时验证码链接和严格 Cookie 成功条件。 |
| `docs/references/ai-rules/05-全量接口目录.md` | 校正索引说明 | 以 `.ai/index/backend-apis.json` 的 252 条路由为准。 |
| `docs/references/DEPENDENCIES.md` | 更新依赖 | 记录 NumPy/OpenCV、固定版本 `slidex` 和相关运行时变量。 |
| `docs/deployment.md` | 更新部署排查 | 同步无头/有头滑块配置、运行时回退和日志保留边界。 |
| `docs/MIGRATION.md` | 更新迁移边界 | 记录知识库表初始化、日志清理和滑块依赖迁移注意事项。 |
| `docs/reports/CHANGELOG.md` | 新增日志项 | 建立本次更新详情入口。 |

[查看详情](../update-list/update-2026-09-13.md)

---

## 2026-09-10 - 项目文档基线与 AI 安全边界

**变更概述**：补齐项目概览、架构、界面、接口、依赖和统一索引；根据当前源码记录功能开关、AI 配置来源、模型服务 URL 校验、托管运行时公网 DNS 映射兼容规则和密钥展示边界，并重建 API 源码索引。

| 文档 | 变更类型 | 简介 |
| --- | --- | --- |
| `README.md` | 更新导航 | 增加文档入口和最近更新。 |
| `docs/README.md` | 新增 | 建立分类目录、阅读顺序和文档约定。 |
| `docs/guide/PROJECT_OVERVIEW.md` | 新增 | 记录项目定位、入口、目录和运行链路。 |
| `docs/modules/ARCHITECTURE.md` | 新增并更新安全边界 | 记录服务分层、功能开关、AI 安全流、部署拓扑和托管运行时公网 DNS 映射的限定放行规则。 |
| `docs/modules/INTERFACES.md` | 新增 | 记录前端页面、开关可见性和用户旅程。 |
| `docs/references/API.md` | 新增并更新校验 | 记录认证、功能开关、AI 模型和接口分组，并说明 `198.18.0.0/15` 映射仅对 DNS 主机名生效。 |
| `docs/references/DEPENDENCIES.md` | 新增 | 记录依赖、配置来源和 Docker 变体。 |
| `docs/deployment.md` | 更新安全 | 补充 AI 地址校验、模型列表权限、密钥展示规则和托管运行时 DNS 映射边界。 |
| `docs/MIGRATION.md` | 更新迁移 | 补充 AI 环境变量覆盖、密钥边界和模型地址迁移后的 DNS 映射兼容边界。 |
| `.ai/index/backend-apis.json` | 重建索引 | 按当前源码校正为 255 条路由并加入 `/ai-models`。 |

[查看详情](../update-list/update-2026-09-10.md)

---

## 2026-09-10 - README、1.1.0 与淡蓝色前端主题

**变更概述**：重写根 README，突出前端自动 AI 聊天功能，补充阿奇索自动发货搭配说明、主页面截图和 Issue 反馈入口；软件版本统一为 1.1.0，并将前端品牌主题调整为淡蓝色。

| 文档或资源 | 变更类型 | 简介 |
| --- | --- | --- |
| `README.md` | 重写 | 以卖家前端功能为主线介绍 AI 回复、知识库、消息中心、账号、商品、订单、卡密、通知和设置。 |
| `docs/screenshots/dashboard.png` | 更新 | 使用脱敏后的前端总览页面截图。 |
| `docs/guide/PROJECT_OVERVIEW.md` | 更新 | 同步 1.1.0 的自动 AI 聊天定位与阿奇索自动发货搭配方式。 |
| `frontend/`、`static/` | 更新 | 统一淡蓝色品牌变量、控件、图表、图标和构建产物；保留红色错误/危险状态色。 |

[查看详情](../update-list/update-2026-09-10.md)

---

[← 返回主文档](../../README.md)
