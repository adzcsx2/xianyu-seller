# API 接口参考

## 基本约定

- 服务默认地址为 `http://localhost:8080`；前端使用同源请求。
- 需要认证的接口使用 `Authorization: Bearer <session-token>`。
- `/docs` 和 `/redoc` 提供 FastAPI 运行时文档；`.ai/index/backend-apis.json` 是源码检索索引。
- 完整路径、handler、认证提示和 schema 以 [全量接口目录](ai-rules/05-全量接口目录.md) 与当前源码为准；当前源码索引包含 252 条路由，且因没有独立 OpenAPI JSON，部分 schema 仍需回到 handler 核验。

## 入口接口

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/health` | 无需登录 | 检查 Cookie 管理器、SQLite 和系统资源；异常返回 503。 |
| `GET` | `/system-settings/public` | 无需登录 | 返回登录、注册和验证码等公开设置，不含敏感值。 |
| `POST` | `/login` | 无需登录 | 支持管理员/用户凭据、邮箱验证码和关闭登录校验时的本地自动会话。 |
| `POST` | `/logout` | 已认证 | 清理当前会话。 |
| `GET` | `/` | 无需登录 | 返回前端 SPA 入口。 |

## 功能开关

### `GET /feature-flags`

已认证用户可读。响应包含 `revision`、`configured`、`effective`、开关定义和警告；不包含密钥、Cookie 或业务数据。

### `PUT /feature-flags`

仅管理员可写，使用 revision 保护的 partial patch。请求核心字段：

```json
{
  "expected_revision": 3,
  "flags": {
    "feature_ai_reply_enabled": false
  }
}
```

- `200`：持久化并返回最新快照、变更 key 和运行时应用状态。
- `409`：`feature_revision_conflict`，说明客户端基于过期快照更新。
- `422`：`invalid_feature_flag`，未知 key、非 Boolean 值或非法 patch。
- 被关闭的业务动作统一返回 `409`，错误码为 `feature_disabled`。

## AI 配置与模型

| 方法 | 路径 | 认证/归属 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/ai-reply-settings/{cookie_id}` | 已认证 + 账号归属 | 读取指定账号 AI 设置；普通用户只看到密钥状态，管理员受保护响应可查看部署级密钥。 |
| `PUT` | `/ai-reply-settings/{cookie_id}` | 已认证 + 账号归属 | 更新账号 AI 设置；受 `feature_ai_reply_enabled` 门禁。 |
| `GET` | `/ai-reply-settings` | 已认证 | 返回当前用户所有账号设置，遵循同样的密钥展示规则。 |
| `POST` | `/ai-reply-test/{cookie_id}` | 已认证 + 账号归属 | 使用真实商品上下文隔离测试 AI 回复，不进入买家会话；受 AI 开关门禁。上游无有效回复时返回 502 和稳定的用户可读错误文案。 |
| `GET` | `/ai-models?cookie_id=...` | 已认证 + 账号归属 | 查询指定账号当前生效 OpenAI 兼容服务的模型 ID。 |
| `GET` | `/ai-models` | 管理员 | 查询系统级模型列表；普通用户返回 403。 |

模型查询会请求 `<base_url>/models`，不跟随重定向。地址必须是 HTTP(S)，不得包含 URL 凭据、query 或 fragment；普通 AI 请求拒绝本机、内网、链路本地、保留、多播和未指定地址。托管运行时若将公网 DNS 结果映射到 `198.18.0.0/15`，仅 DNS 主机名的该映射可继续访问，直接填写字面量 IP 仍会被拒绝。无效配置返回 400，上游失败返回不泄露供应商细节的 502。

## 业务接口分组

| 分组 | 典型路径 | 主要副作用 |
| --- | --- | --- |
| 账号与登录 | `/cookies`、`/password-login`、`/qr-login` | 登录、Cookie 恢复、账号状态和后台监听 |
| 商品与发货 | `/items`、`/delivery-rules`、`/item-reply` | 本地商品、同步、规则和发货动作；`POST /items` 不是闲鱼发布接口 |
| 订单 | `/api/orders`、`/orders` | 同步、状态、手动发货、物流和导入 |
| 消息 | `/chat`、`/send-message`、`/message-filters` | 读取/发送消息、过滤和通知 |
| 卡密 | `/cards` | 库存、分组、导入和分配 |
| 知识库 | `/knowledge-bases` | 全局知识、商品绑定、预览和问答 |
| 商品自动化 | `/product-automation` | 素材、筛选、删除、修复和运行记录 |
| 管理与备份 | `/admin/*`、`/backup/*` | 管理数据、日志、备份导入导出；高风险操作需管理员或归属权限 |
| 验证码与风控 | `/api/captcha/*`、`/api/risk-control/*` | 人工验证会话、截图、鼠标事件和风控状态 |

## 系统日志接口

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/logs` | 仅管理员 | 按最新记录向前返回分页日志；支持 `lines`（服务端限制最多 1000）、`offset`、`level`、`source`、`start_time` 和 `end_time`，响应包含 `total`、`limit`、`offset`、`has_more`。 |
| `GET` | `/logs/stats` | 仅管理员 | 返回当前收集器中的总量、级别统计、来源统计、容量和日志文件位置。 |
| `POST` | `/logs/clear` | 仅管理员 | 清空候选日志文件、内存缓冲和增量读取状态；操作不可恢复。 |

`/logs` 的时间参数接受 ISO 8601 时间；开始时间晚于结束时间返回 `400`。日志正文中的多行 traceback 会并入首条记录，保留原始时间、级别和来源，避免刷新时拆成新的系统事件。

## 知识库文档闭环

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` / `POST` | `/knowledge-bases/{base_id}/documents` | 列出文档元数据，或上传不超过 512 KiB 的 UTF-8 Markdown/TXT；相同内容重复上传返回既有文档。 |
| `GET` | `/knowledge-bases/{base_id}/documents/{document_id}` | 用户主动打开预览时返回确定性解析的章节；列表接口不返回正文。 |
| `POST` | `/knowledge-bases/{base_id}/documents/{document_id}/imports` | 把用户明确选择的章节一次性导入为启用事实，并自动关联文档来源。 |
| `DELETE` | `/knowledge-bases/{base_id}/documents/{document_id}` | 删除未使用文档；有关联时返回分型 409，只有显式选择才会连同自动导入的事实删除。 |

来源标题本身不代表文件已经上传。旧来源会返回 `metadata_only`，文档来源会返回解析/导入状态、关联条目数和运行时启用数。知识库问答与商品预览的 `provided_evidence` 只列出本次实际提供给 AI 的安全来源摘要，不包含原始正文、备注、本地路径或内部规则。

知识库写操作使用聚合 `expected_version`。冲突响应在 `detail` 中提供稳定的 `error_code`，包括 `knowledge_version_conflict`、`knowledge_source_in_use`、`knowledge_document_in_use` 和 `knowledge_validation_error`。

## 验证码与风控接口

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| `POST` | `/api/captcha/manual-session` | 已认证 + 账号归属 | 以表单启动人工验证；仅风控中的账号可用，`timeout` 会限制在 60～900 秒。成功后服务端清理旧挑战 Cookie、保存新 Cookie、尝试重启账号并解除风控状态。 |
| `POST` | `/api/risk-control/{cookie_id}/fresh-captcha-url` | 已认证 + 账号归属 | 使用当前 Cookie 获取一次性新验证链接；若风控已解除则返回 `need_verify=false`。 |
| `GET` | `/api/risk-control/status` | 已认证 | 返回当前用户账号的风控熔断、验证类型、冷却和人工验证状态。 |

自动滑块结果只有包含有效 `x5sec` Cookie 才会写回账号；仅视觉通过、只有挑战标记或未返回 Cookie 都按失败处理，并提示人工验证。验证链接和 Cookie 属于实时账号数据，不应写入文档、日志或测试 fixture。

## 认证与错误边界

- `401`：缺少或过期会话。
- `403`：不是管理员、账号不属于当前用户或系统模型列表权限不足。
- `409`：功能被关闭或功能开关 revision 冲突等状态冲突。
- `422`：Pydantic 请求校验或功能开关 patch 不合法。
- `502`：上游平台/模型服务失败；服务端不应把密钥、完整 Cookie、签名或上游错误原文返回给浏览器。
- AI 测试无有效回复时返回稳定的 `502` 文案；前端 `frontend/lib/request.ts` 会优先把响应中的字符串或对象 `detail.message` 映射为用户可读错误。

修改或新增接口前，先运行 API-first 索引脚本，再同步 handler、schema、认证、资源归属、前端客户端和文档。
