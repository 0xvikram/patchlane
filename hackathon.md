# Patchlane — neatHack build log

## Project

**Patchlane** takes a repository's Dependabot backlog to zero: every pull request ends merged, fixed, or dismissed, with proof.

Problem: Dependabot opens update pull requests faster than teams can judge them, so most are left unmerged. On 9 Oct 2026 GitHub's public search showed 61.3 million open Dependabot pull requests, 58.1 million of them older than six months.

## Team

Pending: names to be confirmed by the team.

## Stack

- Python 3.12, managed with uv
- OpenAI-compatible model client (provider not chosen yet)
- neatlogs for tracing agent runs
- Entire for checkpoints of coding-agent sessions
- cfo.ai for the business plan (not started)

## Build log

### Sat 10 Oct 2026

- Created the repository with the planning files only (`spec/`). A practice build of this spec was done in a separate private repository before kickoff; none of that code is here.
- Enabled Entire in the repository with Claude Code as the agent.
- Added the project skeleton: settings, config, the model client, neatlogs tracing and a smoke script that makes one traced model call.
- Tests: 13 unit tests pass (`uv run pytest`). They use a fake model endpoint; no real model call has been made yet.
- Found: the `openai` 3.x SDK uses `httpx2`, so `respx` cannot intercept its requests. The tests inject an `httpx2` mock transport instead.
- Not done yet: no model provider key and no neatlogs key, so the smoke script stops with "Not configured" and no trace exists.

## Demo

Pending.

## Known limitations and next steps

- No real model call or neatlogs trace yet. Next: add keys, run `uv run python -m scripts.smoke_llm`, link the trace here.
- Next block: the core loop on one pull request (sandbox, baseline tests, apply the update, run tests, fixer, patch guard).

## Submission

- [ ] Public repository with commits dated during the hackathon
- [ ] neatlogs trace links, including a before and after pair
- [ ] A run where an action failed and the agent recovered
- [ ] Entire checkpoints
- [ ] cfo.ai business plan: pricing, costs, revenue, runway
- [ ] Demo video, three minutes or less, covering neatlogs, Entire and cfo.ai
- [ ] Posts tagged #neatHack
