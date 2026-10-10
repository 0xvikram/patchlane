# Spec 001 — open items, decisions and questions

Log for the reviewer (Hiten). Each entry: what, why, what I did, what I need from you.

## Decisions taken before the run (from Q&A)
- One branch `feat/001-init-spec`, one PR; full schema in a single Alembic migration (`backend/db/migrations/versions/0001_initial.py`).
- No real credentials: every external service is mocked by `mocks/` (GitHub API + OAuth + git hosting, Bedrock OpenAI-compatible, OSV, PyPI, cfo.ai MCP) and fake `entire` / `opencode` CLIs (`mocks/bin/`). Real clients are used everywhere; only base URLs differ. Put real values in `.env` to switch.
- Full scope including devbox/devconsole, Entire review, cfo.ai sync and oauth2-proxy overlay.

## Schema additions beyond spec section 15 (all in migration 0001)
- `runs.repo` (owner/name, needed for public mode where no `repos` row exists) and `runs.summary` (RunSummary JSON).
- `work_items.repo`, `work_items.base_sha`, `work_items.group_key`.
- `fix_attempts.guard_reasons`, `fix_attempts.test_status`.
- `actions.level`, `actions.head_sha` (needed for the "head SHA changed" cancellation rule).
- `costs.id` (surrogate PK) and `costs.at`; `eval_results` PK `(eval_id, case_id)` and `at`.

## Placeholders you must fill
- `config.toml` `[llm.models]` ids are placeholders (`us.zai.glm-5.3`, `moonshotai.kimi-k2.5`, `zai.glm-4.7-flash`) — confirm in the Bedrock console (spec §31 #8, #37, #38). `[pricing]` numbers are placeholders.
- `config.toml` defaults to laptop values (`concurrency = 1`, `cpus = 1`, `memory = "2g"`); server values are in comments of spec §30.

## [VERIFY] items from spec §31
Not verifiable without the real services; each is behind an adapter with a fake. Status per item is tracked below as implementation proceeds.

## Design decisions taken during implementation (please review)
1. **Gateway token never enters workflow history.** Spec §8.3 shows `issue_gateway_token` returning the token to the workflow, which contradicts §5.4 ("no secrets in workflow inputs or history; activities mint gateway tokens themselves"). `opencode_fix` (and `entire_review`) mint the per-attempt token inside the activity and revoke it in `finally`. `worker-sandbox` and `worker-review` therefore get `GATEWAY_SIGNING_KEY` and DB access (they already mount `./data`).
2. **Sandboxes never clone with a token.** Instead of a short-lived installation token inside the sandbox (§18.2), the `github` worker runs `fetch_repo_bundle` (clone with the installation token on the github worker, `git bundle` of base + PR heads into the blob store) and the sandbox clones from that bundle. Same outcome, no credential in the sandbox even briefly, no network needed for the clone step.
3. **Decision table runs inside workflow code.** `core/decision.py` is pure and deterministic, so `ItemWorkflow` calls it directly instead of through an activity.
4. **`record_event` also updates `work_items` / `runs` columns** in the same transaction (`item_update`, `run_update`), so the UI never sees an event without the matching row state.
5. **Demo world** (`mocks/demo/scenarios.py`): 7 Dependabot PRs on `demo-org/demo-app` covering every verdict path (SUPERSEDED, MERGE, FIX_THEN_MERGE, security MERGE, DEV_ONLY_NO_IMPACT, UNREACHABLE_AND_BREAKING, NEEDS_HUMAN). The e2e test asserts each expected verdict.
6. **Superseded security PRs are dismissed as SUPERSEDED without reachability analysis.** The newer PR for the same package carries the security fix, so dismissing the older one is safe, but strictly read, the hard rule ("security update with REACHABLE/UNCERTAIN code is never DISMISS") would forbid it because no analysis ran (reachability recorded as UNCERTAIN). I kept DISMISS/SUPERSEDED. Tell me if you want superseded security PRs analysed or turned into NEEDS_HUMAN instead.

## Questions from the core-logic implementation (decision table, bump, usage)
- Decision table gaps in spec §10.2 that I had to fill: `tests="n/a"` outside the dev-only row → NEEDS_HUMAN/ENV_FAILURE; "no symbols called + dynamic access + fixed" → FIX_THEN_MERGE (confidence ≤ 0.7). Confirm.
- Confidence: every verdict starts at 0.9; dynamic access caps MERGE/FIX_THEN_MERGE at 0.7; missing package source caps at 0.5. Should FIX_THEN_MERGE / NEEDS_HUMAN start lower?
- `apply_bump` edits manifests only in the PR's manifest directory (+ its `requirements/` subdir), not the whole repo. Right for monorepos?
- `apply_bump` does not widen upper bounds: `>=2.0,<3` bumped to 3.1 becomes `>=3.1,<3` (unsatisfiable → resolution failure → NEEDS_HUMAN). Should it widen `<3` instead?
- `scan_dynamic_access` ignores test files. Keep?
- Supersession is keyed on (package, manifest), so the same package in two directories of a monorepo is not superseded.

## LLM / gateway notes
- Upstream 401/403 (bad Bedrock key) → gateway returns **502 `upstream_auth_error`** so it can't be mistaken for a bad sandbox token. Other upstream 4xx pass through (key redacted); 5xx → 502.
- Gateway budget: concurrent requests that passed the budget check together can overshoot `max_tokens` slightly (checked before the call, accounted after).
- Bundled prompts (`backend/harness/prompts/*.md`) are my wording; v2 analyst asks for evidence refs on every path and prefers UNCERTAIN under dynamic access. Push them to neatlogs prompt management as `dba-analyst` etc. with labels v1/v2/production when the key exists.
- `submit_analysis.evidence_refs` requires ≥ 1 entry (spec §8.1 "evidence refs required").

## API / activities notes
- `ItemDetail.attempts` is the `FixAttemptView[]` array (the contract also had a numeric `attempts` on ItemCard; in ItemDetail the count is its length).
- PAUSED is written by the API on pause (the workflow keeps running, just stops dispatching).
- Rate limit + double-start guard are in-process (single API process). Caddy must overwrite `X-Forwarded-For` (it does by default for reverse_proxy).
- **[VERIFY]** Entire checkpoint URL format used in item detail: `https://entire.io/gh/{CHECKPOINT_REPO}/checkpoints/{id}`; ops links to entire.io / cfo.ai are placeholders.
- **[VERIFY]** cfo.ai MCP tool names/arguments (`list_scenarios`, `edit_scenarios`, `inspect_table_blocks`, `edit_table_blocks`) are assumed; the fake MCP server implements those. Default `CFO_SYNC_MODE=direct` (MCP calls from the activity); `opencode` mode runs the `cfo-sync` OpenCode agent as the spec describes.
- Business assumptions in `backend/evals/economics.py`: $49/repo/month, 12 PRs/repo/month, $80/month server, 30 engineer-minutes saved per PR, 0.5 h saved per cleared PR in the report. Margin = (price − cost per PR × PRs/month) / price.
- `fetch_repo_bundle` uses `git clone --bare` (not `--mirror`) so `refs/pull/*` never enters bundles.

## Findings from running the REAL Entire / OpenCode CLIs in the sandbox image (infra task)
These answer spec §31 items; mock mode uses fakes that follow the plan's contract, so switching `MOCK_CLIS=0` needs the adapters noted below.
- **#1 (OpenCode headless → Entire capture): NOT confirmed.** Real Entire adds no `Entire-Checkpoint` trailer / `refs/entire/*` on a plain commit without an agent session. The fake always adds them. Fallback in place: transcript stored as blob; event `checkpoint_missing` when no trailer.
- **#3 (`entire review` with OpenCode): NO.** Real CLI: "no review runner adapter; available: claude-code, codex, pi". The workflow's in-house consistency check is therefore the real path; `entire review` only works with a supported runner.
- **#5/#21 (OpenCode config + gateway): YES.** Real `opencode run --agent dba-fixer` read the brief and edited the file via a streaming gateway; `@ai-sdk/openai-compatible` is bundled. Needed `permission.external_directory: {"/work/.dba/*": allow}` (added to `dba-fixer.md`). OpenCode makes one extra tool-less "title" request per session; the gateway counts it in the budget.
- **#14 (`entire graph`): CLI differs from the spec.** `graph diff` takes git revs (`--base <rev> --head <rev> --repo . --json`), not two directories; `impact`/`neighbors` take `--symbol NAME|file:line --repo . --format json`. Python fully supported; third-party edges appear as `external:symbol:pkg.func`. The sandbox layer falls back to an in-process AST symbol diff when `entire graph diff` fails. **Adapter needed for real mode** (commit old/new sources into a temp git repo, then diff by revs — the spec's original idea).
- **#24 (`entire login` without TTY): YES**, output has `Device code: XXXX-XXXX` and the URL on separate lines; parsers handle both. Real `entire auth status` exits 0 even when logged out ("○ Not logged in") — decide from text. `entire dispatch` needs login unless `--local`.
- **#30 (Docker Desktop network connect/disconnect): YES**, verified on arm64; sandboxes reach only the allowlist through tinyproxy; SSE unbuffered through real Caddy (#33).
- **#35 (oauth2-proxy env names): YES** on v7.15.5. **#36** (Temporal UI behind oauth2-proxy with real Google login) not verifiable here.
- Spec §22.2 step 7 bug: `git bundle create out.bundle HEAD 'refs/entire/checkpoints/*'` treats the glob as a pathspec → empty bundle. Using `--glob='refs/entire/checkpoints/*'`.
- `sandbox-install` network is `internal: true` (egress only via the proxy) — otherwise sandboxes would have a direct internet route.
- Pinned images: temporalio/temporal 1.9.1, temporalio/ui 2.55.0, oauth2-proxy v7.15.5, caddy 2.11.7-alpine, OpenCode 1.18.35. Entire can't be pinned via install.sh (stable resolved to 0.11.4).
- Open: pin `OAUTH2_PROXY_TRUSTED_IPS` to the Docker subnet? (currently only a warning; proxy reachable only from Caddy).

## Web UI notes
- Next 16.4: `web/proxy.ts` replaces `middleware.ts` (deprecated, can't coexist). Same redirect rules as spec §16.1.
- All data is fetched client-side with TanStack Query (pages are thin server shells) — spec §16.4's "Server" rendering column is not followed, so Playwright can intercept everything and SSE patches one cache. Tell me if you want server-side initial data.
- shadcn substitutions: Toast → `sonner`; Data Table → Table + Checkbox + Pagination (no registry item); Typography → Tailwind classes; Date Picker → Popover + Calendar. Style `radix-nova`. `components/custom/` is empty (target met).
- Settings page has no Select/Slider because the API only edits `action_level` and `auto_approve`; auto-approve is limited to comment/label/push_fix (merge/close always manual).
- "Undo" on an approval toast sends `reject`; once the workflow has taken the approval the API returns 409 and the UI shows it.
- **Lighthouse ≥ 95 (spec §16.9) not measured** — headless Lighthouse failed (NO_FCP). axe (same rule set) passes with no serious/critical violations on 16 screens in light and dark; keyboard-only walkthrough, reduced motion and phone layout are covered by Playwright.
- lucide-react 1.x has no GitHub brand icon; "Sign in with GitHub" uses `LogIn`.

## Findings from running the full stack locally (Chrome, mock world, Docker sandboxes)
- The whole demo works through the real stack: OAuth (mock), backlog with advisories/supersession/dev-only, run board with live SSE, real Docker sandboxes (uv + pytest), fake OpenCode via llm-gateway producing the `get_json → fetch_json` patch, Entire checkpoint, verifier, approvals (3 merges + 3 closes), report. All 7 verdicts as expected.
- **Do not open `data/dba.sqlite3` with the host `sqlite3` CLI while the stack runs on Docker Desktop (macOS).** WAL shared memory does not work across the host/VM bind mount and the containers start failing with `disk I/O error` (I hit this; a restart recovered it, integrity check ok). Use `docker compose exec api python -c ...` or `scripts/backup.sh`.
- "First click does nothing" during the browser pass: diagnosed as clicks landing before hydration finished in a *background* automation tab (`document.visibilityState === "hidden"`, Chrome throttles it). Click events are delivered (verified with a capture listener) once hydrated; not an app bug.
- Bugs found and fixed during the browser pass: approvals count included auto-approved actions; cost meter stayed $0.00 (run summary now refetched on verdict/status events); board needed horizontal scroll at 1512px (columns now share the width); approvals table now lists waiting decisions first; Bedrock test claimed success on failure and called Bedrock from the API (now via llm-gateway with a minted token).

## Not done / partial (deliberate, tell me if you want them)
- **neatlogs dashboard setup** (spec §20): code detections (`dismiss_without_evidence`, `fix_loop_exhausted`, `cost_spike`, `patch_guard_denied`, `opencode_timeout`), the AI evaluator and prompt labels live in the neatlogs dashboard — needs the real key. In code: every activity is a TOOL span with `session_id = run_id` and `run_id`/`item_id`/`attempt` tags (Temporal interceptor), LLM calls are auto-instrumented, the gateway adds a span per forwarded call, and prompts are fetched from neatlogs when the key is set.
- **Cross-worker trace linking** via a Temporal OTel interceptor (spec §20, [VERIFY] #12) not attempted; grouping is by session (`run_id`) + tags.
- **Merge sequencing "rebase" step** (spec §12): merges wait for green checks with durable timers (≤ 20 min) one at a time, but dba does not ask Dependabot to rebase first; a stale PR fails the head-SHA/merge check and is reported.
- **`hackathon.md`, `business-plan/`, demo video** (spec §27/§29 B8): submission material, not code.
- **Lighthouse score** not measured (see Web UI notes); axe checks pass.

## Independent security/correctness review (before the PR)
A read-only reviewer audited auth, webhooks, gateway, sandbox secrets, patch guard, action rules and workflow determinism. Findings and resolutions:
- **F1 (high) patch guard did not guard what gets pushed** (repo-local git hooks / textconv could change the commit after the guard; push_fix pushed the bundle without re-checking) → fixed: pinned-base `--no-textconv` guard, post-commit re-guard, worker-side re-guard + ancestry check before any push.
- **F2 (high) public analysis could read private installed repos** → fixed: public runs require an anonymous `GET /repos/{repo}` with `private: false`.
- **F3 (high) authorization was per installation, not per repo; no write check** → fixed: session holds visible/writable repo ids; mutations need push/admin; `auto_approve` limited to comment/label/push_fix.
- **F4 (medium) "no checks" counted as green** → fixed: `none` is waited on and fails with `no_checks` at the deadline.
- **F5 (medium) failing child workflow left the run non-terminal** → fixed in the workflow (FAILED + report) and the API (stale runs reconciled).
- **F6 (medium) FIX_THEN_MERGE could merge without the fix pushed** → fixed: cancelled with `fix_not_applied`.
- **F7 (medium) placeholder secrets accepted** → fixed: API refuses to start with default secrets outside mock/laptop mode.
- **F8 (medium) public analyze unbounded** → fixed: PR cap per public run and a concurrency cap.
- **F9 (medium) gateway budget only pre-checked** → fixed: completion limits clamped to the remaining budget, `n>1` rejected. Not fixed: parallel requests can still each pass the pre-check (no atomic reservation).
- **F10 (low) approvals accepted after the window closed** → fixed (refused by the workflow, routed to the late path by the API).
- **F11 (low) blobs readable by any signed-in user** → fixed: blob reads require access to the owning run.
- **F12 (low) patch guard coverage gaps** → fixed (pytest.toml, Django tests, Tests/ dirs, constraints/Pipfile/VCS pin-backs, symlinks, .gitattributes).
- **F13 (low) superseded security PRs** → kept as decision 6 above; note the close is not tied to the superseding PR being merged.
- **F14 (low) misc** → fixed: sandbox `--cap-drop ALL` + no-new-privileges, archive size caps, refresh limited, approvals validated atomically. Not fixed: stateless session cookie (logout does not revoke server-side); `override_verdict` is an eval label and does not block a pending merge.

- Follow-ups from the authorization fix: permissions are as fresh as the last sign-in (sessions last 7 days; the user token is never stored); the repo payload has no `can_write`, so read-only users see 403 toasts on action buttons instead of disabled buttons; sessions hold at most 400 repo ids (fail closed beyond); mixed approve+reject is validated as a whole but sent as two workflow updates.
