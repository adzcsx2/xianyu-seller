# 滑块重登修复 TDD 验证记录

日期：2026-09-20

## 结论

本次重新登录失败并非主要由滑块距离计算错误导致。运行日志显示滑块目标距离约为 312px，实际拖动也到达约 312px，但平台仍返回验证失败。结合运行环境与上游修复历史，根因是无头/有头浏览器暴露出的 UA、平台、UA-CH 和插件信息不一致，被平台识别为自动化环境。

滑块失败后的清理链还有第二个问题：旧依赖在另一个线程关闭 Playwright 同步对象，触发线程切换异常并遗留运行时；随后自动重连很快再次发起密码登录，最终报出在 asyncio 循环中使用 Playwright Sync API 的错误。

## 用户旅程与回归契约

| 用户旅程 | 可观察契约 | 回归测试 |
| --- | --- | --- |
| 会话过期后触发密码重登 | 使用包含一致浏览器指纹和同线程资源清理的 slidex 修订 | `test_slidex_is_pinned_to_fingerprint_and_same_thread_cleanup_fix` |
| 滑块失败或验证超时 | 本次尝试也应进入冷却期，不能由 WebSocket 重连连续拉起浏览器 | `test_auto_refresh_failure_starts_cooldown_before_next_reconnect` |

## RED 证据

- `python -m unittest discover -s tests -p test_dependency_security.py`：旧依赖修订不满足指纹与清理修复契约，测试失败。
- `python -m unittest discover -s tests -p test_password_login_lifecycle.py`：连续两次自动刷新创建了 2 个登录实例，期望为 1，测试失败。

## GREEN 证据

- `python scripts/run_tests.py --suite core --database snapshot`：582 个测试通过。
- 独立构建 `xianyu-seller:slidex-fix-verify`：成功安装精确修订 `8a7e9616220390c5927ac282f576a181a380edef`，包版本为 `slidex 0.5.9`。
- 镜像内源码断言通过：密码登录不再通过辅助线程关闭 Playwright，并包含有头模式指纹、网络层 UA-CH 指纹和 `userAgentData` 覆盖。
- `python scripts/run_tests.py --quality --database snapshot`：596 个测试通过；总覆盖率 30.3%，满足仓库当前 20% 门禁；前端构建、TypeScript 检查、三套 Compose 配置和 `git diff --check` 全部通过。

## 实现变更

- 将 slidex 固定到同时包含浏览器指纹一致性和同线程资源清理修复的 0.5.9 精确修订。
- 密码登录一经实际发起，无论成功、失败还是抛出异常，都会记录冷却时间，阻断 WebSocket 短退避重连造成的登录浏览器循环。
- 增加依赖修订和失败冷却两类回归测试，并隔离测试之间的类级冷却状态。

## 已知边界

- 未使用真实账号执行线上滑块验收，以避免自动化测试接触真实账号、验证码和会话数据；真实平台最终放行仍需在更新运行容器后观察一次。
- 当前运行中的容器未被本次验证替换；本次只构建了独立验证镜像。
- 仓库全局覆盖率为 30.3%，低于通用 80% 目标，但本次新增故障路径均有定向回归测试，且满足仓库现行质量门禁。

## 本地提交

- `a695e42 test: 增加滑块重登故障回归用例`
- `854d05d fix: 修复滑块指纹与重登清理循环`
