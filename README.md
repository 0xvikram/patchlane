# Patchlane

Patchlane takes your Dependabot backlog to zero: every PR ends merged, fixed, or dismissed, with proof.

Built for [neatHack](https://neatlogs.com/hackathon), 10–12 October 2026.

## Status

Submitted as work in progress. What exists: the design, the project skeleton, the model client, neatlogs tracing, and a smoke script that makes one traced model call. The agent loop described below is designed but not built yet. See [`hackathon.md`](hackathon.md) for the build log.

A practice build of this spec was done in a separate private repository before kickoff. None of that code is in this repository; `spec/001-open-items.md` records what that practice run taught us.

## What it is designed to do

This section describes the design, not working code. For each open Dependabot pull request in a repository, Patchlane will:

1. Reads what changed in the dependency.
2. Finds where the repository uses it.
3. Decides whether the change can reach the repository's code.
4. Applies the update and runs the tests, and fixes the repository's code if they fail.
5. Ends with a verdict and the evidence behind it: merge, fix then merge, dismiss, or needs a human.

## Planning files

- [`spec/001-init-spec.md`](spec/001-init-spec.md): the design
- [`spec/001-plan.md`](spec/001-plan.md): the implementation plan
- [`spec/001-api-contract.md`](spec/001-api-contract.md): the HTTP contract
- [`spec/001-open-items.md`](spec/001-open-items.md): decisions, findings and open questions

## Run it

```bash
uv sync
cp .env.example .env        # then fill in the keys
uv run pytest
uv run python -m scripts.smoke_llm   # one traced model call
```

The model ids are set in `config.toml` (currently `gemini-2.5-flash` through Google's OpenAI-compatible endpoint).
