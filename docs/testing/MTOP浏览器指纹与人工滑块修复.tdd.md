# MTOP 浏览器指纹与人工滑块修复 TDD 证据

## 来源与用户旅程

本次旅程由故障日志与用户描述推导，没有外部计划文档。

- 账号通过人工滑块取得 `x5sec` 后，Token 刷新应使用相同的 User-Agent 与 Client Hints，不再被 MTOP 判定为指纹伪造。
- Docker/NAS 上浏览器启动较慢时，人工验证弹窗应继续连接，直到服务器端滑块画面可用。

## RED / GREEN 记录

### 统一浏览器指纹

- RED：`python -m unittest discover -s tests -p test_mtop_browser_fingerprint.py -v`
- 结果：`ModuleNotFoundError: No module named 'utils.mtop_browser_fingerprint'`
- GREEN：同一命令通过 4 项测试。
- 保证：Edge 151 的 UA、`sec-ch-ua`、平台与移动端标记来自同一个配置源；Token 刷新、实时惩罚 URL 请求和人工验证 Playwright context 共用该指纹。

### 人工滑块画面重连

- RED：`python -m unittest discover -s tests -p test_manual_captcha_frontend_retry.py -v`
- 结果：未找到 `CAPTCHA_WS_RETRY_LIMIT`，测试失败。
- GREEN：同一命令通过 1 项测试。
- 保证：人工滑块 WebSocket 重试窗口由原来的 20 秒延长至 120 秒，覆盖常见 Docker/NAS 浏览器冷启动与验证码渲染时间。

### Patchright 浏览器运行时

- RED：`python -m unittest discover -s tests -p test_patchright_browser_runtime.py -v`
- 结果：Patchright 版本未锁定、Docker 镜像未安装其对应 Chromium，人工会话仍导入普通 Playwright。
- GREEN：同一命令通过 3 项测试。
- 保证：镜像固定 `patchright==1.62.3`，安装对应 Chromium 1234（Chrome 151.0.7922.34），人工会话使用 Patchright。

### 人工验证入口与冷却期解耦

- RED：`python -m unittest discover -s tests -p test_manual_captcha_access.py -v`
- 结果：缺少统一的人工验证准入判定，冷却结束后只能返回 409。
- GREEN：同一命令通过 3 项测试。
- 保证：当前仍有一小时内的滑块事件时，即使冷却倒计时已经归零，人工验证入口仍可用；正常账号仍不会被无故打开惩罚页。

## 测试规格

| # | 保证 | 测试 | 类型 | 结果 |
|---|---|---|---|---|
| 1 | 默认 MTOP 指纹是完整的 Edge 151 UA 与 Client Hints | `tests/test_mtop_browser_fingerprint.py` | 单元 | PASS |
| 2 | 人工浏览器与 HTTP Token 请求使用同一份指纹 | `tests/test_mtop_browser_fingerprint.py` | 集成约束 | PASS |
| 3 | Token 刷新和人工验证链路不再嵌入 Chrome 138/139 | `tests/test_mtop_browser_fingerprint.py` | 回归 | PASS |
| 4 | 前端等待服务器端滑块会话至少 90 秒 | `tests/test_manual_captcha_frontend_retry.py` | 回归 | PASS |
| 5 | 本地模拟滑块可显示、拖动并完成 | `python scripts/run_tests.py --suite e2e --database snapshot` | E2E | PASS（12 项） |
| 6 | Patchright 版本、镜像浏览器与人工会话引擎保持一致 | `tests/test_patchright_browser_runtime.py` | 运行时约束 | PASS（3 项） |
| 7 | 冷却结束后有效滑块事件仍允许人工会话 | `tests/test_manual_captcha_access.py` | 回归 | PASS（3 项） |
| 8 | 项目完整测试、类型检查、构建与 Compose 配置均通过 | 全量门禁与独立前端/Compose 校验 | 完整门禁 | PASS（444 项） |
| 9 | 部署容器内 Patchright 能启动目标浏览器，且不暴露 WebDriver | 容器运行时冒烟 | 部署 | PASS（Chrome 151.0.7922.34，`navigator.webdriver=False`） |
| 10 | 部署后的真实 MTOP Token 刷新取得 accessToken，账号恢复连接 | 容器服务日志 | 真实链路 | PASS（`SUCCESS::调用成功`） |

## 覆盖率与已知边界

- 新增指纹模块定向覆盖率：100%（15/15 statements）。
- 仓库完整覆盖率：27.7%，高于项目当前 20% 门禁，但低于通用 80% 目标；这是既有大型单文件与历史模块覆盖率造成的存量差距。
- 部署重启后，服务使用账号现有 Cookie 调用真实 MTOP Token 接口并成功取得 accessToken；由于账号已恢复，安全门不会再无故开启人工滑块会话。
