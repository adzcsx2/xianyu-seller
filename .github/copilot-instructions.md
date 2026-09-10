# Copilot Project Instructions

## Repository context

- This repository is a Python 3.11+ FastAPI service with a React 19/TypeScript/Vite frontend. `Start.py` launches `app.reply_server:app`; `frontend/` builds assets served from `static/`.
- Backend route and auth work is centered in `app/reply_server.py`, `app/routers/`, and `app/services/`; persistence and configuration are in `app/db_manager.py` and `app/config.py`.

## General rules

- Use source code, manifests, tests, and directory scans as the source of truth; mark unverified facts as `unknown`.
- Reuse existing modules, request paths, naming, and local conventions. Touch only files needed for the request and preserve unrelated changes.
- Plan first for ambiguous work, changes spanning 3+ source files or modules, new dependencies/configuration, or public API, model, route, permission, persistence, or directory changes.
- Keep new files focused and preferably below 500 lines. Do not perform unrelated refactoring.
- Use `python scripts/run_tests.py` as the automation entry point: `--suite core --database snapshot` for normal regression, `--suite e2e --database snapshot` for headless browser behavior, and `--quality --database snapshot` for the complete local gate. The runner invokes TypeScript and the detached Vite build directly through Node; no repository ESLint or Ruff command is configured.
- Put every initialization, hook, application, diagnostic, test, build, and audit log file below the repository-root `logs/` directory. Do not intentionally write logs to the root, `.tmp/`, `/docs`, or source directories.
- Treat knowledge-base contents as private business data: never stage, commit, reproduce, or transmit them without an explicit request for that exact transfer. Store them only in ignored runtime data under `data/` or ignored local files under `app/knowledge/`; keep knowledge implementation code versioned.
- Treat every real account's login and operating data as private, including cookies, passwords, tokens, browser profiles, storage/session state, QR/captcha artifacts, account identifiers, messages, orders, and exports. Never stage, commit, quote, place real values in fixtures/docs, or transmit them. Keep them in ignored runtime paths such as `data/`, `browser_data/`, and `slider_cookies/`; examples must be synthetic.
- Production code in `app/`, `utils/`, `Start.py`, and frontend source must not use Mock/Stub/Spy data or test-only imports; tests may use `unittest.mock`.
- Keep external HTTP, database, browser, file, and mail access behind existing service/manager boundaries or explicit injected seams. Guard mock paths with an explicit non-production condition.
- Follow RED -> GREEN: define the observable contract and seam, run a valid failing test, implement the minimum behavior, then rerun that target and the applicable broader suite. Include negative and boundary cases.
- Direct real-database testing is permitted through `--database live --allow-live-writes`, which creates a SQLite backup first. Prefer `snapshot` for repeatability and `temp` for destructive migration/rollback scenarios.
- Do not depend on desktop control or manual clicks for acceptance. Use Python Playwright headless on a random port and follow `docs/references/ai-rules/02-测试规范.md` for detailed layers, coverage, artifacts, and change-based gates.
- New docs go under `/docs`; category names are English, while documentation filenames, task directories, and report-topic directories are Chinese.
- Use `docs/plan/<中文任务名>/` for 3+ related planning documents and `docs/reports/<中文报告主题>/` for audit, performance, evaluation, and retrospective reports. `CHANGELOG.md` may remain at `docs/reports/` root.
- Keep detailed rules modular under `docs/references/ai-rules/`; read the relevant file instead of expanding this router.
- This project normally stops at a local commit and does not push to a remote. Remote sync, push, branch publication, pull requests, and merges require an explicit user request; never force-push. Inspect status/diff and stage only task files before committing.
- For endpoint or data-access work, search the API-first index with `.ai/tools/api-first/search-api-index.ps1`, rebuild it when stale, and verify route, handler, schemas, service flow, and auth in source. See `docs/references/ai-rules/03-后端接口优先.md`.
- All new Git worktrees must use `<project-root>/.worktree/<worktree-name>`; the root `.gitignore` ignores `/.worktree/`.
- If final-rule-audit hooks are present, reread applicable rules and audit modified files and minimal verification before replying; fix violations first. The current init standard does not use `.ai/skills`, mirrors, `sync-project-skills.sh`, or `PostToolUse` refresh hooks.
- Copilot instructions are kept only here; do not also create or maintain a root `AGENTS.md` for Copilot configuration.
- The legacy `AGENT.md` is migration input only and is not the active project rule source.
- Do not commit secrets, runtime databases, logs, browser state, or user data. Do not change remotes or force-push without explicit authorization.
- Use concise Chinese Conventional Commit messages when committing and never add AI attribution or a `Co-Authored-By` line.
- No direct child Git repositories were detected during initialization; if that changes, keep child commits and indexes isolated from the root.
- Preserve the existing Python sync/async style, FastAPI/Pydantic boundaries, React request utilities, and local naming conventions in the area being changed.
- Keep generated project documentation UTF-8 and in English; follow the Chinese filename and directory naming policy under `/docs`.
