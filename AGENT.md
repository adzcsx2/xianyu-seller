# Project Guide

## Overview

闲鱼卖家 is an account, item, order, messaging, automated
reply, and delivery management system for Xianyu sellers.

- Backend: Python 3.11+, FastAPI, Uvicorn, SQLite, Playwright/Patchright,
  DrissionPage, HTTP clients, and YAML configuration.
- Frontend: React 19, TypeScript, Vite, Axios, Recharts, and Tailwind CSS.
- The backend serves the built frontend from `static/` on port 8080.

## Key paths

- `Start.py`: startup preparation and application launcher.
- `app/reply_server.py`: FastAPI application, authentication, and most routes.
- `app/routers/`, `app/services/`, and `utils/`: route modules, services, and reusable helpers.
- `app/db_manager.py` and `app/config.py`: SQLite access and YAML configuration.
- `frontend/App.tsx`, `frontend/components/`, and `frontend/services/api.ts`: UI and API client.
- `tests/`: Python `unittest` tests and browser fixtures.
- `docs/`: documentation; `docs/references/ai-rules/` contains focused AI rules.

## Working rules

- Source, manifests, tests, and directory scans outrank README assumptions. Mark unverified facts as `unknown`.
- Reuse existing call paths and local style. Touch only files needed for the request and preserve unrelated changes.
- Plan first for ambiguous work, 3+ source files, cross-module changes, new dependencies/configuration, or public API, model, route, permission, persistence, or directory changes.
- Keep new files focused and preferably under 500 lines. Do not perform unrelated cleanup or legacy refactoring.
- Use `python scripts/run_tests.py` as the automation entry point. Run `--list` to inspect suites, `--suite core --database snapshot` for the normal regression, `--suite e2e --database snapshot` for headless browser behavior, and `--quality --database snapshot` for the complete local gate.
- The complete runner invokes TypeScript and the detached Vite build directly through Node, avoiding platform-specific npm child-shell issues; build output stays below `logs/test-artifacts/` and does not overwrite `static/`. No repository ESLint or Ruff command is configured.
- Write every application, diagnostic, and test log under the repository-root `logs/` directory. Do not create log files in the project root, `.tmp/`, `app/`, `frontend/`, or any other source directory. Treat third-party cache-internal logs as disposable cache data.
- Treat all knowledge-base contents as private business data. Do not stage, commit, quote, copy into documentation, or send them to external services unless the user explicitly requests that exact data transfer. Knowledge content belongs in the ignored runtime database under `data/` or ignored local files under `app/knowledge/`; knowledge-base implementation code remains versioned.
- Treat every real account's login and operating data as private, including cookies, passwords, tokens, browser profiles, storage/session state, QR codes, captcha artifacts, account identifiers, chat/order data, and account exports. Never stage, commit, quote, place in fixtures/docs, or transmit real account data. Keep it only in ignored runtime paths such as `data/`, `browser_data/`, and `slider_cookies/`; tests and examples must use obviously synthetic values.

## Boundaries and testing

- Production directories (`app/`, `utils/`, `Start.py`, and frontend source) must not import or contain Mock/Stub/Spy data; tests may use `unittest.mock`.
- Keep external HTTP, database, browser, file, and mail dependencies behind existing managers/services or explicit injected seams in new business logic. Do not directly instantiate clients or make real calls inside pure business functions.
- Unit tests should cover negative and boundary behavior. Use real test services/databases for integration tests when an environment exists, and guard any mock path with an explicit non-production condition.
- Follow RED -> GREEN: define the observable contract and seam, run the new test to a valid failure, implement the minimum production behavior, and rerun the same target before broader regression checks.
- Direct real-database testing is permitted for this single-user project through `--database live --allow-live-writes`; the runner creates a SQLite backup first. Prefer `snapshot` for repeatability and `temp` for destructive migration/rollback scenarios.
- Never require desktop-control initialization or manual clicks for acceptance. Use Python Playwright headless on a random port; mark only the unavailable manual visual check as `not verified`.
- Detailed automation, isolation, coverage, and change-based gate rules are in `docs/references/ai-rules/02-测试规范.md`.
- Command examples and troubleshooting are in `docs/guide/自动化测试指南.md`.

## Documentation and operations

- Use `/docs` and reuse semantic categories: `plan`, `product`, `design`, `guide`, `modules`, `references`, `checklist`, and `reports`.
- Keep category directory names English; use Chinese for documentation filenames, task directories, and report-topic directories.
- Group related work in `docs/plan/<中文任务名>/`; put audit, performance, evaluation, and retrospective reports in `docs/reports/<中文报告主题>/`.
- All new Git worktrees belong under the project `.worktree/<worktree-name>` directory, which is ignored by the root `.gitignore`.
- If the project final-rule-audit hooks exist, finish by rereading rules, auditing modified files, and recording minimal verification. The current standard does not use `.ai/skills`, mirrors, `sync-project-skills.sh`, or `PostToolUse` refresh hooks.
- Copilot project instructions are maintained only in `.github/copilot-instructions.md` because no root `AGENTS.md` existed at initialization.
- This project normally uses local commits only; do not push to a remote, publish branches, create pull requests, or merge unless the user explicitly requests that separate operation. See `docs/references/ai-rules/04-本地提交策略.md`.
- Before adding or changing an endpoint, search `.ai/index/backend-apis.json` with the tools under `.ai/tools/api-first/` and verify the source route, handler, schemas, flow, and auth boundary. See `docs/references/ai-rules/03-后端接口优先.md`.
- Use concise Chinese Conventional Commit messages when committing, and never add AI attribution or a `Co-Authored-By` line.
- Do not commit secrets, runtime databases, logs, browser state, or user data; do not change remotes or force-push without explicit authorization.
- The root repository has no direct child Git repositories. If that changes, keep child indexes and commits isolated from the root.
