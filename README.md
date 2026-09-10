# 闲鱼卖家

面向闲鱼卖家的本地多账号运营工作台，覆盖账号、商品、订单、消息、自动回复、知识库、卡密和自动发货。聊天核心可以在关闭其他可选业务后独立运行。

> 本项目 fork 自 [23Star/xianyu-super-butler](https://github.com/23Star/xianyu-super-butler)，仅用于保留直接来源说明。

## 功能

- 账号扫码、Cookie 和登录恢复，以及资料同步和连接状态管理。
- 商品与订单同步、卡密库存、发货规则和风险拦截。
- 消息中心、手动收发、关键词回复、AI 回复和全局知识库。
- 买家互动、商品自动化、通知与运行日志。
- 「系统设置 → 功能区」提供独立 Boolean 开关。关闭功能会隐藏对应页面、阻止服务端动作并收敛后台任务，但保留原有配置，重新开启即可恢复。
- Token 周期刷新、Cookie 周期刷新等主动任务可以关闭；连接所需的 Token 获取、扫码/人工恢复和手动聊天仍属于恢复与聊天路径。

## 安全边界

- 功能开关不是删除操作，不会删除商品、订单、卡密、知识库、模板、日志或账号配置。
- 后端对关闭功能返回稳定的 `409 feature_disabled`；前端隐藏不是安全控制。
- Cookie、密码、Token、二维码、聊天记录、订单和卡密属于私密业务数据，只保存在本地运行目录，不要提交或发送到外部服务。
- 自动回复、自动发货和平台账号操作有业务与风控风险。项目不能保证永不出现验证码、限流或账号处罚，请先用测试账号验证。

## Docker Compose

需要 Docker 和 Docker Compose。源码构建会使用当前分支的前后端代码：

```bash
git clone https://github.com/adzcsx2/xianyu-seller.git
cd xianyu-seller
cp .env.example .env
docker compose up -d --build
```

国内网络环境可以使用：

```bash
docker compose -f docker-compose-cn.yml up -d --build
```

NAS 或不希望本机构建时，使用：

```bash
docker compose -f docker-compose.nas.yml up -d
```

NAS 配置默认使用 `ghcr.io/adzcsx2/xianyu-seller:latest`。启动后访问 `http://localhost:8080/`；带 Nginx 的配置使用 `--profile with-nginx`。升级前请先备份 `data/`、`logs/` 和 `backups/`，并阅读 [迁移说明](docs/MIGRATION.md)。

## 源码运行

需要 Python 3.11+、Node.js 20+、npm 和 Chromium：

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

管理后台、API 文档和健康检查分别位于 `/`、`/docs` 和 `/health`。默认管理员配置可在 `.env` 中修改；生产环境请启用登录、替换默认密码，并避免把免登录模式暴露到公网。

## 外部服务配置

公告、AI 和商品详情服务默认均为未配置，不会因为空值自动请求某个维护者服务。需要使用时，请在「系统设置」或配置文件中显式填写可信地址，并自行核验服务商、密钥、隐私和费用。

## 数据与测试

运行数据位于 `data/`，日志位于 `logs/`，备份位于 `backups/`；这些目录和登录浏览器状态均不应提交。

```powershell
python scripts/run_tests.py --list
python scripts/run_tests.py --suite core --database snapshot
python scripts/run_tests.py --suite e2e --database snapshot
python scripts/run_tests.py --suite all --coverage --quality --database snapshot
```

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [文档索引](docs/README.md) | 按指南、模块、参考、计划和报告浏览全部文档 |
| [项目概览](docs/guide/PROJECT_OVERVIEW.md) | 运行入口、目录结构和核心边界 |
| [架构说明](docs/modules/ARCHITECTURE.md) | 后端、前端、任务和数据流 |
| [接口参考](docs/references/API.md) | 认证、功能开关、AI 模型和健康检查接口 |
| [部署与排查](docs/deployment.md) | Docker、滑块验证、更新和故障排查 |
| [自动化测试指南](docs/guide/自动化测试指南.md) | 测试套件、数据库隔离和质量门禁 |

### 最近更新

| 日期 | 描述 |
| --- | --- |
| 2026-09-10 | 补充项目总览、架构、接口、依赖和文档索引，并记录 AI 服务安全边界。 |

> 查看全部更新：[文档更新日志](docs/reports/CHANGELOG.md)

问题反馈和版本信息请使用 [Issues](https://github.com/adzcsx2/xianyu-seller/issues) 与 [Releases](https://github.com/adzcsx2/xianyu-seller/releases)。

## 许可证

本项目使用 [GNU Affero General Public License v3.0](LICENSE)。修改、部署或通过网络向用户提供服务时，请遵守 AGPL-3.0 的相关义务。
