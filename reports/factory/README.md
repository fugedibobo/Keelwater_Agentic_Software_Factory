# Factory telemetry for this build

`build-telemetry.csv` records who built each work order of this repo, what it cost and how the checks went. It is read from the final report comments on issues #1 to #13 (via `gh`), the check verdict comments on their pull requests, and GitHub timestamps. It is built for the delegation ruleset in `docs/delegation.md` (section 10, "Measured on this build"). All company data in the repo is invented; this file is real build data.

## One row per engine task, not per work order (flagged conflict)

Issue #28 asks for one row per work order. Its own measured section needs totals per engine, first-check pass rate per engine and the codex and agy share, which one row per work order cannot give when several engines worked on one order. The CSV therefore has one row per (work order, engine task), with a `role` column. The check fields and wall time sit on the one `build` row of each work order, so counting `build` rows still counts work orders. This is flagged on #28 for the pull request.

## Columns and their source

- `issue`: the work-order issue number.
- `status`: `done` (final report posted, work order closed), `partial` (a Partial report posted: #10 and #11) or `in-progress` (no final report yet; none at the last refresh). #7 and #13 are `done`: #7 is a Done report whose quality floors fail (the honest result per the author's ruling). #12 is `done`: it was reopened and closed by the Part 1 revision (#38).
- `role`: `build` (the engine whose work was merged), `attempted` (an engine that stopped with nothing usable), `rework`, `check`, `review` (an adversarial review by a different model family: on #13 codex gpt-6.1-sol reviews what Claude Sonnet built, the Part A rule "review by a different family" in `docs/delegation.md`), `live-run` (live model calls and tuning), or `orchestrate`.
- `engine`: `opus`, `sonnet`, `haiku`, `codex`, `agy` or `other`, as the report names it. Checkers and live runners are Sonnet; the orchestrator is Opus.
- `model`: the exact model id as the report states it (for example `gpt-6.1-terra`), else the short name the report uses. Effort is the report's own tier.
- `effort`: as reported, else `not reported`.
- `tokens_in`, `tokens_out`: reports give totals only, so both are `not reported` on every row.
- `tokens_total`: the figure from the report's token table. Where a report lists two figures for one engine (for example `117k + 60k` for a check and its re-check) the cell is their sum. `k` is read as 1,000.
- `tokens_basis`: `measured` when the report gives the figure with no estimate marking, `estimated` when the report marks it `(estimated)`, or writes `~` or `about` before it, `not reported` when there is no figure. Nothing is estimated by the person writing the CSV.
- `live_usd`, `live_usd_basis`: live model spend from the report, same basis rule (so "about USD 0.27" on #2 is `estimated`). It sits on the `build` row when the report says "live spend USD 0" and on the `live-run` row when a live runner spent money. Reports that give no live spend leave it `not reported`. Several figures of the same basis in one report are added into one cell (#13 fresh proof 0.1708 + 0.198 is 0.3688 measured); figures of different bases go on separate rows, so an estimate is never added to a measured figure. Spend the report says is "not metered" (#13 handoff previews, under USD 0.30) is not put in a cell. The review-fix re-records (about USD 0.10) appear in both the #7 and #13 reports; they are recorded once, under #13.
- `first_check_result`: `PASS` or `REWORK`, from the first check verdict comment on the work order's main pull request (the first one named in its report) (`check sonnet <sha>: PASS|REWORK`); `none` on `in-progress` build rows. Only on the `build` row. For #12 the first verdict was the planning chat's own check of the Done report (REWORK), not a Sonnet check; the pull request merged before that rework was done. For #13 the main pull request is #58, whose first check was REWORK; the review-fix pull requests #51 and #52 passed first time and are not used for the first check, but their verdicts count in `rework_count` (which is 1).
- `rework_count`: the number of REWORK verdicts on the pull request(s) of the work order. Only on the `build` row. A rework started without a REWORK verdict on a pull request (the fact-sheet lock fix after #6) is a `rework` row, not counted here.
- `wall_minutes`: minutes between the work order's Started comment and its final report comment, from GitHub comment timestamps (UTC). Rounded half up to one decimal place (12.95 minutes is 13.0). Only on the `build` row. The Started comment is the work order's first "Started" comment (for #13, after two handover comments). It includes waiting, such as the usage limit on #4 and the author's answers on #2, #7, #10 and #13. It is not engine time. #12 shows 1.0 because the Done report followed the Started comment by about a minute.
- `overrides`: one short phrase on what changed the plan, as the report says it.
- `source_url`: the report comment (or, for an `in-progress` row, the issue) the row was read from.

## Rows that are not in the file

- Follow-up work after a report has no rows until the work order posts a new report.
- #28 itself has no row; its Part A was a planning-chat docs change.
- #13 has one `review` row for the Sol adversarial review and its two scoped re-checks (all BLOCK), as its report tables them; tokens are `not reported`. #13 also has `about` figures (Sonnet builders about 1.2M and checkers about 700k across 9 runs each), recorded as `estimated`.

## Refreshing

When #10 (still Partial) or any other work order gets a new final report, read their final reports with `gh api repos/fugedibobo/Keelwater_Agentic_Software_Factory/issues/<n>/comments` (and the pull request comments for the check verdicts), update or add the rows, set `status`, and then run:

```
uv run python scripts/telemetry_summary.py --write-doc
```

The script reads this CSV and rewrites only the block between `<!-- measured:start -->` and `<!-- measured:end -->` in `docs/delegation.md`. The "refreshed on" date is the CSV's modification time, or `--date DD/MM/YYYY`. Without `--write-doc` it prints the block. The test is `tests/test_telemetry_summary.py`.
