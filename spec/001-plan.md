# dba (Dependabot Backlog Agent) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. TDD is mandatory (CLAUDE.md): write failing tests → run (see them fail) → implement → run (green) → commit. Steps use `- [ ]`.

**Goal:** Implement spec `spec/001-init-spec.md` (v9): a Docker Compose system that works through a repo's Dependabot PR backlog and ends each PR with a verdict + evidence + proposed GitHub actions.

**Architecture:** Python 3.12 backend (`backend/`) = FastAPI API + Temporal workflows/activities split over task queues + an OpenAI-compatible `llm-gateway`. Next.js App Router + shadcn UI (`web/`). Every external service is reachable through a real client whose base URL is configurable; in mock mode those URLs point at `mocks/` (a FastAPI "mock world" that imitates GitHub, Bedrock (OpenAI-compatible), OSV, GHSA, PyPI and git hosting) and fake `entire` / `opencode` CLIs. The same code paths run against real services once `.env` holds real values.

**Tech Stack:** Python 3.12, uv, FastAPI, pydantic v2, pydantic-settings, SQLAlchemy 2 async + aiosqlite, Alembic, temporalio, httpx, openai SDK, PyJWT[crypto], sse-starlette, pytest + pytest-asyncio + respx. Next.js (App Router, TS strict), Tailwind v4, shadcn/ui, lucide-react, motion, TanStack Query, react-hook-form + zod, next-themes, Vitest + Testing Library, Playwright.

**Spec:** `spec/001-init-spec.md`. **Open items / questions log:** `spec/001-open-items.md`.

## Global Constraints

- One branch `feat/001-init-spec`, one PR. **Exactly one Alembic migration** (`backend/db/migrations/versions/0001_initial.py`) holding the full section-15 schema. Nobody adds a second migration; schema changes edit 0001.
- Python ≥ 3.12; dependencies only through root `pyproject.toml` (uv). Web deps only in `web/package.json` (pnpm).
- SQLite pragmas on every connection: `journal_mode=WAL; busy_timeout=5000; foreign_keys=ON; synchronous=NORMAL`.
- Workflow code: no I/O, no clock (use `workflow.now()`), no randomness, no model calls, no neatlogs. Large payloads → blob store, workflows carry `sha256` refs. No secrets in workflow inputs.
- Hard rule: a security update whose vulnerable code is `REACHABLE` or `UNCERTAIN` is never `DISMISS`.
- Sandboxes never receive Bedrock, GitHub or Docker credentials; model access only via `llm-gateway` per-attempt tokens.
- UI: shadcn first → `components/composed/` → `components/custom/` (target: none). lucide-react icons only, theme tokens only, no hex, no inline styles. Motion tokens fast 150 / base 200 / slow 300 ms. Reduced motion respected.
- Comments only where logic is complex (CLAUDE.md). No redundant comments.
- Mock rule: a real client is used for every service; the mock-world URLs are the `.env.example` defaults (`GITHUB_API_URL`, `GITHUB_WEB_URL`, `LLM_BASE_URL`, `OSV_API_URL`, `PYPI_INDEX_URL`, `PYPI_JSON_URL`, `CFO_MCP_URL`). neatlogs is a no-op when `NEATLOGS_API_KEY` is empty. `entire`/`opencode` are fake scripts (`mocks/bin/`) in mock images.

## Review Focus

1. Duplicate webhook deliveries / repeated "Start run" clicks → exactly one workflow (deterministic IDs), no duplicate GitHub comments (hidden marker `<!-- dba:{item_id} -->`, unique action key). Test owner: Tasks 4, 9, 10.
2. PR head SHA changes between analysis and action execution → action cancelled, item re-queued, never merged. Test owner: Task 9.
3. Baseline test suite already red, or a flaky test → only new failures count; one rerun. Test owner: Task 2 (`testresults`), Task 8.
4. SSE client reconnects with `Last-Event-ID` → no lost or duplicated events. Test owner: Task 10.
5. Malformed / prose-only model output and gateway tokens that are expired, revoked, over budget or using a non-allowlisted alias → clean `NEEDS_HUMAN`/401/429, never a crash. Test owner: Tasks 5, 6.

---

## Shared interfaces (locked in Task 1; everyone imports these)

`backend/core/contracts.py` (pydantic v2, all `model_config = ConfigDict(frozen=False, extra="forbid")`):

```text
Verdict: MERGE | FIX_THEN_MERGE | DISMISS | NEEDS_HUMAN
ReasonCode: SUPERSEDED | UNREACHABLE_AND_BREAKING | DEV_ONLY_NO_IMPACT | BUDGET | RESOLUTION_FAILURE |
            INTERACTION_FAILURE | CI_FAILED | SOURCE_UNAVAILABLE | FIX_EXHAUSTED | SECURITY_UNFIXED |
            DYNAMIC_ACCESS | VERIFIER_DOWNGRADE | VERIFIER_REJECTED | ENV_FAILURE | TOOL_ERROR
Reachability: REACHABLE | UNREACHABLE | UNCERTAIN          Risk: LOW | MED | HIGH
BumpType: patch | minor | major | unknown                  TestStatus: pass | fail | env_error
ItemState: QUEUED SUPERSEDED_CHECK PREPARING ANALYZING APPLYING TESTING FIXING DRAFTED VERIFYING
           DONE DONE_DISMISS DONE_NEEDS_HUMAN
VerifierDecisionKind: CONFIRM | REJECT | DOWNGRADE
ActionType: comment | label | push_fix | combined_pr | close | merge
ActionStatus: PROPOSED | APPROVED | REJECTED | EXECUTED | FAILED | CANCELLED
RunStatus: PENDING | PLANNING | RUNNING | PAUSED | AWAITING_APPROVAL | EXECUTING | COMPLETED | FAILED | CANCELLED
RunMode: backlog | watch | eval | public

PRRef{number:int, title:str, head_ref:str, head_sha:str, url:str, created_at:datetime, body:str=""}
PackageBump{name, from_version, to_version, manifest:str, dev_only:bool=False}
Advisory{id:str, cve:str|None, severity:str, cvss:float|None, summary:str, vulnerable_symbols:list[str]=[],
         fixed_in:str|None, fix_commit_url:str|None}
WorkItem{item_id, run_id, repo, base_sha, prs:list[PRRef], packages:list[PackageBump], advisories:list[Advisory],
         bump_type:BumpType, priority:int, group:str|None=None, superseded_by:int|None=None}
CallSite{file, line:int, symbol, code:str=""}
AnalysisReport{reachability, paths:list[list[str]], risk, expected_breakage:list[str], notes:str, evidence_refs:list[str]}
TestResult{status:TestStatus, total:int, passed:int, failed:list[str], errors:list[str], new_failures:list[str],
           log_ref:str|None, duration_s:float=0, flaky_rerun:bool=False}
PreviousAttempt{diff_ref, result:str}
FixBrief{item_id, attempt:int, packages, failing_tests:list[str], failure_tail_ref:str|None, failure_tail:str,
         changed_symbols:list[str], call_sites:list[CallSite], impact:list[str], previous_attempts:list[PreviousAttempt],
         constraints:list[str]}
GuardResult{allow:bool, reasons:list[str]}
FixAttempt{attempt:int, diff_ref:str|None, files:list[str], guard:"allow"|"deny", guard_reasons:list[str],
           test_result_ref:str|None, test_status:TestStatus|None, commit_sha:str|None, entire_checkpoint_id:str|None,
           tokens_in:int=0, tokens_out:int=0, usd:float=0}
Claim{claim:str, evidence_ref:str}
DraftVerdict{verdict, reason_code:ReasonCode|None, reachability, confidence:float(0..1), summary:str, claims:list[Claim]}
ReviewResult{verdict:"approve"|"concern"|"reject", ref:str|None, source:"entire"|"inhouse"}
VerifierDecision{decision:VerifierDecisionKind, checks:dict[str,bool], review:ReviewResult|None, notes:str=""}
Action{action_id, run_id, item_id, repo, pr:int, type:ActionType, level:int, payload:dict, status:ActionStatus,
       head_sha:str}
ItemOutcome{item_id, state:ItemState, verdict:Verdict, reason_code:ReasonCode|None, confidence:float,
            draft:DraftVerdict|None, verifier:VerifierDecision|None, attempts:int}
RunSummary{run_id, status:RunStatus, total:int, by_verdict:dict[str,int], actions_proposed:int, actions_executed:int,
           usd:float, report_ref:str|None}
```

Other locked names (signatures exact):

- `backend/settings.py`: `Settings` (pydantic-settings, env), `AppConfig` (parsed `config.toml`), `get_settings() -> Settings` (lru_cache), `load_config(path: str | None = None) -> AppConfig`.
- `backend/db/session.py`: `make_engine(url) -> AsyncEngine` (pragmas), `get_sessionmaker(url=None) -> async_sessionmaker`, `init_db(url)` (runs Alembic upgrade head).
- `backend/db/models.py`: SQLAlchemy models for every section-15 table, class names `Installation Repo Run WorkItemRow Event Evidence Blob FixAttemptRow VerdictRow ActionRow Override GatewayToken Cost EvalCase EvalResult`.
- `backend/db/events.py`: `async record_event(sm, *, run_id, item_id=None, type, from_state=None, to_state=None, detail=None) -> int` (retries `database is locked` with jitter) and `async events_after(sm, run_id, after_id, limit=500) -> list[dict]`.
- `backend/blobs.py`: `BlobStore(root, sm)` with `async put(data: bytes|str, kind: str) -> str (sha256)`, `async get(sha) -> bytes`, `path_for(sha) -> Path` (layout `{root}/{sha[0:2]}/{sha}`).

## Waves

| Wave | Tasks (parallel inside a wave, each in its own worktree) |
|---|---|
| 0 | Task 1 (orchestrator) |
| 1 | Tasks 2, 3, 4, 5+6, 7 |
| 2 | Tasks 8, 9, 10, 11 |
| 3 | Tasks 12, 13, 14 (orchestrator) |

---

### Task 1: Foundation (orchestrator)
**Files:** `pyproject.toml`, `.gitignore`, `.env.example`, `config.toml`, `backend/settings.py`, `backend/core/contracts.py`, `backend/db/{models,session,events}.py`, `backend/db/migrations/**` (alembic env + `0001_initial.py`), `alembic.ini`, `backend/blobs.py`, `backend/tracing.py`, `tests/conftest.py`, `tests/unit/test_{contracts,settings,db,events,blobs}.py`, `spec/001-open-items.md`.
- [ ] Failing tests: contracts round-trip + reject extra keys + confidence bounds; settings env override + config.toml parse; migration creates all 16 tables + `(run_id,id)` events index + `UNIQUE(repo,pr,type,item_id)`; pragmas applied (`PRAGMA journal_mode` = wal); `record_event` ids monotonic, `events_after` paging; retry on `database is locked`; blob put idempotent, sha correct, path layout; `tracing.init()` no-op without key.
- [ ] Implement, green, commit `feat(foundation): contracts, settings, db schema, events, blobs`.

### Task 2: Pure core logic
**Files:** `backend/core/{decision,patch_guard,planning,versions,testresults,usage,bump}.py`, `tests/unit/core/*`.
**Produces:**
- `decision.decide(f: DecisionFacts) -> DraftVerdict` where `DecisionFacts{symbols_called:bool, dynamic_access:bool, tests:"pass"|"fixed"|"fail"|"n/a", is_security:bool, dev_only:bool, used:bool, analyst:AnalysisReport|None, source_available:bool=True}`; implements table 10.2 row by row, `confidence ≤ 0.7` for dynamic-access MERGE, `≤ 0.5` when source unavailable, analyst stricter outcome wins, security hard rule.
- `patch_guard.check_patch(diff: str, packages: list[PackageBump], max_lines=200) -> GuardResult` (section 8.4: test files, conftest, skip/xfail markers, `pragma: no cover`, CI dirs, `pytest.ini`/`setup.cfg [tool:pytest]`/`pyproject [tool.pytest`, pin-back of bumped package in any manifest/lockfile, `.dba/ .opencode/ .entire/`, >200 changed lines).
- `versions.bump_type(from_v, to_v) -> BumpType` (PEP 440 via `packaging`), `versions.parse_dependabot_title(title) -> list[PackageBump-lite]` handling "Bump X from A to B", "Bump X from A to B in /path", grouped "Bump the pip group across 1 directory with 3 updates" (body table).
- `planning.supersede(items) -> (kept, superseded)`; `planning.group(items, seeds=SEED_GROUPS) -> dict[str, list]`; `planning.priority(item, now) -> int` (CVSS≥7 +100, any advisory +50, patch +20, minor +10, major 0, runtime +10, age/30 days capped +10); `planning.plan_backlog(run_id, repo, base_sha, prs, advisories_by_pr, dev_only_by_pkg, now) -> list[WorkItem]` sorted by priority desc.
- `testresults.parse_junit(xml: str) -> (total, passed, failed[], errors[])`; `testresults.compare(baseline: TestResult|None, after) -> TestResult` (only new failures count; env_error when collection error/no tests ran with non-zero exit).
- `usage.find_usages(repo_dir, package_import_names: list[str], symbols: list[str]) -> list[CallSite]` (AST: `import x`, `from x import y as z`, attribute chains `x.a.b`, skips tests unless asked); `usage.scan_dynamic_access(repo_dir, names) -> list[CallSite]` (`getattr` with non-literal, `importlib.import_module`, `__import__`, string-based lookups of the package).
- `bump.apply_bump(repo_dir, pkg: PackageBump) -> list[str]` (edits `requirements*.txt`, `pyproject.toml` PEP 621 + Poetry dep tables; returns changed files; lockfiles regenerated by `uv lock`/`poetry lock` in sandbox, not here); `bump.import_names(dist_name) -> list[str]` (normalise, known map e.g. `beautifulsoup4→bs4`, `PyYAML→yaml`).
- [ ] Edge cases tested per function (empty inputs, pre-releases, epoch versions, aliases, star imports, relative imports, syntax-error files skipped, CRLF diffs, binary diffs, renamed files).
- [ ] Commit per module.

### Task 3: GitHub + advisories + PyPI clients and the mock world (GitHub/OSV/PyPI/git)
**Files:** `backend/integrations/github/{app_auth,client,webhooks,oauth}.py`, `backend/integrations/{advisories,pypi}.py`, `mocks/{app,github,osv,pypi,gitserve,world}.py`, `mocks/demo/build_world.py`, `tests/unit/integrations/*`, `tests/integration/test_mock_world.py`.
**Produces:** `GitHubApp(app_id, key_pem, api_url)` → `jwt()`, `async installation_token(installation_id) -> str` (cached until 5 min before expiry); `GitHubClient(token, api_url)` with `list_dependabot_prs(repo)`, `get_pr(repo, n)`, `pr_files(repo, n)`, `pr_comments`, `upsert_comment(repo, n, marker, body)` (idempotent via marker), `add_labels`, `close_pr`, `merge_pr(repo, n, sha)`, `create_pr`, `get_check_status(repo, sha) -> "pending"|"success"|"failure"`, `get_repo`, `list_installation_repos`, `push_ref` helpers via git (in sandbox worker), `get_ghsa(id)`. `verify_signature(secret, body, header) -> bool`. `OAuth.authorize_url(state)`, `async exchange(code) -> user`. `advisories.fetch(ghsa_or_pkg) ` GHSA → OSV fallback. `pypi.versions(pkg)`, `pypi.download_sdist_or_wheel(pkg, version, dest)`.
**Mock world:** single FastAPI app `mocks.app:app` on `:9000` with prefixes `/github/api` (REST subset above + `/app/installations/{id}/access_tokens`, OAuth `/github/login/oauth/*`), `/git/{owner}/{repo}.git` (dumb-HTTP static bare repos), `/osv`, `/pypi/simple` + `/pypi/json` + `/pypi/files`, all in-memory state with `POST /_mock/reset` and `/_mock/state`. `mocks/demo/build_world.py` builds: demo packages (`dbademo-http` 1.0.0→2.0.0 renames `get_json`→`fetch_json` (breaking, reachable); `dbademo-fmt` 1.2.0→1.2.1 patch (MERGE); `dbademo-fmt` 1.2.0→1.3.0 (supersedes 1.2.1); `dbademo-yaml` 3.0→4.0 security advisory, vulnerable symbol `unsafe_load` unreachable, tests pass → MERGE; `dbademo-lint` dev-only unused → DISMISS DEV_ONLY_NO_IMPACT; `dbademo-cache` 1.0→2.0 breaking, unreachable, unfixable → DISMISS UNREACHABLE_AND_BREAKING) as wheels + sdists, and the `demo-org/demo-app` git repo with one branch + PR per bump.
- [ ] Tests: JWT claims (iat-60, exp ≤10 min, iss), token caching/expiry, pagination (Link header), 5xx retry, 404 mapping, idempotent comment, signature verify (valid/invalid/missing/wrong algo), GHSA→OSV fallback, mock world contract tests using the real clients against `httpx.ASGITransport`.

### Task 5: LLM provider, harness and fake Bedrock
**Files:** `backend/llm/{provider,pricing}.py`, `backend/harness/{tools,loop,context,brief,prompts}.py`, `mocks/llm.py` (mounted at `/llm/v1` in mock world), tests.
**Produces:** `provider.chat(role, messages, tools=None, tool_choice="required", **kw) -> ChatResult{message:dict, tool_calls:list[ToolCall{id,name,arguments:str}], usage{in,out,reasoning}, usd, model, ms}`; `provider.resolve_model(role)`; `pricing.usd(model, in_tok, out_tok)`. Harness: `ToolSpec{name, description, schema(pydantic model), queue, activity}`; `ROLE_TOOLS["analyst"|"fixer"|"verifier"]` (≤6 each, `submit_analysis`, `submit_verdict`, `submit_patch`); `loop.validate_call(tool_specs, call) -> (args|None, error_msg|None)`; `loop.LoopState` (turns, tokens, usd, repair_count, nudged) + `loop.step_decision(state, result, budget) -> "tool"|"submit"|"repair"|"nudge"|"budget_exhausted"|"give_up"`; `context.fence_untrusted(text)`; `context.budget_sections(sections, max_tokens)`; `brief.render_fix_brief(FixBrief) -> markdown`; `prompts.get_prompt(name, label)` (neatlogs when key set, else bundled `backend/harness/prompts/{name}.{label}.md`, labels v1/v2/production). Fake LLM: deterministic scripted responses keyed on role/model + markers in messages; produces valid tool calls, can be told (via `/_mock/llm/script`) to return malformed args or prose to exercise repair paths; supports `stream=true` SSE chunks; returns `usage`.

### Task 6: llm-gateway
**Files:** `backend/gateway/{app,tokens}.py`, tests.
**Produces:** `tokens.issue(signing_key, *, jti, item_id, attempt, aliases, max_tokens, ttl_s, now) -> str`, `tokens.verify(signing_key, token, now) -> Claims` (HMAC-SHA256, constant-time); FastAPI `gateway.app:app` with `GET /v1/models` (aliases only), `POST /v1/chat/completions` (stream + non-stream passthrough, alias → model id, real key injected, budget check before/after, usage → `gateway_tokens` + `costs`), `GET /healthz`. Activities helpers `issue_gateway_token`, `revoke_gateway_token` write `gateway_tokens`.
- [ ] Tests: bad signature/expired/revoked/unknown jti → 401; alias not allowed → 403; over budget → 429; streaming passthrough chunk order and usage accounting from the final chunk; upstream 5xx → 502; never leaks the upstream key in responses/logs.

### Task 7: Infrastructure, devbox/devconsole, fake CLIs
**Files:** `docker-compose.yml`, `compose.server.yml`, `compose.dev.yml`, `Caddyfile.local`, `Caddyfile.server`, `docker/Dockerfile.{app,web,sandbox,review,devbox,mocks}`, `docker/opencode/{sandbox,devbox,review,economics}.json`, `docker/opencode/agents/{dba-fixer,cfo-sync}.md`, `docker/egress-proxy/*`, `docker/devbox/entrypoint.sh`, `devconsole/app.py`, `mocks/bin/{entire,opencode}` (Python scripts), `scripts/backup.sh`, `.github/workflows/{ci,deploy-ssh}.yml`, tests.
- Fake `entire`: `version`, `enable --agent opencode` (installs git `commit-msg`/`post-commit` hooks adding `Entire-Checkpoint: <12 hex>` trailer and `refs/entire/checkpoints/<2>/<id>`), `status [--detailed]`, `checkpoint list --json`, `graph diff <old_dir> <new_dir> --json` (AST-based public symbol diff: removed/changed signatures), `graph impact <file:symbol> --json`, `graph neighbors`, `review ...` (JSON findings), `login` (prints URL + `ABCD-1234` code then exits 0 after `ENTIRE_FAKE_LOGIN_DELAY`), `auth status|revoke`, `dispatch`, `doctor`, `plugin install graph`, `hooks opencode turn-end`.
- Fake `opencode`: `--version`; `run --agent dba-fixer "<msg>"` reads `/work/.dba/brief.md` (or `$DBA_BRIEF`), calls `$OPENCODE_BASE_URL/chat/completions` with `$DBA_GATEWAY_TOKEN` model `fixer`, applies the unified diff from the answer with `git apply`, prints a transcript; `export` prints JSON; `web` serves a placeholder page on the port.
- devconsole: FastAPI `GET /status`, `POST /entire/enable`, `/graph/init`, `GET /checkpoints`, `POST /doctor`, `/hooks/test`, `/entire/login` (+ `GET /events` SSE), `/entire/logout`, `/dispatch` — each runs the section-22.1 command via an injectable runner.
- [ ] Tests: `docker compose config` validates for laptop, server overlay, devbox profile; Caddyfile routing assertions (`/api /auth /webhooks` → api with `flush_interval -1`, `/devbox-api` → devbox); fake CLIs unit-tested in temp git repos; devconsole endpoints with a fake runner; server overlay keeps temporal-ui unpublished and 7233 unpublished.

### Task 4: Web UI (Next.js + shadcn)
**Files:** `web/**` (routes in spec 16.4 each with `loading.tsx`/`error.tsx`, `template.tsx`, `components/ui` (shadcn CLI), `components/composed/*` (16.5.2), `lib/{api,query-keys,use-run-events,motion,utils,types}.ts`), `web/tests/**` (Vitest + Testing Library), `web/e2e/**` (Playwright, run against the stack in Task 14).
- `lib/types.ts` mirrors the contracts above (string unions). `lib/api.ts` typed client for every 16.2 endpoint (same-origin `/api`). `useRunEvents(runId)` EventSource with `Last-Event-ID` resume, patches TanStack Query cache, exposes `status: "live"|"reconnecting"`.
- Middleware: unauthenticated (no `dba_session` cookie) → `/connect`, except `/connect`, `/analyze`, `/r/*`.
- [ ] Tests: each composed component (render, a11y roles/labels, keyboard, reduced-motion), VerdictBadge icon+text for all verdicts, KanbanBoard places cards by state, ApprovalsTable selection + confirm flow + optimistic revert on error, useRunEvents reconnect/dedupe, forms validation (repo URL accepts URL / `owner/repo` / PR link), every page renders loading/empty/error states (MSW).

### Task 8: Sandbox drivers + sandbox/analysis activities
**Files:** `backend/sandbox/{driver,docker_driver,local_driver}.py`, `backend/temporal/activities/{sandbox,graph,analysis,opencode,verify,review}.py`, tests.
**Produces:** `SandboxDriver` protocol: `async create(item_id, image, cpus, memory, network) -> SandboxHandle`, `exec(h, cmd:list[str]|str, env=None, timeout=None, workdir="/work/repo") -> ExecResult{code, stdout, stderr, duration_s}`, `write_file`, `read_file`, `connect(h, network)`, `disconnect(h, network)`, `copy_out(h, path, dest)`, `destroy(h)`, `janitor(max_age_s)`. `LocalDriver` (temp dirs on host, for tests/dev, network ops recorded) and `DockerDriver` (docker CLI, labels `dba.item`, resource flags, read-only rootfs + tmpfs). Activities (names from spec section 14) with typed dataclass inputs/outputs, heartbeats every 30 s.
- [ ] Tests: LocalDriver full create→clone (from mock git)→`uv sync`→baseline→apply_bump→run_tests→opencode_fix (fake CLI + gateway) → patch guard → commit trailer → export_bundle; DockerDriver integration test (skipped without Docker) with network connect/disconnect; flaky rerun; env_error path; guard deny resets tree.

### Task 9: Temporal workflows, remaining activities, worker
**Files:** `backend/temporal/workflows/{backlog_run,item,actions,pr_watch,eval,public,economics_sync,entire_login}.py`, `backend/temporal/activities/{events,github,llm,gateway_tokens,planning,report,economics,actions}.py`, `backend/temporal/{worker,client,queues}.py`, tests.
- ItemWorkflow implements the section-9 state machine exactly, `record_event` per transition, budgets (25 turns, 200k tokens, item USD cap, 15 min), fixer ≤3 attempts, verifier REJECT → FIXING once, `finally` destroy_sandbox + export_checkpoints, `override_verdict` signal, `get_status` query.
- BacklogRunWorkflow: ingest → plan → children with bounded concurrency N → integration_pass → propose_actions → wait approvals (validated update `approve_actions`/`reject_actions`, 24 h timeout) → ActionExecutionWorkflow; `pause`/`resume` signals; cancellation cleans up.
- ActionExecutionWorkflow: hard rules from section 13 (installed repos only, merge requires CONFIRM + green + integration clean + checks green with durable timer ≤20 min, close only DISMISS, NEEDS_HUMAN → label+comment only, head-SHA change → CANCELLED).
- [ ] Tests with `WorkflowEnvironment.start_time_skipping()` and mocked activities: every lifecycle path in section 9, every decision-table row end to end, pause/resume, cancel cleanup, approvals timeout, duplicate start dedupe, head SHA change, replay determinism test (`Replayer`).

### Task 10: FastAPI app
**Files:** `backend/api/{app,deps,auth,sse}.py`, `backend/api/routes/{repos,runs,items,actions,public,admin,webhooks,blobs}.py`, tests.
- All 16.2 endpoints. Session: signed cookie `dba_session` (itsdangerous, `SESSION_SECRET`), GitHub OAuth (mock world in mock mode). Admin = logins in `ADMIN_LOGINS`. SSE `/api/runs/{id}/events` polls `events_after` every 500 ms, honours `Last-Event-ID`, `id:` per event, heartbeat comments. Public analyze rate-limited per IP (in-memory token bucket) and never executes code. Webhook HMAC verified → `PRWatchWorkflow` with id `pr-{repo}-{pr}-{head_sha}`.
- [ ] Tests with httpx AsyncClient + a fake Temporal client: auth flows, 401/403 paths, every route happy + error, SSE resume, webhook bad signature, rate limit.

### Task 11: Evals, economics, Entire login, cfo.ai
**Files:** `backend/temporal/workflows/{eval,economics_sync,entire_login}.py` activity bodies, `backend/integrations/{entire,cfo}.py`, `dataset/cases/*.yaml`, `backend/evals/{score,dataset}.py`, `mocks/cfo.py`, tests.
- Scoring: accuracy, confusion matrix, green rate, NEEDS_HUMAN rate, cost/item, time/item; economics snapshot JSON + CSV export; `entire login` stdout parsing (URL regex + device code `[A-Z0-9]{4}-[A-Z0-9]{4}`) with raw fallback.

### Task 12–14 (orchestrator): integration, compose E2E, UI verification
- 12: wire everything, full-suite run, fix integration bugs.
- 13: `tests/e2e/test_full_run.py`: real Temporal dev server + all workers in-process + mock world + LocalDriver → start run on `demo-org/demo-app`, assert verdict per PR equals the scenario table, approvals → mock GitHub state shows comments/labels/merge/close. Smoke tests (`tests/smoke/`): compose up (mock mode), health endpoints, one run. Blackbox tests: only HTTP against Caddy.
- 14: Playwright E2E for the user journey (16.10) + manual check in Chrome (claude-in-chrome), screenshots, a11y check; then PR.
