# 知识库审查修复 TDD 证据

## 范围

本次仅修复审查项 2、4、5：

- 将 Passistant 活动价保护限定到已保存的 Passistant 商品知识库，不影响其他低价商品按账号折扣议价。
- 知识库页面在切换账号、切换商品、重新加载和导入模板前检查未保存修改。
- 统一知识库服务端校验、HTTP 请求模型和接口文档约定，包括长度、数量、严格类型、未知字段和 512 KiB 载荷上限。

按项目所有者决定，审查项 1（内网截图）和审查项 3（项目共用模板）保持不变。

## 用户旅程与验收条件

1. 普通低价商品仍按账号配置的最低折扣计算；只有已保存并标记为 `passistant` 的知识库商品锁定当前活动价。
2. 运营人员编辑知识但尚未保存时，切换账号、商品、重新加载或导入模板都必须先确认，避免静默丢失。
3. 知识库 API 与领域服务接受相同边界：键 1–80 字符、答案最多 800 字符、匹配短语最多 20 个且单项最多 80 字符、关键词最多 30 个且单项最多 32 字符、来源最多 8 个且单项最多 240 字符、整份载荷最多 512 KiB；布尔值和整数使用严格类型，未知字段被拒绝。

## RED 阶段

- 提交 `69b0d89`：增加知识库校验、未保存修改保护和普通低价商品议价回归用例。
- 提交 `4242068`：补充 Passistant 商品价格保护范围用例。
- `python -m unittest discover -s tests -p "test_ai_reply_safety.py"` 初次失败：价格解析函数不支持 `protect_current_price`。
- `python -m unittest discover -s tests -p "test_product_knowledge.py"` 初次失败：边界不一致、列表未规范化、无载荷上限、布尔值会被强制转换、前端缺少未保存修改保护、服务缺少商品范围判断。

## GREEN 阶段

- 提交 `fc248f8`：实现知识库合同统一、未保存修改保护及 Passistant 专属价格保护。
- `python -m unittest discover -s tests -p "test_ai_reply_safety.py"`：38 项全部通过。
- `python -m unittest discover -s tests -p "test_product_knowledge.py"`：27 项全部通过。
- `python -m py_compile app/ai_reply_engine.py app/product_knowledge.py app/reply_server.py`：通过。
- `docker compose build xianyu-app`：前端生产构建和 Docker 镜像构建通过。
- `docker compose up -d --no-deps xianyu-app`：容器使用新镜像重建成功。
- `GET http://localhost:8080/health`：返回 `healthy`，数据库和 Cookie 管理服务均为 `ok`。

## 全量回归

`python -m unittest discover -s tests -p "test_*.py"` 共运行 339 项，338 项通过。唯一失败为既有的 `test_slider_watchdog.KillBrowserProcessTests.test_matches_only_own_user_data_dir`，与本次修改范围无关；该失败在修复前基线中已经存在。

## 覆盖率

已为每项修改保证增加正向、反向和边界回归用例。当前 Python 环境未安装 `coverage` 模块，`python -m coverage --version` 返回 `No module named coverage`，因此数值覆盖率未验证。

## 合并与边界证据

- RED 测试提交与 GREEN 实现提交均已进入当前分支历史。
- 未重置、覆盖或清理工作区中与本次修复无关的既有改动。
- 本次未操作浏览器，部署验证仅使用 Docker 命令和 HTTP API。
