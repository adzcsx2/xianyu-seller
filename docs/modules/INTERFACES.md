# 界面与功能开关

## 页面入口

前端由 `frontend/App.tsx` 装配，侧边栏由 `frontend/components/Sidebar.tsx` 提供。以下页面始终可见：仪表盘、账号、消息、通知与日志、系统设置、关于。

| 页面 ID | 页面 | 主要职责 | 受控开关示例 |
| --- | --- | --- | --- |
| `items` | 商品与发货 | 商品同步、详情、发货配置 | `feature_items_enabled`、`item_sync_enabled`、`auto_delivery_enabled` |
| `orders` | 订单管理 | 订单同步、状态、手动发货 | `feature_orders_enabled`、`order_sync_enabled` |
| `buyer-interaction` | 买家互动 | 评价、求花、确认收货致谢 | `feature_buyer_interaction_enabled` |
| `cards` | 卡密库存 | 分组、库存和导入 | `feature_cards_enabled` |
| `auto-reply` | 自动回复 | 关键词与规则回复 | `feature_auto_reply_enabled` |
| `ai-reply` | AI 回复 | AI 配置、测试和自动回复 | `feature_ai_reply_enabled` |
| `knowledge-base` | 知识库 | 知识库 CRUD、商品绑定、文档上传/预览/导入和依据核对 | `feature_knowledge_base_enabled` |
| `product-automation` | 商品自动化 | 素材、筛选、删除和修复任务 | `feature_product_automation_enabled` |

## 可见性与执行语义

`frontend/contexts/FeatureFlagsContext.tsx` 拉取后端快照，`frontend/lib/featureRegistry.ts` 只保存页面和控件归属，不复制后端默认值。页面进入和侧边栏展示都使用 `effective` 状态；页面在开关关闭后会回退到仪表盘。

关闭功能的完整语义由后端保证：

- 页面入口隐藏；
- 对应写操作或后台任务返回稳定的 `409 feature_disabled`；
- 原有配置、商品、订单、卡密、知识库和日志保留；
- 重新开启后，仍保留的配置可以继续使用。

## 高风险交互

- 账号登录、扫码、人工滑块和 Cookie/Token 恢复会接触真实账号状态。
- 自动回复、AI 回复、自动发货、商品自动化和订单手动发货会触发外部或业务动作。
- 管理员设置包含登录、注册、SMTP、AI、备份和功能开关；前端展示不替代后端权限校验。
- API Key、密码、Cookie、验证码、聊天/订单数据和卡密只允许在本地运行时使用，不得放入截图、测试 fixture 或文档。

## 账号验证交互

- 账号登录和 Token 刷新遇到滑块时，系统先尝试自动验证；只有取得有效 `x5sec` Cookie 才更新会话，视觉上拖动成功但未取得服务端票据仍提示失败。
- 自动验证失败后，账号处于风控状态时才显示「人工验证」。人工会话会暂停该账号的自动刷新，成功后清理旧挑战 Cookie、更新本地会话并重启账号；非风控账号调用人工验证会被拒绝。

## 通知与日志页

管理员在「通知与日志」中可进入「系统日志」标签：按全部/最近时间段/自定义时间、日志级别和来源筛选；首批显示最新 1000 条，滚动到底部加载更早记录。页面默认每 30 秒刷新一次，也支持手动刷新；刷新或加载更多正在进行时不会并发覆盖当前结果。

「清空日志」需要二次确认，清空文件和内存缓冲且不可恢复。应用文件日志和验证码日志按天轮转并保留最近 7 天，测试产物也遵循 7 天清理策略。

## 典型用户旅程

```text
登录 → 账号连接 → 商品/订单同步 → 配置规则与知识库
     → 开启需要的后台任务 → 消息/订单触发动作 → 通知与日志核对
```

知识库文档的普通用户路径是：打开全局知识库 → 上传 Markdown/TXT → 预览并勾选章节 → 确认这些章节可成为买家可见事实 → 导入 → 在来源卡片核对关联数和 AI 可用数 → 用问答区查看“本次提供给 AI 的依据”。仅在“来源引用”里填写类似 `README.md：产品简介` 的标题会明确显示“仅引用记录 · 未上传文件”。内部键由系统生成，创建条目时无需填写。

## 前端与 API 的兼容约束

- `frontend/services/api.ts` 是前端 API 调用集中入口；修改后端响应字段时要同步类型和页面状态处理。
- `/feature-flags` 的 revision 冲突必须提示用户刷新快照，不应静默覆盖其他管理员的修改。
- AI 模型下拉框只展示模型 ID；普通账号响应不能依赖 API Key 原文。
- 生产页面来自 `static/`，前端变更完成后必须重新构建并通过 detached build 检查。
