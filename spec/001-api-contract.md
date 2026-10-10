# dba HTTP API contract (spec §16.2)

Shared by `backend/api` (FastAPI) and `web/lib/api.ts`. All JSON; errors are `{"detail": string}` with a
proper status (400 validation, 401 not signed in, 403 not admin / not allowed, 404, 409 conflict, 429 rate limit).
Times are ISO-8601 UTC strings. Enum values are the strings from `backend/core/contracts.py`.

## Shared shapes
```ts
type Verdict = "MERGE" | "FIX_THEN_MERGE" | "DISMISS" | "NEEDS_HUMAN";
type ItemState = "QUEUED"|"SUPERSEDED_CHECK"|"PREPARING"|"ANALYZING"|"APPLYING"|"TESTING"|"FIXING"|"DRAFTED"|"VERIFYING"|"DONE"|"DONE_DISMISS"|"DONE_NEEDS_HUMAN";
type RunStatus = "PENDING"|"PLANNING"|"RUNNING"|"PAUSED"|"AWAITING_APPROVAL"|"EXECUTING"|"COMPLETED"|"FAILED"|"CANCELLED";
type Reachability = "REACHABLE"|"UNREACHABLE"|"UNCERTAIN";
type ActionType = "comment"|"label"|"push_fix"|"combined_pr"|"close"|"merge";
type ActionStatus = "PROPOSED"|"APPROVED"|"REJECTED"|"EXECUTED"|"FAILED"|"CANCELLED";

PRRef        { number, title, head_ref, head_sha, url, created_at, body }
PackageBump  { name, from_version, to_version, manifest, dev_only }
Advisory     { id, cve, severity, cvss, summary, vulnerable_symbols: string[], fixed_in, fix_commit_url }
CallSite     { file, line, symbol, code }
TestResult   { status: "pass"|"fail"|"env_error", total, passed, failed: string[], errors: string[], new_failures: string[], log_ref, duration_s, flaky_rerun }
AnalysisReport { reachability, paths: string[][], risk: "LOW"|"MED"|"HIGH", expected_breakage: string[], notes, evidence_refs: string[] }
DraftVerdict { verdict, reason_code, reachability, confidence, summary, claims: {claim, evidence_ref}[] }
VerifierDecision { decision: "CONFIRM"|"REJECT"|"DOWNGRADE", checks: Record<string, boolean>, review: {verdict, ref, source} | null, notes }
Action       { action_id, run_id, item_id, repo, pr, type, level, payload, status, head_sha,
               approved_by: string|null, executed_at: string|null, result: object|null,
               item: { package: string, from_version: string, to_version: string, verdict: Verdict|null } }
RunSummary   { run_id, status, total, by_verdict: Record<Verdict, number>, actions_proposed, actions_executed, usd, report_ref }

Repo         { repo_id, full_name, default_branch, installation_id, action_level: 0..5, auto_approve: ActionType[],
               open_dependabot_prs: number|null, approvals_waiting: number, latest_run: RunBrief|null }
RunBrief     { run_id, repo, repo_id, mode, status, started_at, finished_at, total, resolved, approvals_waiting }
ItemCard     { item_id, run_id, prs: PRRef[], packages: PackageBump[], advisories: Advisory[], state, verdict: Verdict|null,
               reason_code: string|null, confidence: number|null, attempts, priority, group: string|null, updated_at }
FixAttemptView { attempt, diff_ref, files: string[], guard: "allow"|"deny", guard_reasons: string[], test_result_ref,
               test_status, commit_sha, entire_checkpoint_id, checkpoint_url: string|null, tokens_in, tokens_out, usd }
ItemDetail   = ItemCard & { repo, base_sha, analysis: AnalysisReport|null, draft: DraftVerdict|null,
               verifier: VerifierDecision|null,
               final: { verdict, reason_code, confidence, summary } | null,
               evidence: { changed_symbols: string[], call_sites: CallSite[], dynamic_access: CallSite[],
                           impact_paths: string[][], baseline: TestResult|null, after: TestResult|null },
               attempts: FixAttemptView[], actions: Action[],
               override: { user_login, verdict, reason, at } | null,
               links: { neatlogs: string|null, pr: string } }
Run          = RunBrief & { prompt_label, share_id: string|null, summary: RunSummary|null, items: ItemCard[],
               usd: number, cost_cap_usd: number }
Report       { run_id, repo, finished_at, summary: RunSummary|null,
               stats: { cleared: number, hours_saved: number, usd: number, total: number },
               items: { item_id, prs: PRRef[], packages: PackageBump[], verdict, reason_code, confidence, summary }[] }
Event        { id, run_id, item_id: string|null, type, from_state, to_state, detail: object|null, at }
```

## Auth
| Method | Path | Response |
|---|---|---|
| GET | `/auth/login?next=/repos` | 302 → GitHub authorize (mock world in mock mode) |
| GET | `/auth/callback?code&state` | sets `dba_session` cookie (HttpOnly, SameSite=Lax, signed), 302 → `next` or `/repos` |
| GET | `/auth/me` | `{ login, name, avatar_url, is_admin }` or 401 |
| POST | `/auth/logout` | 204, clears cookie |

## Product API (session required)
| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/healthz` | | `{ ok: true, version }` (no auth) |
| GET | `/api/repos` | | `{ repos: Repo[] }` (syncs installations on first call) |
| GET | `/api/repos/{repo_id}` | | `Repo` |
| PATCH | `/api/repos/{repo_id}` | `{ action_level?, auto_approve? }` | `Repo` |
| GET | `/api/repos/{repo_id}/backlog` | | `{ repo: Repo, prs: { number, title, url, head_sha, created_at, package, from_version, to_version, bump_type, dev_only, advisories: Advisory[], group, superseded_by, priority }[] }` |
| POST | `/api/repos/{repo_id}/plan` | `{}` | `{ items: { prs: number[], packages: PackageBump[], priority, group, superseded_by, bump_type }[], estimate: { usd, minutes, items } }` |
| GET | `/api/runs?repo_id=` | | `{ runs: RunBrief[] }` |
| POST | `/api/runs` | `{ repo_id, prompt_label?: "production", pr_numbers?: number[] }` | 202 `{ run_id }`; 409 `{detail, run_id}` if a run is already active for the repo |
| GET | `/api/runs/{run_id}` | | `Run` |
| GET | `/api/runs/{run_id}/events` | header `Last-Event-ID` or `?after=` | SSE: `id: <event.id>`, `event: <event.type>`, `data: <Event JSON>`; comment heartbeat every 15 s |
| POST | `/api/runs/{run_id}/pause` · `/resume` · `/cancel` | | 202 `{ status }` |
| GET | `/api/items/{item_id}` | | `ItemDetail` |
| POST | `/api/items/{item_id}/override` | `{ verdict, reason }` | `{ ok: true }` |
| GET | `/api/blobs/{sha}` | | raw content, `text/plain; charset=utf-8` (diffs, logs, transcripts) |
| GET | `/api/runs/{run_id}/actions` | | `{ actions: Action[] }` |
| POST | `/api/runs/{run_id}/approvals` | `{ approve: string[], reject: string[] }` | `{ actions: Action[] }` |
| GET | `/api/runs/{run_id}/report` | | `Report` |
| POST | `/api/runs/{run_id}/share` | | `{ share_id, url }` |

Event types emitted on the run stream: `run_status` (detail `{status}`), `run_planned` (`{total, superseded}`), `item_state` (from/to), `item_verdict` (`{verdict, reason_code, confidence}`), `attempt` (`{attempt, guard, test_status}`), `actions_proposed` (`{count}`), `action_status` (`{action_id, status}`), `cost` (`{usd_total}`), `log` (`{message}`).

## Public (no auth)
| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/public/reports/{share_id}` | | `Report` |
| POST | `/api/public/analyze` | `{ repo: string }` (URL, `owner/repo`, or PR URL) | 202 `{ run_id, repo }`; 400 invalid repo; 429 rate limited; 503 public mode disabled |
| GET | `/api/public/runs/{run_id}` | | `Run` (public-mode runs only) |
| GET | `/api/public/runs/{run_id}/events` | | SSE, same format (public-mode runs only) |

## Webhooks
`POST /webhooks/github` — HMAC `X-Hub-Signature-256`; 401 bad signature; 202 `{ workflow_id }` or 200 `{ ignored: true }`.

## Admin (session + admin)
| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/admin/ops` | | `{ version, git_sha, queues: { name, healthy, workers, detail }[], integrations: { name, status: "ok"|"degraded"|"down"|"mock", detail }[], links: { temporal_ui, neatlogs, entire, cfo } }` |
| GET | `/api/admin/evals` | | `{ evals: { eval_id, prompt_label, started_at, cases, accuracy, green_rate, needs_human_rate, usd_per_item, ms_per_item, confusion: Record<label, Record<predicted, number>> }[], dataset_size }` |
| POST | `/api/admin/evals` | `{ prompt_label, models?: { coder?, orchestrator? } }` | 202 `{ eval_id }` |
| GET | `/api/admin/economics.json` · `.csv` | | snapshot |
| POST | `/api/admin/economics/sync` | `{ label? }` | 202 `{ workflow_id }` |
| POST | `/api/admin/integrations/entire/login` | | 202 `{ workflow_id }` (code arrives on `/api/admin/events`) |
| GET | `/api/admin/integrations/entire/status` | | `{ connected, connected_as, detail }` |
| POST | `/api/admin/integrations/entire/logout` | | `{ ok }` |
| POST | `/api/admin/integrations/bedrock/test` | | `{ ok, model, ms, usd, content }` |
| GET | `/api/admin/events` | | SSE: `login_code {url, code, raw}`, `login_done {connected_as}`, `login_failed {reason}`, `sync_progress {step, detail}`, `log {line}` |

## Devbox (through Caddy at `/devbox-api`, admin)
`GET /status`, `POST /entire/enable`, `POST /graph/init`, `GET /checkpoints`, `POST /doctor`, `POST /hooks/test`, `POST /entire/login`, `GET /events` (SSE, same login events), `POST /entire/logout`, `POST /dispatch`. Each command endpoint returns `{ ok, code, stdout, stderr }`; `/status` returns `{ entire_version, opencode_version, status, auth }`.

## Additions during implementation
| GET | `/api/public/config` | | `{ install_url, public_analysis }` (no auth) |
| Devbox `GET /status` | | `{ workspace, entire_version, entire_status, entire_auth, opencode_version }`, each a command result `{ cmd, ok, code, stdout, stderr }` (supersedes the string fields above) |

## Security notes (authorization, public analysis, limits)
- **Per-repository authorization.** At sign-in the API reads `GET /user/installations/{id}/repositories` with the user's
  token and stores, in the signed `dba_session` cookie, `read_repo_ids` (repos the user can only see) and
  `write_repo_ids` (GitHub `permissions.push` or `permissions.admin`). Every read of a repo, run, item, action, report or
  event stream needs the repo among those; every mutation (start / pause / resume / cancel run, approvals, `PATCH
  /api/repos/{id}`, override, share) needs it in `write_repo_ids`. Admins bypass both. 403 detail is `You do not have
  access to this ...` (cannot see it) or `You need write access to this ...` (can see, cannot change). Public-mode runs
  stay readable by any signed-in user and controllable by admins only.
- **Session caps.** A cookie is limited to ~4 KB and a signed repo id costs ~7 bytes, so at most 400 ids are stored
  (writable first, then read-only) and at most 1000 repos per installation are examined at sign-in. Repos beyond the caps
  are not accessible (fail closed). The user token is not stored, so permissions are as fresh as the last sign-in
  (session lifetime 7 days): `?refresh=1` re-syncs the App's installations but cannot refresh a user's permissions.
  Sessions issued before this change lack the id lists and are answered with 401 (sign in again).
- **`GET /api/repos?refresh=1`** forces a full installation sync: 403 unless admin or the user has write access to at
  least one repo; 429 (`Retry-After: 60`) when the same user already forced one within 60 s.
- **`PATCH /api/repos/{id}`** `auto_approve` accepts only `comment`, `label`, `push_fix`; `merge`, `close` and
  `combined_pr` are 400 (they always need an explicit approval). Values stored earlier are filtered the same way when a
  run starts.
- **`POST /api/runs/{id}/approvals`** with both lists: ids are validated together (database, then the workflow's own
  `awaiting` list) before either update is sent; 409 means nothing was applied. If the workflow still rejects the approve
  update after the reject update went through (a race the API cannot undo), the 409 detail ends with `(already rejected:
  ...)`.
- **`POST /api/public/analyze`** only accepts repositories GitHub serves anonymously: it fetches `GET /repos/{repo}`
  without credentials and needs `200` with `private: false`, otherwise `400 Only public repositories can be analyzed`
  (private, missing and blocked repos are indistinguishable). The PR list passed to the run is explicit: a PR URL gives
  that PR, otherwise the first `config.public.max_prs` (default 10) open Dependabot PRs of the newest 300 open PRs.
  `429` (`Retry-After: 60`) while `config.public.max_concurrent_runs` (default 2) public runs are non-terminal; the
  per-IP rate limit is applied first. Anonymous GitHub calls share the server's 60 requests/hour limit: a rate-limited
  check answers 503.
- **`GET /api/blobs/{sha}`** is readable when some run that references the blob is readable (fix attempt diff/test log,
  any ref in the item's evidence or verdict JSON, `runs.summary.report_ref`); a blob nothing references is admin-only.
  Unknown and unreferenced blobs are both 403 for non-admins.
- **Startup.** `create_app` raises when the API is publicly reachable (`PUBLIC_BASE_URL` starts with `https://`, or
  `GITHUB_API_URL` is not the mock world: host `mocks`, `localhost`, `127.0.0.1` or `::1`) and `SESSION_SECRET`,
  `GITHUB_WEBHOOK_SECRET` or `GATEWAY_SIGNING_KEY` is a shipped default, contains `change-me` or is shorter than 32
  characters.
- **Mock GitHub.** `GET /user/installations/{id}/repositories` returns the demo repo with `permissions` (the demo user has
  push); `POST /_mock/github/permissions {repo, permission: none|read|write|admin}` changes it, `POST
  /_mock/github/repos {full_name, private}` registers extra repos for `GET /repos/{owner}/{repo}`. `GET
  /repos/{owner}/{repo}` and its `/pulls` listing are anonymous for public repos; everything else still needs a token.
