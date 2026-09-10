# Project Rules

This file is the high-density project router for AI coding. It was created by
`dt:init`; it describes the current repository and constrains future work.

## Evidence and scope

- Treat source code, build files, package manifests, tests, and directory scans as the single source of truth. If a fact is not verified, say `unknown`.
- Reuse existing modules, call paths, naming, and local conventions before introducing abstractions or dependencies.
- Touch only files directly required by the request. Preserve unrelated user changes and do not refactor legacy code incidentally.
- Give a short plan before work that is ambiguous, crosses modules/packages, changes 3+ source files, adds dependencies/configuration, or changes public APIs, data models, routes, permissions, persistence, or directory boundaries.
- This standard governs future AI coding; it does not authorize refactoring existing code that the task does not touch.

## Repository map and stack

- Runtime: Python 3.11+, FastAPI, Uvicorn, SQLite, Playwright/Patchright, DrissionPage, HTTP clients, and YAML configuration.
- Frontend: React 19, TypeScript, Vite, Axios, Recharts, Tailwind CSS under `frontend/`; the built output is served from `static/` by FastAPI.
- Runtime entry: `Start.py` performs startup preparation and starts `app.reply_server:app` on port 8080.
- Backend routes and auth: `app/reply_server.py`, `app/api_captcha_remote.py`, and `app/routers/`.
- Services and persistence: `app/`, `app/services/`, `utils/`, `app/db_manager.py`, `app/config.py`, and runtime data under `data/`.
- Frontend entry and API boundary: `frontend/index.tsx`, `frontend/App.tsx`, `frontend/components/`, `frontend/services/api.ts`, and `frontend/lib/request.ts`.
- Tests: `tests/test_*.py`, using `unittest.TestCase` and `unittest.IsolatedAsyncioTestCase`; fixtures are under `tests/fixtures/`.

## Commands and verification

- Install Python dependencies: `python -m pip install -r requirements.txt`.
- Install test dependencies: `python -m pip install -r requirements-test.txt`.
- Install the browser used by the project: `playwright install chromium`.
- Build the frontend: `cd frontend; npm ci; npm run build` (the build writes the served assets to `static/`).
- Run the application: `python Start.py`.
- List automated suites: `python scripts/run_tests.py --list`.
- Run core regression: `python scripts/run_tests.py --suite core --database snapshot`.
- Run headless browser E2E: `python scripts/run_tests.py --suite e2e --database snapshot`.
- Run the complete local gate: `python scripts/run_tests.py --quality --database snapshot`.
- Frontend checks are part of `--quality`; the runner invokes the local TypeScript and detached Vite build directly through Node to avoid platform-specific npm child-shell issues. Output stays below `logs/test-artifacts/` and does not replace `static/`.
- All initialization, hook, application, diagnostic, test, build, and audit log files must be written below the repository-root `logs/` directory. Never create an intentional log file in the root, `.tmp/`, a source directory, `/docs`, or another runtime directory.
- Knowledge-base contents are private business data. Never stage, commit, reproduce in documentation, or transmit that content externally without an explicit request covering the exact transfer. Store it only in the ignored `data/` runtime database or ignored local files below `app/knowledge/`; keep implementation code versioned.
- All real account login and operating data is private: cookies, passwords, tokens, browser profiles, storage/session state, QR codes, captcha artifacts, account identifiers, messages, orders, and exports must never be staged, committed, quoted, copied into fixtures/docs, or transmitted externally. Store them only in ignored runtime paths such as `data/`, `browser_data/`, and `slider_cookies/`; use clearly synthetic test/example values.
- There is no verified repository ESLint or Ruff command; do not claim one passed.
- A final rule audit hook is installed for both Claude and Codex. Before the final response, reread applicable rules, audit every modified file, and report the minimum verification result; fix violations first.

## Coding boundaries

- Keep new source files focused and preferably below 500 lines. Do not enlarge already-large files with unrelated responsibilities; split only when the requested change needs it.
- Keep production code in `app/`, `utils/`, `Start.py`, and the frontend source free of Mock/Stub/Spy data and test-only imports. Test code under `tests/` may use `unittest.mock`.
- Existing code uses module-level managers and direct clients in places. Preserve those local patterns unless a task explicitly includes a refactor; for new business logic, keep HTTP, database, browser, file, and mail access behind an explicit seam or injected dependency.
- Python external dependencies should be passed through constructors, function parameters, or existing manager/service boundaries. Do not instantiate a repository/client or issue a real request inside a pure business function.
- When a mock-enabled path is necessary, guard it with an explicit non-production test/development condition; production configuration must select real dependencies.
- Unit tests must include failure and boundary cases where relevant. Add integration coverage against a real test service/database when the task has such an environment; do not make a unit test pass by changing business behavior.
- Use RED -> GREEN for behavior changes. Direct real-database tests are permitted only through `--database live --allow-live-writes`, which creates a backup first; use `snapshot` normally and `temp` for destructive migration/rollback cases.
- Acceptance must not depend on desktop-control initialization or manual clicking. Use Python Playwright headless with a random local port and label only unavailable manual visual inspection as `not verified`.
- Follow the detailed automation, coverage, artifact, and change-based gate rules in `docs/references/ai-rules/02-测试规范.md`.
- Use `docs/guide/自动化测试指南.md` for command examples and troubleshooting.
- Preserve Python sync/async style, existing FastAPI/Pydantic models, and existing React request/state/style patterns in the touched area.

## API-first rule

For any business capability, data access, integration, diagnosis, acceptance, or new endpoint request, search and verify existing backend APIs before proposing a contract:

- Rebuild when stale: `pwsh -File .ai/tools/api-first/build-api-index.ps1 -WorkspaceRoot .`.
- Search: `pwsh -File .ai/tools/api-first/search-api-index.ps1 -WorkspaceRoot . -Query "<domain resource action caller>"`.
- Verify route registration, handler, schemas, service/repository flow, and auth middleware in source. Report method/path, caller boundary, inputs/outputs, and evidence. The index is a discovery aid, not an authorization decision.
- Detailed protocol: `docs/references/ai-rules/03-后端接口优先.md`.

## Documentation and rule routing

- New documentation belongs under `/docs`. Reuse semantic equivalents before creating directories.
- Standard categories are `plan`, `product`, `design`, `guide`, `modules`, `references`, `checklist`, and `reports`; category names remain English.
- Documentation filenames, task-directory names, and report-topic directory names under `/docs` must be Chinese.
- Aggregate 3+ related planning documents in `docs/plan/<中文任务名>/`; put audit, performance, evaluation, and retrospective reports in `docs/reports/<中文报告主题>/`. `CHANGELOG.md` may remain at `docs/reports/` root.
- Main rules stay short and route to focused rules. Read the relevant files under `docs/references/ai-rules/` before changes to architecture, tests, or APIs.
- Current focused rules: `docs/references/ai-rules/01-架构边界.md`, `docs/references/ai-rules/02-测试规范.md`, `docs/references/ai-rules/03-后端接口优先.md`, and `docs/references/ai-rules/04-本地提交策略.md`.

## Worktrees and hooks

- Keep the project-local `.worktree/` directory. All new Git worktrees must be created at `<project-root>/.worktree/<worktree-name>`; do not create sibling worktrees or default to an external directory. The root `.gitignore` contains `/.worktree/`.
- Project hooks are execution gates, not rule sources. The installed Windows hooks are `.claude/hooks/final-rule-audit.ps1` and `.codex/hooks/final-rule-audit.ps1`, registered on `Stop`; they fail open and never edit business code.
- The current init standard does not create `.ai/skills`, configured mirrors, `sync-project-skills.sh`, or `PostToolUse` mirror refresh hooks. Do not add them unless explicitly requested.
- The legacy `AGENT.md` was read as migration input and is not the active standard. Because `.github/copilot-instructions.md` is the existing sole Copilot project configuration, keep it as the only Copilot location; do not create or maintain a second root `AGENTS.md` for Copilot.
- Existing project AI guidance, API-first artifacts, and project hooks were upgraded or verified against the current init standard; this standard constrains future coding and does not authorize unrelated source refactors.

## Git

- Use concise Chinese Conventional Commit messages when asked to commit. Never add AI attribution or any `Co-Authored-By` line.
- This project normally stops at a local commit and does not push to a remote. Remote synchronization, push, branch publication, pull-request creation, and merge require an explicit user request; never force-push.
- Before committing, inspect status and diff, stage only files belonging to the current task, and leave unrelated user changes untouched. Do not commit secrets, runtime databases, logs, browser state, or user data.
