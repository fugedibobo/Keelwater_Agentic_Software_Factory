# AGENTS.md: how coding agents build this repo

<purpose>
- Public demo repo: the Keelwater Signal Engine and its Signal Board. Keelwater is fictional; all data is synthetic.
- Design canon: docs/architecture.md (section 11 is the CLI); area docs in docs/; day plan docs/build-plan.md.
- When sources disagree: the issue body wins, then the area doc, then architecture.md. Name any conflict you resolve in the PR.
</purpose>

<roles>
- Orchestrator of record: one Claude Code session, model opus, effort high, in the main checkout (the repo root on the author's laptop, outside OneDrive). It dispatches the milestone's work orders, pushes branches, opens PRs, comments, merges, and alone asks the repo owner.
- Workers: codex, newest terra model, effort high, through the codex plugin; one per issue, in worktree .worktrees/issue-<N> on branch issue-<N>-<slug>; at most 3 at once. Workers build and test offline (FakeGateway, replay), commit and report. They never run live steps, push, comment or merge.
- Sonnet subagents (effort high), started by the orchestrator: check each PR and return at most 10 lines; run live steps (probe, smokes, live runs, tuning); do work that needs Claude skills (impeccable, playwright-cli).
- If the codex 5-hour window has under 30% left, a sonnet subagent builds instead; the report says so.
- L2: one Claude Code session, model sonnet, effort high, in .worktrees/L2, for #12 then #11 (Archify and visual fitting). It opens its own PRs and never merges.
- Reviewer: codex, newest sol model, effort medium, once, on the finished milestone in #13.
- One level of delegation: workers and subagents never start further agents.
- Claude Code build sessions compact normally (auto-compaction on); they never stop to hand over because of context size. Push and post a checkpoint comment on the current issue at each finished Done-means box, so a restarted session can resume. The 75%/85% warn-and-hand-over rule applies only to the author's Cowork planning chats.
</roles>

<workflow>
- First act on an issue: a "Started" comment naming the engine. If a live session already posted one, stop.
- One issue, one branch from origin/main, one PR. PR body: what changed, the Done-means checklist with evidence, the test command with pass/fail counts, "Refs #<N>". Never "Closes".
- Merge: only the orchestrator, after a sonnet check PASS (a gated PR also needs the repo owner's written GO). It runs gh pr merge --squash <P> (allowed in .claude/settings.json, so no prompt), then git pull --ff-only and uv run pytest -q on main in the main checkout, and closes the issue with the squash commit SHA. Workers and L2 never merge. Nobody pushes to main directly; .claude/settings.json denies it.
- After #7 merges, every merge check also runs uv run keelwater run in .worktrees/check and needs MATCH.
- Keep to Scope; new ideas go in the report as follow-ups.
- Edit only files your issue owns. Shared contracts (signal_engine/contracts.py, signal_engine/schema.sql, contracts/sources/, docs/contracts/) change additively only, flagged at the top of the PR.
- Issue comments: Started, needs-decision (if any), final report. PR comment: the check verdict, headed "check sonnet <head sha>: PASS" or "REWORK".
</workflow>

<checks>
- No CI: local test evidence in the PR is the merge standard.
- Run uv run pytest -q and post the command with its pass/fail counts.
- New non-trivial logic gets a small test; a review finding gets a failing test first.
- Smokes and proofs write only to .scratch/ (db, cache, reports). Live smokes are tests under tests/live/, run with --live.
- After a review BLOCK: fix, then one scoped re-check of the changed lines. A second BLOCK goes to the repo owner as needs-decision; no further loop.
- After 3 failed fixes of one problem, stop and post needs-decision with one diagnostic question.
</checks>

<gates>
Only the repo owner, Andras Fugedi, may approve these, in writing on the issue or PR, or in a permission prompt:
- spending above an issue's USD cap, or any change to the OpenRouter key limit;
- making the repo public or publishing anything;
- changes to AGENTS.md, .claude/settings.json or anything under .github/;
- secret values (agents name keys, never handle their values);
- installs from a URL, git ref or install script;
- deleting anything outside your own work.
To ask: post one needs-decision comment, then carry on with other work. Never wait idle.
</gates>

<security_floor>
- Keys live only in the main checkout's .env (git-ignored): OPENROUTER_API_KEY. The loader finds it from any worktree; a separate clone has none.
- Never print, log, commit, cache or send key values to any model, codex included. Model caches hold request and response bodies only.
- Never open .env or the publish deny-list ($HOME\keelwater-denylist.txt); .claude/settings.json denies both. Only scripts/scan_public.py reads them.
- All data is synthetic and every domain ends in .example. Never add real company or person names; the generator checks names against the spec files.
- Pipeline requests to OpenRouter set provider.data_collection to "deny" (the synthetic-data generator is the one exception, config/models.yaml) and require_parameters to true.
- Pipeline stages use the open-weight models in config/models.yaml; demo triage uses Clef (cloudflare/clef) through OpenRouter's Decisions API. The aws and self-hosted profiles never call OpenRouter. No paid API calls to Claude or OpenAI hosted models.
- Nothing is published until scripts/scan_public.py reports 0 hits.
</security_floor>

<engineering>
- Python 3.12 with uv, SQLite, FastAPI with Jinja, pytest. No Docker, no CI, no front-end build.
- Windows 10, repo outside OneDrive, git core.longpaths true, LF line endings (.gitattributes). Use pathlib; open files and run subprocesses with encoding="utf-8"; the CLI forces UTF-8 stdout; give humans PowerShell-safe commands.
- uv run keelwater run defaults to replay and must always work with no keys and no network.
- Before any live step run uv run keelwater probe (each stage's real parameters, max_tokens 32). If a primary id is not served, use the stage's fallback in config/models.yaml and record the swap in the PR; anything else is needs-decision.
- Respect the issue's USD cap (--max-usd); the gateway aborts a run that passes it.
- Smallest complete change. Mark known limits "# shortcut: <limit>, <when to upgrade>".
</engineering>

<reporting>
- Final issue comment titled "#<N> <issue title>: Done", "Blocked" or "Partial", containing:
  - a plain-English summary of what was built (3-5 lines);
  - the Done-means checklist with evidence (command output, file paths), test counts, live spend in USD per step;
  - overrides: each place a worker's output was rejected or corrected, one line each with why;
  - a tokens table: engine | exact model id, effort | what it did | tokens (measured, or marked "(estimated)", never blank);
  - codex 5-hour window left; free disk before and after; "background left: 0".
- Last line: "Done #<N>: PR #<P>, tests <passed>/<total>, <one-line result>".
</reporting>

<hygiene>
- Check every process and worker you start about every 10 minutes; stop and re-issue anything stuck 30 minutes. Never declare a wait over 5 minutes.
- Write only inside your worktree. Delete .scratch/ and stop servers before reporting.
</hygiene>
