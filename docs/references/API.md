# API 接口参考

## 基本约定

- 服务默认地址为 `http://localhost:8080`；前端使用同源请求。
- 需要认证的接口使用 `Authorization: Bearer <session-token>`。
- `/docs` 和 `/redoc` 提供 FastAPI 运行时文档；`.ai/index/backend-apis.json` 是源码检索索引。
- 完整路径、handler、认证提示和 schema 以 [全量接口目录](ai-rules/05-全量接口目录.md) 与当前源码为准；当前源码索引包含 255 条路由，且因没有独立 OpenAPI JSON，部分 schema 仍需回到 handler 核验。

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

模型查询会请求 `<base_url>/models`，不跟随重定向。地址必须是 HTTP(S)，不得包含 URL 凭据、query 或 fragment；普通 AI 请求拒绝本机、内网、链路本地、保留、多播和未指定地址。无效配置返回 400，上游失败返回不泄露供应商细节的 502。

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

## 认证与错误边界

- `401`：缺少或过期会话。
- `403`：不是管理员、账号不属于当前用户或系统模型列表权限不足。
- `409`：功能被关闭或功能开关 revision 冲突等状态冲突。
- `422`：Pydantic 请求校验或功能开关 patch 不合法。
- `502`：上游平台/模型服务失败；服务端不应把密钥、完整 Cookie、签名或上游错误原文返回给浏览器。
- AI 测试无有效回复时返回稳定的 `502` 文案；前端 `frontend/lib/request.ts` 会优先把响应中的字符串或对象 `detail.message` 映射为用户可读错误。

修改或新增接口前，先运行 API-first 索引脚本，再同步 handler、schema、认证、资源归属、前端客户端和文档。
