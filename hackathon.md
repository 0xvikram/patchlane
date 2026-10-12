# Patchlane — neatHack build log

## Project

**Patchlane** takes a repository's Dependabot backlog to zero: every pull request ends merged, fixed, or dismissed, with proof.

Problem: Dependabot opens update pull requests faster than teams can judge them, so most are left unmerged. On 9 Oct 2026 GitHub's public search showed 61.3 million open Dependabot pull requests, 58.1 million of them older than six months.

## Team

Pending: names to be confirmed by the team.

## Stack

- Python 3.12, managed with uv
- OpenAI-compatible model client, currently pointed at `gemini-2.5-flash`
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
- Added keys locally. The smoke script made its first real model call with neatlogs tracing on: `model: gemini-2.5-flash`, `reply: patchlane online`, `tokens: 8 in, 3 out`.
- Found: `gemini-2.5-flash` spends output tokens on thinking, so a 20-token cap returned an empty reply. Raised the cap to 512.

### Mon 12 Oct 2026

- No agent code was added after Saturday. We are submitting what exists and saying so plainly.
- Re-ran the checks: 13 tests pass, and the smoke script again returned `patchlane online` with tracing on (workflow name `patchlane-smoke` in neatlogs).
- Recorded a short demo video of the current state. The narration is an AI voice.

## Demo

A short video of the current state: the problem, the design (labelled as design), and the real traced smoke run. Link: pending.

## Known limitations and next steps

- The agent loop is not built: nothing yet reads a pull request, runs tests, fixes code or gives a verdict.
- There is no before and after trace pair and no failed-then-recovered run, because there is no agent run yet.
- Entire is enabled in the repository, but no commit carries a checkpoint yet.
- The cfo.ai business plan is not started.
- Next block: the core loop on one pull request (sandbox, baseline tests, apply the update, run tests, fixer, patch guard).

## Submission

- [x] Public repository with commits dated during the hackathon
- [ ] neatlogs trace links, including a before and after pair
- [ ] A run where an action failed and the agent recovered
- [ ] Entire checkpoints
- [ ] cfo.ai business plan: pricing, costs, revenue, runway
- [ ] Demo video, three minutes or less, covering neatlogs, Entire and cfo.ai
- [ ] Posts tagged #neatHack
