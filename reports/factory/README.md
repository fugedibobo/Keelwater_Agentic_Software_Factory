# Factory telemetry for this build

`build-telemetry.csv` records who built each work order of this repo, what it cost and how the checks went. It is read from the final report comments on issues #1 to #13 (via `gh`), the check verdict comments on their pull requests, and GitHub timestamps. It is built for the delegation ruleset in `docs/delegation.md` (section 10, "Measured on this build"). All company data in the repo is invented; this file is real build data.

## One row per engine task, not per work order (flagged conflict)

Issue #28 asks for one row per work order. Its own measured section needs totals per engine, first-check pass rate per engine and the codex and agy share, which one row per work order cannot give when several engines worked on one order. The CSV therefore has one row per (work order, engine task), with a `role` column. The check fields and wall time sit on the one `build` row of each work order, so counting `build` rows still counts work orders. This is flagged on #28 for the pull request.

## Columns and their source

- `issue`: the work-order issue number.
- `status`: `done` (final report posted, work order closed), `partial` (a Partial report posted: #7 and #11) or `in-progress` (no final report yet: #10 and #13, which were still open on 04/11/2026). #12 is `done`: it was reopened and closed by the Part 1 revision (#38).
- `role`: `build` (the engine whose work was merged), `attempted` (an engine that stopped with nothing usable), `rework`, `check`, `live-run` (live model calls and tuning), or `orchestrate`.
- `engine`: `opus`, `sonnet`, `haiku`, `codex`, `agy` or `other`, as the report names it. Checkers and live runners are Sonnet; the orchestrator is Opus.
- `model`: the exact model id as the report states it (for example `gpt-6.1-terra`), else the short name the report uses. Effort is the report's own tier.
- `effort`: as reported, else `not reported`.
- `tokens_in`, `tokens_out`: reports give totals only, so both are `not reported` on every row.
- `tokens_total`: the figure from the report's token table. Where a report lists two figures for one engine (for example `117k + 60k` for a check and its re-check) the cell is their sum. `k` is read as 1,000.
- `tokens_basis`: `measured` when the report gives the figure with no estimate marking, `estimated` when the report marks it `(estimated)` or `~`, `not reported` when there is no figure. Nothing is estimated by the person writing the CSV.
- `live_usd`, `live_usd_basis`: live model spend from the report, same basis rule. It sits on the `build` row when the report says "live spend USD 0" and on the `live-run` row when a live runner spent money. Reports that give no live spend leave it `not reported`.
- `first_check_result`: `PASS` or `REWORK`, from the first check verdict comment on the work order's pull request (`check sonnet <sha>: PASS|REWORK`); `none` on `in-progress` build rows. Only on the `build` row. For #12 the first verdict was the planning chat's own check of the Done report (REWORK), not a Sonnet check; the pull request merged before that rework was done.
- `rework_count`: the number of REWORK verdicts on the pull request(s) of the work order. Only on the `build` row. A rework started without a REWORK verdict on a pull request (the fact-sheet lock fix after #6) is a `rework` row, not counted here.
- `wall_minutes`: minutes between the work order's Started comment and its final report comment, from GitHub comment timestamps (UTC). Only on the `build` row. It includes waiting, such as the usage limit on #4 and the author's answers on #2 and #7. It is not engine time. #12 shows 1.0 because the Done report followed the Started comment by about a minute.
- `overrides`: one short phrase on what changed the plan, as the report says it.
- `source_url`: the report comment (or, for `in-progress` rows, the issue or comment) the row was read from.

## Rows that are not in the file

- Follow-up work after a report (for example the extract filter on #7 and the review fixes on #13, started on the author's ruling of 04/11/2026) has no report yet, so it has no rows. It is added when the work order closes.
- #28 itself has no final report; its Part A was a planning-chat docs change.
- The `in-progress` rows carry no token figures. #10 already merged PR #45 after a check PASS, but that is not in the CSV until its final report is posted.

## Refreshing

When #7, #10 or #13 close, read their final reports with `gh api repos/fugedibobo/Keelwater_Agentic_Software_Factory/issues/<n>/comments` (and the pull request comments for the check verdicts), update or add the rows, set `status`, and then run:

```
uv run python scripts/telemetry_summary.py --write-doc
```

The script reads this CSV and rewrites only the block between `<!-- measured:start -->` and `<!-- measured:end -->` in `docs/delegation.md`. The "refreshed on" date is the CSV's modification time, or `--date DD/MM/YYYY`. Without `--write-doc` it prints the block. The test is `tests/test_telemetry_summary.py`.
