# 项目概览

## 项目定位

闲鱼卖家 1.1.0 是面向闲鱼卖家的本地多账号运营工作台，当前以前端自动 AI 聊天为核心，覆盖账号连接、商品、订单、消息、AI 回复、知识库、卡密、自动发货和运行日志。若使用阿奇索自动发货，可由阿奇索负责发货，本项目补充自动聊天能力。

项目以本地部署为主：FastAPI 后端同时提供管理 API 和构建后的 React 单页应用，运行数据保存在本地 SQLite 与运行目录中。

## 技术栈

| 层次 | 技术与事实源 |
| --- | --- |
| 后端 | Python 3.11+、FastAPI、Uvicorn、Pydantic、SQLite |
| 平台连接 | Playwright 1.60.0、Patchright 1.62.3、DrissionPage、WebSocket/HTTP 客户端 |
| 前端 | React 19、TypeScript、Vite、Axios、Recharts、Tailwind CSS |
| 配置 | `.env`、`global_config.yml`、系统设置表 |
| 测试 | Python `unittest`、Playwright headless、Coverage.py、TypeScript 检查和 detached Vite 构建 |
| 部署 | Docker Compose；NAS 配置使用 GHCR 预构建镜像 |

## 运行入口

1. `Start.py`：启动前检查并迁移旧数据库路径、准备 Playwright 浏览器，然后启动服务。
2. `app/reply_server.py`：创建 FastAPI 应用，注册认证、业务路由、健康检查、静态文件和 SPA 回退。
3. `XianyuAutoAsync.py`：账号连接、消息监听、订单/商品后台任务和运行时功能开关收敛。
4. `frontend/App.tsx`：前端登录、页面状态和功能页装配；生产静态产物位于 `static/`。

## 主要目录

| 路径 | 职责 |
| --- | --- |
| `app/` | FastAPI、数据库、认证、AI、知识库、功能开关和业务服务 |
| `app/routers/`、`utils/` | 路由子模块与浏览器、风控、订单等复用能力 |
| `frontend/` | React 页面、组件、API 客户端和构建脚本 |
| `static/` | 后端直接服务的前端构建产物和上传图片 |
| `tests/` | 单元、集成和 headless 浏览器测试 |
| `scripts/` | 测试编排、诊断和辅助脚本 |
| `data/` | SQLite、运行数据和本地知识库；不应提交 |
| `logs/`、`backups/`、`browser_data/` | 日志、备份和浏览器运行状态；不应提交 |
| `docs/` | 指南、架构、接口、计划、报告和测试证据 |

## 核心边界

- 功能开关只改变页面可见性、后台任务和动作执行，不删除业务数据或配置。
- 后端以 `feature_disabled` 和认证/归属校验作为实际安全边界，前端隐藏不是授权控制。
- 外部公告、AI 和商品详情服务默认不配置；只有部署者显式提供地址后才会发起请求。
- AI 模型服务地址会在服务端校验协议、URL 部分、解析结果和重定向；密钥不应出现在日志、普通用户响应或文档中。
- 自动回复、自动发货和闲鱼账号操作受平台风控影响，必须使用测试账号验证。

## 典型使用链路

```text
启动 Start.py
  → FastAPI + SPA 可访问
  → 管理员登录 / 本地免登录
  → 连接闲鱼账号
  → 同步商品、订单与消息
  → 配置规则、AI、知识库和卡密
  → 后台监听执行动作
  → 在通知与日志中核对结果
```

## 已知事实源

- [接口参考](../references/API.md) 是面向开发者的摘要。
- [全量接口目录](../references/ai-rules/05-全量接口目录.md) 与 `.ai/index/backend-apis.json` 用于 API-first 检索；当前索引由项目脚本从源码生成。
- [部署与排查](../deployment.md) 和 [自动化测试指南](自动化测试指南.md) 是操作与验证入口。
