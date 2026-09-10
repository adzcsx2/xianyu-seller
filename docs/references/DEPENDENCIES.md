# 依赖与配置

## 运行时依赖

Python 依赖的事实源是 [`requirements.txt`](../../requirements.txt)，测试工具在 [`requirements-test.txt`](../../requirements-test.txt)，前端依赖和锁文件在 [`frontend/package.json`](../../frontend/package.json) 与 `frontend/package-lock.json`。

| 类别 | 依赖/配置 | 用途 |
| --- | --- | --- |
| Web | FastAPI、Uvicorn、Pydantic | API、认证和静态文件服务 |
| 本地数据 | SQLite、PyYAML | 业务数据、系统设置和 YAML 配置 |
| 浏览器 | Playwright `1.60.0`、Patchright `1.62.3`、DrissionPage | 登录、滑块、人机验证和闲鱼页面连接 |
| 网络 | `requests`、`httpx`、`aiohttp`、`websockets` | 平台 API、AI 服务和 WebSocket |
| AI | `openai` | OpenAI 兼容回复客户端 |
| 媒体/数据 | Pillow、qrcode、pandas、openpyxl、xlsxwriter | 图片、二维码、表格导入导出 |
| 安全 | PyJWT、passlib/bcrypt、cryptography | 会话、密码和加密能力 |
| 前端 | React 19、TypeScript、Vite、Axios、Recharts、Tailwind CSS | 管理后台和构建 |

## 版本与安装

- Python 要求 3.11+，Node.js 要求 20+。
- Playwright 与 Chromium revision 绑定；安装或升级 Playwright 后必须执行 `playwright install chromium`。
- 常规测试安装 `pip install -r requirements-test.txt` 和 `npm --prefix frontend ci`。
- Nuitka 等打包工具只在 `requirements-build.txt` 中维护，不属于服务运行时必要依赖。

## 配置来源

| 来源 | 典型内容 | 优先级/边界 |
| --- | --- | --- |
| `.env` | 管理员登录、端口、会话、AI 部署默认值、资源限制 | 容器/部署级；不要提交真实密钥 |
| `global_config.yml` | 闲鱼平台端点、心跳、同步周期、日志和浏览器参数 | 项目默认配置；修改后重启生效 |
| SQLite `system_settings` | 功能开关、系统设置、迁移后的持久化值 | 运行时事实源；管理员界面修改 |
| 账号设置表 | Cookie、账号 AI 设置、规则和业务数据 | 当前用户/账号归属隔离 |

AI 三项部署变量为 `API_KEY`、`MODEL_BASE_URL`、`MODEL_NAME`。空的账号级字段才使用环境变量覆盖；页面通过 `ai_env_overrides` 识别来源，但普通响应不暴露密钥。

## Docker 变体

- `docker-compose.yml`：源码构建 `xianyu-app`，可选 Nginx profile。
- `docker-compose-cn.yml`：使用国内镜像源构建，适合国内网络环境。
- `docker-compose.nas.yml`：拉取 GHCR 预构建镜像，适合 NAS 或低配设备。
- 数据、日志和备份应挂载到宿主机并在升级前备份。

## 安全和维护

- 不要将真实 Cookie、Token、密码、API Key、买家消息、订单、卡密、知识库或浏览器状态放进依赖报告和示例。
- 平台外部 URL 和 AI 服务地址必须显式配置并经过服务端校验；空配置不会自动请求维护者服务。
- 依赖升级要同步验证浏览器版本、登录、消息、商品、订单和 AI 流程。
- 项目未配置独立 ESLint/Ruff 命令；质量入口由 [`scripts/run_tests.py`](../../scripts/run_tests.py) 统一编排。
