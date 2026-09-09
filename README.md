# 闲鱼超级管家 · 知识库增强版

面向闲鱼卖家的多账号运营与自动化管理工具，提供商品、订单、消息、自动回复、自动发货和 AI 知识库的一体化后台。

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-19-149ECA?logo=react&logoColor=white)](https://react.dev/)
[![License](https://img.shields.io/badge/License-AGPL--3.0-222222)](LICENSE)
[![Upstream](https://img.shields.io/badge/Upstream-23Star%2Fxianyu--super--butler-f5b301?logo=github)](https://github.com/23Star/xianyu-super-butler)

> 本项目 fork 自 [23Star/xianyu-super-butler](https://github.com/23Star/xianyu-super-butler)，在保留原有自动化能力的基础上，加入了全局知识库、商品知识绑定等个人增强功能。感谢上游项目及其贡献者的开源工作。

## 本次更新

- **人工滑块流程更稳定**：检测到滑块验证后暂停自动重试，等待账号管理页人工处理；验证完成后可使用新的 Cookie 恢复账号任务。
- **登录会话更安全**：默认启用管理员登录，支持通过 `SESSION_TIMEOUT_SECONDS` 配置会话有效期；免登录模式仍仅适用于可信内网。
- **远程验证接口加强保护**：验证码 HTTP 与 WebSocket 接口统一使用登录会话认证，并校验验证会话归属，避免跨账号访问。
- **敏感日志脱敏**：不再输出 Cookie 值，仅记录必要的字段名和数量；同时补充了登录、人工滑块、远程验证和依赖安全相关测试。

![闲鱼超级管家运营概览](docs/screenshots/revenue-overview.png)

## 项目特色

- **多账号统一管理**：扫码、密码或 Cookie 接入账号，分别配置监听、回复与自动化策略。
- **商品与订单管理**：同步商品和历史订单，集中查看状态、金额、库存及发货情况。
- **自动发货**：支持卡密库存、多规格、多数量发货和发货前风险拦截。
- **双层自动回复**：关键词规则负责确定性回复，兼容 OpenAI 协议的模型负责自然语言回复。
- **全局知识库**：维护事实、来源、内部规则和公开问答，并将同一知识库复用于多个商品。
- **买家互动**：支持自动确认、自动评价、求小红花和收货后致谢。
- **商品自动化**：提供素材、发布记录、定时任务、擦亮及上下架相关能力。
- **运营后台**：在一个界面查看营收、账号、订单、会话、通知和运行日志。

## 知识库增强

知识库是本分支相对上游的主要增强能力。进入后台的「知识库」页面后，可以：

1. 创建可跨商品复用的全局知识库；
2. 分别维护买家可见事实、来源引用、内部规则和公开问答；
3. 为不同账号下的商品绑定一个或多个知识库；
4. 使用当前账号配置的 AI 模型测试知识库问答；
5. 将匹配到的知识内容安全地注入 AI 回复上下文。

知识库正文属于本地业务数据，默认保存在 `data/xianyu_data.db`。`data/`、`app/knowledge/` 中的本地知识文件、已登录账号资料以及运行日志均已加入 `.gitignore`，不会作为仓库内容提交。请仍然在推送前检查 `git status`，避免通过强制添加误传商品资料、内部规则、客户信息、Cookie 或密钥。

## 功能概览

| 模块 | 主要能力 |
| --- | --- |
| 总览 | 营收、订单、账号、卡密库存和服务状态 |
| 账号 | 登录、资料同步、监听控制及账号级自动化设置 |
| 商品 | 商品同步、本地信息、图片、规格和商品回复 |
| 订单 | 历史订单拉取、状态刷新、详情补全、手动或自动发货 |
| 卡密 | 分组、批量导入、库存状态、多规格与多数量发货 |
| 自动回复 | 关键词、默认回复、回复次数控制和 AI 回复 |
| 知识库 | 全局知识管理、商品绑定、规则匹配和 AI 问答测试 |
| 消息 | 跨账号会话、消息收发、搜索筛选和回复决策记录 |
| 自动化 | 商品任务、买家互动、通知和备份 |

## 快速开始

### Docker Compose（推荐）

需要 Docker 与 Docker Compose。当前分支包含自定义功能，应从源码构建镜像：

```bash
git clone https://github.com/adzcsx2/xianyu-seller.git
cd xianyu-seller
cp .env.example .env
docker compose up -d --build
```

国内网络环境可使用：

```bash
docker compose -f docker-compose-cn.yml up -d --build
```

启动后访问 `http://localhost:8080/`。如需启用 Nginx：

```bash
docker compose --profile with-nginx up -d --build
```

Windows PowerShell 复制环境文件时使用：

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

### 源码运行

需要 Python 3.11+、Node.js 20+ 和 npm：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
playwright install chromium

Set-Location frontend
npm ci
npm run build
Set-Location ..

python Start.py
```

### 默认入口

- 管理后台：`http://localhost:8080/`
- API 文档：`http://localhost:8080/docs`
- 健康检查：`http://localhost:8080/health`

默认管理员账号为 `admin`，密码为 `admin123`。首次启动后请立即在后台修改密码，或在 `.env` 中设置 `ADMIN_USERNAME` 与 `ADMIN_PASSWORD`。

默认 `ADMIN_LOGIN_ENABLED=true`，登录会话按 `SESSION_TIMEOUT_SECONDS` 过期（默认 86400 秒）。设为 `false` 时，前端不显示登录页，而是使用 `.env` 中的 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 对应管理员自动建立永久会话；该模式只适用于可信内网。

## 使用流程

1. 登录后台并修改默认管理员密码；
2. 在「账号」页面接入闲鱼账号并启动监听；
3. 同步商品与订单，按需导入卡密和配置发货规则；
4. 配置关键词回复或兼容 OpenAI 协议的 AI 模型；
5. 在「知识库」中创建内容，再绑定到对应商品；
6. 先通过测试与预览确认回复效果，再开启自动回复或自动发货。

滑块、人机验证和部署问题参见 [部署文档](docs/deployment.md)。平台风控策略可能变化，自动验证无法保证始终成功，必要时请切换为人工验证。

## 数据目录

| 路径 | 内容 | Git 策略 |
| --- | --- | --- |
| `data/` | SQLite 数据库、账号和业务数据、知识库正文 | 忽略 |
| `logs/` | 应用、诊断和测试日志 | 忽略 |
| `backups/` | 本地数据库备份 | 忽略 |
| `browser_data/` | 浏览器会话与登录状态 | 忽略 |
| `slider_cookies/` | 滑块验证过程中产生的 Cookie 快照 | 忽略 |
| `app/knowledge/` | 可选的本地知识种子或导入内容 | 内容忽略，仅保留程序文件 |

Docker Compose 已将 `data/`、`logs/` 和 `backups/` 挂载到宿主机。升级或重建容器前请备份这些目录，但不要把备份提交到 Git。

## 更新

```bash
git pull
docker compose up -d --build
```

更新前建议备份 `data/`，并查看本分支与上游的数据库迁移说明。不要直接用上游预构建镜像覆盖本分支，否则本分支新增的前后端功能不会包含在镜像中。

## 开发与验证

```powershell
# 查看可用测试套件
python scripts/run_tests.py --list

# 核心回归
python scripts/run_tests.py --suite core --database snapshot

# 完整本地质量检查
python scripts/run_tests.py --quality --database snapshot
```

前端源码位于 `frontend/`，FastAPI 后端主要位于 `app/`，应用入口为 `Start.py`。测试产生的日志统一写入 `logs/test-artifacts/`。

## 安全与使用声明

- 不要提交 `.env`、数据库、知识库正文、日志、Cookie、密码、令牌、浏览器登录状态、二维码、卡密或任何真实账号与客户数据。
- 不要将免登录的管理后台直接暴露到公网。
- 自动回复、自动发货及账号操作具有业务风险，正式使用前请先用测试账号验证规则。
- 本项目仅供学习、研究和合法自动化使用。使用者应遵守所在地法律法规及闲鱼平台规则，并自行承担使用风险。

## 上游与许可证

- 本分支上游：[23Star/xianyu-super-butler](https://github.com/23Star/xianyu-super-butler)
- 上游所基于的原始项目：[zhinianboke/xianyu-auto-reply](https://github.com/zhinianboke/xianyu-auto-reply)
- 开源许可证：[GNU Affero General Public License v3.0](LICENSE)

修改、部署或通过网络向用户提供本项目服务时，请遵守 AGPL-3.0 的相关义务。上游项目的商标、名称和社区渠道不代表其为本分支提供官方支持。
