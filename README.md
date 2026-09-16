# 闲鱼卖家

一个面向闲鱼卖家的本地运营工作台，当前版本 `1.1.0`。项目的核心方向是：让 AI 根据商品知识和账号配置，自动参与买家聊天，减少重复回复和人工盯盘。项目定位以本地自动 AI 聊天和运营辅助为主。

如需自动发货，**建议使用阿奇索负责发货，本项目专注自动 AI 聊天**，用来补充阿奇索暂未覆盖的自动聊天能力。

> 本项目 fork 自 [23Star/xianyu-super-butler](https://github.com/23Star/xianyu-super-butler)，仅用于保留直接来源说明。

## 前端功能

前端是一个 React + TypeScript 的卖家控制台，登录后从左侧导航进入各项功能：

- **AI 回复**：为不同闲鱼账号配置 OpenAI 兼容模型、回复风格、上下文和启停状态，并可在页面内测试回复效果。
- **知识库**：维护商品事实、来源、业务规则和问答内容；支持上传 UTF-8 编码的 Markdown/TXT 文档，预览后按章节导入，并在知识库问答中显示本次提供给 AI 的依据。
- **消息中心**：查看买家会话、读取聊天记录并进行人工补充回复；适合处理 AI 不确定或需要人工确认的消息。
- **账号管理**：扫码登录、Cookie 恢复、连接状态、风控状态和账号级 AI 配置集中管理；遇到滑块验证时自动尝试处理，仅在取得有效验证 Cookie 后更新会话，失败时提示人工处理。
- **商品管理**：同步商品并查看商品状态，作为 AI 理解商品信息和参与买家聊天的基础。
- **订单管理**：查看订单和同步交易状态；自动发货由阿奇索负责，本项目不执行自动发货动作。
- **总览与通知**：通过经营数据、运行日志和通知快速了解账号、消息、订单及任务状态；系统日志支持按时间、级别和来源筛选、分批加载、30 秒自动刷新及手动清空，并自动保留最近 7 天记录。
- **系统设置**：按需启用或关闭商品、订单、AI 回复、知识库、消息等功能，并配置公告和部署参数。

### 前端主要页面

![闲鱼卖家前端总览页面](docs/screenshots/dashboard.png)

## 前置环境

根据运行方式准备以下环境：

- 本地源码运行：Python 3.11+、Node.js 20+（包含 npm）、Git，以及 Playwright Chromium。
- Docker 运行：Docker Engine 或 Docker Desktop，以及 Docker Compose v2；首次构建需要能访问镜像、PyPI、npm 和 Playwright 下载源。
- 国内网络环境：使用 `docker-compose-cn.yml`，它会切换 apt、pip、npm 和 Playwright 镜像源。
- NAS 预构建镜像：设备需要能拉取 `ghcr.io/adzcsx2/xianyu-seller:latest`，不需要在 NAS 上安装 Python 或 Node.js。

不要把密码、Cookie、Token、二维码、聊天记录、订单数据或知识库内容放进 Git 跟踪的文件中。`.env`、运行数据库和运行目录均用于本机配置或持久化，已经加入忽略规则。

## 快速开始

### 本地源码运行（Windows PowerShell）

```powershell
git clone https://github.com/adzcsx2/xianyu-seller.git
Set-Location xianyu-seller

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
python Start.py
```

`Start.py` 会在启动前检查 `frontend` 源码和 `static/index.html` 的更新时间：源码更新时自动执行 `npm ci` 和 `npm run build`，未更新时跳过构建。Windows 下会自动解析 `npm.cmd`；如果构建失败，程序会停止启动，避免继续使用旧前端产物。服务启动后访问 <http://127.0.0.1:8080/>，按 `Ctrl+C` 停止。

如需手动重新构建：

```powershell
Set-Location frontend
npm ci
npm run build
Set-Location ..
```

可通过环境变量修改本地监听地址和端口，例如：

```powershell
$env:API_HOST = '127.0.0.1'
$env:API_PORT = '8081'
python Start.py
```

### Docker Compose（本机构建）

先复制并编辑环境配置，至少设置一个强管理员密码：

```bash
cp .env.example .env
# 编辑 .env，修改 ADMIN_PASSWORD，并填写需要的 AI 配置
docker compose up -d --build
docker compose ps
docker compose logs -f xianyu-app
```

Dockerfile 会在镜像构建阶段编译前端，因此本机构建 Docker 镜像不依赖宿主机的 Python、Node.js 或 npm。`data/`、`logs/` 和 `backups/` 会通过绑定挂载保留在宿主机；停止服务不会删除这些目录。

停止服务：

```bash
docker compose down
```

国内网络环境：

```bash
docker compose -f docker-compose-cn.yml up -d --build
```

启动后访问 <http://127.0.0.1:8080/>。主 Compose 文件和国内 Compose 文件都会默认开启登录验证；生产或公网部署必须在 `.env` 中设置强密码，不要使用示例默认值。

如需同时启动可选的 Nginx（80/443 端口），使用：

```bash
docker compose --profile with-nginx up -d --build
```

### NAS / 不在本机构建

此配置使用 GitHub Container Registry 的预构建镜像，不会在 NAS 上执行 npm、pip 或 Chromium 构建：

```bash
docker compose -f docker-compose.nas.yml pull
docker compose -f docker-compose.nas.yml up -d
```

NAS 配置默认开启登录验证。部署前通过 `.env` 或 shell 环境变量设置管理员密码，例如：

```bash
ADMIN_PASSWORD='请替换为强密码' docker compose -f docker-compose.nas.yml up -d
```

NAS 配置使用 `latest` 预构建镜像，源码修改不会自动进入容器；需要最新源码时，请使用本机构建的 Compose 配置，或先在其他机器构建并发布镜像。

检查 Compose 文件：

```bash
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose-cn.yml config --quiet
docker compose -f docker-compose.nas.yml config --quiet
```

## 使用建议

1. 在「账号管理」登录并确认闲鱼账号处于在线状态。
2. 在「知识库」录入商品事实、价格、售后规则和常见问答。
3. 在「AI 回复」为账号配置可信的模型服务，并先使用测试功能确认回复风格。
4. 在「消息中心」观察实际聊天效果，必要时切换人工回复。
5. 如需自动发货，请在阿奇索中配置；本项目只负责自动 AI 聊天，不执行自动发货。

自动回复、账号操作和平台交互可能触发平台风控。请先使用测试账号验证，并妥善保管 Cookie、Token、聊天记录和订单等私密数据。

## 数据、知识库与 GitHub

知识库内容属于私有业务数据。运行时数据库、上传文档和其他账号数据应只保存在 `data/`、本地运行目录或其他被忽略的运行路径中；`app/knowledge/` 只保留知识库实现代码，不用于存放业务内容。

当前仓库已通过以下措施阻止知识库内容进入 GitHub 或 Docker 构建上下文：

- `.gitignore` 排除 `data/`、`app/knowledge/` 中的内容，以及数据库和运行状态文件。
- `.dockerignore` 排除上述运行数据，即使执行 `COPY . .` 也不会把它们放入镜像构建上下文。
- GitHub Actions 只处理 Git 中已跟踪的源码来构建镜像，不会读取本机 `data/`、日志、浏览器状态或知识库运行数据；发布前还会检查禁止路径，发现被跟踪就直接失败。

提交前可检查：

```bash
git status --short
git ls-files | grep -E '(^|/)(data|knowledge|knowledge_base|browser_data|logs)/|\.(db|sqlite|sqlite3)$'
```

不要使用 `git add -f` 强行添加这些路径；如果某个私有文件曾经被跟踪过，仅添加 `.gitignore` 不会从历史中删除它，需要先备份，再执行针对该文件的 `git rm --cached` 并检查 Git 历史。

## 问题反馈

使用中有问题、发现缺陷或有功能建议，请提交 [Issue](https://github.com/adzcsx2/xianyu-seller/issues)，并尽量附上复现步骤、运行环境和脱敏后的日志。请不要在 Issue 中提交密码、Cookie、Token、二维码、订单或聊天记录。

## 文档与许可证

- [文档索引](docs/README.md)
- [项目概览](docs/guide/PROJECT_OVERVIEW.md)
- [部署与排查](docs/deployment.md)
- [自动化测试指南](docs/guide/自动化测试指南.md)

本项目使用 [GNU Affero General Public License v3.0](LICENSE)。修改、部署或通过网络向用户提供服务时，请遵守 AGPL-3.0 的相关义务。
