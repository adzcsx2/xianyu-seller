# 架构说明

## 分层关系

```text
React/Vite 前端
  ├─ App.tsx / Sidebar.tsx：登录、页面和功能开关可见性
  ├─ components/：账号、商品、订单、消息、AI、知识库等页面
  └─ services/api.ts：同源 HTTP API 客户端
          ↓ Bearer 会话
FastAPI 应用（app/reply_server.py）
  ├─ 认证与权限：会话 TTL、管理员依赖、账号归属
  ├─ 业务路由：商品、订单、消息、卡密、知识库、自动化
  ├─ 功能开关：registry → SQLite revision → runtime apply
  └─ 静态文件：static/、SPA catch-all
          ↓
领域服务与后台运行时
  ├─ db_manager.py：SQLite、迁移、备份和配置持久化
  ├─ file_log_collector.py：文件日志快照、增量读取、筛选和分页
  ├─ XianyuAutoAsync.py：账号连接、消息监听、后台任务
  ├─ ai_reply_engine.py / ai_models.py：AI 配置、模型发现和回复
  ├─ knowledge_runtime.py / product_knowledge.py：知识库检索与商品绑定
  └─ utils/：浏览器、登录、滑块、订单、风控、日志保留和通知工具
```

## 功能开关模型

`app/feature_flags.py` 定义不可变、有序的开关注册表。每个定义包含 key、默认值、分组、说明、依赖、UI 目标和风险等级。

- `GET /feature-flags`：任何已认证用户读取非敏感快照。
- `PUT /feature-flags`：仅管理员用 `expected_revision` 做 partial patch 原子更新。
- 依赖开关按拓扑顺序计算 `effective`；父开关关闭时，子功能即使配置为真也不会生效。
- 保存后由运行时应用；配置已持久化但实例无法立即收敛时，响应和日志会反映 pending/failed 状态。
- 业务入口还会执行服务端 `_require_feature_enabled`，因此关闭功能不能仅靠前端绕过。

当前开关覆盖商品、订单、卡密、买家互动、自动回复、AI 回复、知识库、商品自动化，以及资料同步、Token 刷新和 Cookie 刷新等后台行为。

## AI 配置与安全流

AI 配置按“账号持久化设置优先，部署环境变量兜底”解析：

```text
账号设置 / 系统设置
          ↓ 空字段才叠加
API_KEY + MODEL_BASE_URL + MODEL_NAME
          ↓
validate_model_service_url
          ↓
OpenAI 兼容客户端或 GET /models
```

- 系统设置响应使用 `ai_env_overrides` 只标记来源，不回传环境变量值。
- 普通账号读取 AI 设置只返回 API Key 已配置状态；管理员受保护的设置响应才可查看部署级密钥。
- 系统级 `/ai-models` 仅管理员可访问；账号级查询必须通过当前用户的账号归属检查。
- 服务端禁止非 HTTP(S) URL、凭据/query/fragment、无法解析的主机、私有/本机地址和 HTTP 重定向；托管运行时将公网 DNS 结果映射到 `198.18.0.0/15` 时，仅对 DNS 主机名放行该映射，字面量 IP 仍按 SSRF 规则拦截；上游错误不把 URL、密钥或供应商原文返回给前端。

## 知识库文档流

```text
上传 UTF-8 Markdown/TXT
  → 本地确定性解析与分段
  → 文档/章节元数据写入 SQLite
  → 用户显式选择章节
  → 一次性导入为启用事实并建立来源关系
  → AI 检索时生成无私密字段的 provided_evidence
```

- `app/knowledge_documents.py` 只处理上传字节，不访问文件系统、网络、浏览器或模型；支持 Markdown 标题路径和 TXT 段落分段，单文档上限为 512 KiB、1000 个章节、单章节 800 字符。
- 数据库保留文档摘要、章节 checksum、导入映射和来源状态；列表不返回正文，只有用户主动打开详情时才返回解析章节。
- 重复内容按 checksum 幂等处理；写操作使用知识库 `expected_version`，删除有关联文档时要求显式确认是否删除自动导入事实。
- `provided_evidence` 只说明本次送入 AI 的来源标题、内容类型和文档状态，不暴露正文、备注、本地路径或内部规则。

## 数据与后台任务

- SQLite 默认位于 `data/xianyu_data.db`，启动时执行必要的路径迁移和数据库迁移。
- Cookie、账号连接、商品、订单、消息、AI 设置、知识库和功能开关均通过数据库或本地运行目录持久化。
- 日志写入 `logs/`，数据库备份写入 `backups/`；测试运行会在 `logs/test-artifacts/` 生成隔离产物。应用日志按天轮转并保留 7 天，验证码日志也按天写入并由同一策略清理。
- `FileLogCollector` 维护最多 10000 条内存记录，按日志级别、来源和时间范围去重筛选；接口从最新记录向前按 `offset` 分页，文件追加时优先读取新增字节，截断或轮转时才完整重读。
- 账号运行时由 `XianyuLive` 管理连接状态、消息与订单监听、Token/Cookie 刷新、自动回复和自动发货任务。后台任务读取 `effective` 功能快照决定是否启动或停止对应行为。

## 滑块验证链路

账号登录和 Token 刷新共用兼容运行时：优先加载 `slidex`，缺失时回退本地实现；自动求解失败后可按配置尝试 DrissionPage 或远程/人工会话。所有引擎都经过 `slider_orchestrator` 归一化，只有拿到真实 `x5sec` Cookie 才算成功；仅视觉拖动成功、只有 `x5secdata`/`x5sectag` 或未返回 Cookie 均判定失败。

验证成功时只合并新的 x5 相关 Cookie，并清除旧挑战标记后更新账号会话；验证失败不写回 Cookie，账号转人工处理并记录可脱敏的验证日志。轨迹池按账号安全键存储，不能通过账号标识穿越运行数据目录。

## 部署拓扑

默认 Compose 运行 `xianyu-app`，将本地数据、日志和备份挂载到容器；可选 `nginx` 使用 `with-nginx` profile。源码构建负责前端静态产物，NAS Compose 直接拉取 `ghcr.io/adzcsx2/xianyu-seller:latest`。

## 变更注意事项

- 新增或修改后端接口前，先更新 `.ai/index/backend-apis.json` 并核对源码 handler、schema、认证和资源归属。
- 修改开关时必须同时检查后端 registry、运行时任务门禁、前端 UI registry、页面降级和测试合同。
- 任何会触发闲鱼外部动作的服务都应通过既有 manager/service 或显式 seam，纯业务函数不要直接创建外部客户端。
- 修改知识库文档、日志分页或滑块验证时，必须同步检查数据库/文件生命周期、前端状态竞态、敏感数据脱敏和对应的 headless 测试合同。
