---
name: Work order
about: One unit of build work for a coding agent. One issue, one branch, one PR.
title: "[what gets built]"
labels: work-order
assignees: ''
---

<!-- Markdown headings only, so the issue renders on GitHub. Replace every [bracketed] placeholder. -->

Product line: [milestone] | Depends on: [#N, or none] | Run by: [L1 orchestrator with one codex worker, or L2 sonnet session] | Estimate: [hours] h agent time | Crown-jewel: [yes or no]

## User value

[One or two sentences: what a person can do after this that they cannot do today.]

## Context

- Read first: [doc sections, exact].
- Files this issue owns: [paths]. Anything else is touched only if this issue says so.
- Uses from earlier issues: [modules or contracts, with issue numbers].

## Done means

- [ ] [A command or click a person runs, and exactly what they see.]
- [ ] [...]
- [ ] `uv run pytest -q` passes; counts posted in the PR.

## Scope

- [Plain words; at most about one day of build.]

## Out of scope

- [What stops the work widening. Cut-first items, if any, in order.]

## Skills

- ponytail (smallest complete change); [engineering:testing-strategy, impeccable, archify, engineering:documentation, as relevant].

## Engine routing

- Machine: `laptop`, [L1 orchestrator, worktree `.worktrees/issue-N`, or L2 session in `.worktrees/L2`]
- Model: [`opus` orchestrator; build by `terra` (codex plugin); live steps and PR check by `sonnet` subagents] or [`sonnet` (no codex)]
- Effort: [`high` (opus), `high` (terra), `high` (sonnet)]
- Parallel: [`yes, with #N`] or [`no, wait for #N`]

```
Implement #N
```

- Do not send to any external model, codex included: `.env`, the values of OPENROUTER_API_KEY and TYPESAFE_API_KEY, the publish deny-list file. [Add anything else.]
- Live calls: [none, or: probe first, then ..., run by a sonnet subagent; cap USD x.xx. The codex worker never runs live steps.]
- Review: [orchestrator's sonnet check only, or: codex sol, effort medium, once on the finished milestone]

## Human steps

- [None, or the needs:human-action issue number and what it unblocks.]

## Checks

- `uv run pytest -q`: post the pass/fail counts.
- [The specific tests this issue must add.]
- [Command output to paste into the PR. Smokes write only to `.scratch/`.]

## Output

- Final issue comment as set out in the `reporting` section of AGENTS.md, titled "#N [issue title]: Done" (or Blocked, Partial).
- [Anything specific this issue must report.]

## Teardown

- Delete `.scratch/` and any test databases you created; stop every process you started.
- Report free disk before and after (`df -h .` in Git Bash, or `Get-PSDrive C` in PowerShell).
