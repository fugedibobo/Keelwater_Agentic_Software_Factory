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

## Tokens by model (#64)

`tokens-by-model.csv` is the per-model token record: `model, input, cache_write, cache_read, output, total, source` (`measured` or `estimated`), plus `cache_write_1h`, the part of `cache_write` written to the one-hour cache (it is priced higher than the five-minute write). `total` is the sum of the four token types. `openrouter-usage.csv` is the per-model breakdown behind the OpenRouter row. `model-prices.csv` holds the list prices used, in USD per million tokens, with the page each was read from.

```
python scripts/measure_tokens.py measure              reads the local session logs, rewrites the two token CSVs
python scripts/measure_tokens.py render --write-doc   rewrites the generated blocks in docs/ai-usage.md, docs/delegation.md and README.md
```

`measure` needs the laptop's Claude Code and Codex session logs; `render` and the tests need only the CSVs. The script reads token counts, model names and timestamps only. It never copies prompt or response text, and no file it writes holds a home-folder path.

Sources for `model-prices.csv`, all read on 05/11/2026:

- Claude Opus 5.5, Sonnet 5.5 and Haiku 5.5: https://platform.claude.com/docs/en/about-claude/pricing. Cache reads on Opus and Sonnet 5.5 are 0.05x the input price. Haiku has two tiers by prompt size; the table uses the over-100K tier, so its cost is not understated.
- Codex GPT-6.1 Terra and Sol: https://developers.openai.com/api/docs/pricing, standard tier, prompts of 272K tokens or less. The other OpenAI pricing page (openai.com/api/pricing) returned HTTP 403 and was not retried.
- Gemini Argon (agy): https://aistudio.google.com/docs/pricing lists Gemini 4 Argon at USD 2 input, 0.10 cached input and 10 output until 30/11/2026, then double. The page does not say that agy uses this model, so the match is by name and the row is a published price applied to a small figure.
- OpenRouter pipeline: no list price needed; each recorded response carries the cost OpenRouter billed (`cost_usd`), and the row sums those.
