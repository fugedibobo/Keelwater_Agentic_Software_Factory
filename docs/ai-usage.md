# How I used AI

Author: Andras Fugedi. Living log, started 02/11/2026; state as of 04/11/2026 about 12:30 UTC. This is how this repo was built. The presentation's AI slide is drawn from this file. FOUND means read at a source (an issue, a pull request, a file); INFERRED means reasoned. Times are UTC, which is London time in November.

## How I used AI, in short

**1. What was used, and for which parts.** Claude did most of the work. An Opus session planned, dispatched work orders and merged. Sonnet subagents built 11 of the 12 done or partial work orders (92%), checked every pull request and ran the live steps. Haiku read and searched. Codex (GPT-6.1 Terra) was the planned builder but built only #2's offline generator (PR #33; first check passed; tokens not reported). It stalled or hit its usage limit on #1, #4, #5 and #6, and two attempts on #10 built nothing. agy (Gemini) was blocked on #7. Codex and agy together built 1 of 12 (8%). AI covered the research, design, code, checks and first drafts. I kept the key, the spend limit, approvals, publishing and the judgement calls. My own time was about 2 hours by 04/11/2026 02:30 (my estimate), within the 4-hour ask.

**2. Where I trusted it and where I overrode it.** I trusted mechanical work (scaffolding, schemas, test plumbing) once the tests ran and a separate Sonnet check passed. I overrode four AI recommendations in the planning session: open-weight models rather than a paid frontier API, a public repo, a one-day demo build, and keeping the Jev decision model the AI had dismissed. On 04/11 I replaced Jev with open-weight Clef, and I made Phoenix mandatory after the startup status recommended cutting it. I dropped market-size figures that differed 64 times between research firms. Evidence overrode me once: public datasets did not fit.

**3. What AI got wrong, and how it was caught.** The AI's design put a closed-weight, US-hosted decision model (Jev) into production triage. Research found it cannot run inside a private network, a hard requirement, and I later replaced it with Clef everywhere ([#4](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/4), [PR #25](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/25)). Second, on 04/11 a worker's two-pager report said 5 links when the PDF had 4, and a footnote link went nowhere ([#12](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/12), [PR #22](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/22)). An independent check flagged it seven minutes after the report. The first Sonnet check then passed the same commit, the merge went ahead, and the issue was reopened. The check that caught it exists because of the framework I built for my own agent projects: a separate cheap agent checks every Done report against the repo.

## The trail

### Who did which part (detail for point 1)

| Part | What did it | My role |
|---|---|---|
| Clarifying the goal | An orchestrating Claude session ran a structured "grill me" question session: ten numbered questions, each with a recommended answer | Answered; overrode four recommendations (point 2) |
| Research | Six parallel subagents (web search, public docs, public GitHub repos), each returning findings labelled FOUND or INFERRED, saved to [docs/research/](research/) | Set the questions, read the summaries |
| Design | The orchestrator wrote [docs/architecture.md](architecture.md); subagents drafted the evals, data, board, decisions and diagram specs from it | Set direction and constraints; ruled on trade-offs |
| Review | Independent subagents attacked the design from three angles (product leadership, engineering leadership, one-day feasibility); two fix rounds followed | Accepted or rejected findings |
| Build (from 04/11/2026 00:44) | Claude Code orchestrating work orders: Sonnet builders, Sonnet checks, codex when it had capacity | Kept the key, the spend limit, approvals and judgement calls |
| Writing | Drafted by AI, edited for plain English | Final read of everything that is published |

### Where I trusted the output and where I did not (detail for point 2)

Trusted as it came:
- Record shapes for the source tools (Gong, Intercom, Fireflies, FullStory, HubSpot): the research cites each vendor's API reference, and the synthetic data copies those field names. Good enough for a demo; a real connector would be built against the live API.
- Mechanical work: scaffolding, schemas, synthetic data assembly, test plumbing, provided the tests ran and a check passed.

Checked or overridden:
- Any number that will be quoted to leadership. Market-size estimates for claims software ranged from USD 0.5bn to USD 35bn between research firms (a 64x spread), so I dropped market size entirely.
- Productivity claims. The research surfaced vendor telemetry next to randomised trials; the two-pager leans on the trials and labels the rest.
- Model ids and prices, which change weekly. The build probes each id before use.

### Decisions

| Decided by | What | Why | Evidence |
|---|---|---|---|
| Me, overriding 4 AI recommendations (02/11 to 03/11) | Open-weight models instead of a paid frontier API; a public repo; a one-day demo build; keep Jev | Cheaper, and it matches the private-network direction; a one-day build is what fits the time | [PR #19](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/19), [build-plan handover](build-plan.md) |
| Me, against the AI | Kept Jev when the AI dismissed it as a transcription error | I knew it was real; research confirmed it launched in September 2026, after the model's training data | [PR #19](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/19) |
| AI design, caught by research | Jev in production triage; reversed to demo-only | Closed weights and US hosting mean it cannot run inside a private AWS network | [PR #19](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/19), [ADR-003](decisions.md) |
| Me, 04/11 | Clef through OpenRouter for demo triage, with Jev and its key dropped | Self-hostable open weights, so demo and production share a model, and one API key | [#4 body](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/4), [PR #25](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/25), [#14 comment](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/14#issuecomment-6619892001) |
| Evidence, over me | Synthetic data instead of the public datasets I proposed | Research found none that were B2B and freely redistributable; the planted themes give the evals an answer key | [PR #19](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/19) |
| AI reviewing AI | Faults found in the architecture the orchestrator wrote: one model family generating and judging the data, recency maths that would break replay, a triage threshold gap, corroboration counting tools instead of feedback routes | Subagents writing the evals and data specs hit them; all fixed before the build | [PR #19](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/19) |
| Me, overriding the AI's status recommendation | Phoenix made mandatory, with traces, labelled datasets and eval experiments | Telemetry is what lets the pipeline improve itself | [#10 body](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/10) |
| Me | Cheaper engines (agy, Terra, Sonnet, Haiku) build non-crown-jewel work; Opus orchestrates only | Conserve paid usage | [#28](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/28), [delegation.md](delegation.md) |
| Me | A delegation ruleset built on published benchmarks, with no benchmark run; Claude and Codex assumed, open-weight challengers tracked | Evidence from public sources was enough for a proposal | [#28](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/28), [PR #29](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/29) |
| Me, with AI-added guards | Clef as the factory's router and telemetry triager (my idea); code decides crown-jewel work, route up when unsure, shadow until certified (AI) | A decision model sorts cheaply; guards stop a wrong downgrade | [PR #29](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/29), [delegation.md section 7](delegation.md) |
| Me | Gap review against the six Part 1 questions, then a second question session: halving model, Part 1 revision, metric dictionary v0 owned by product ops, skills meaning agent skills, designers fed by evidence, the factory as a delegation meta-harness | Close the gaps before submission. The halving model (#37) then found halving idea-to-customer time not plausible in 18 months, and Part 1 now says so (#38); its inputs are all INFERRED | [#37](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/37), [PR #43](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/43), [#38](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/38), [PR #44](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/44) |
| An agent proposed, I accepted | Diagram B cut | Its 17 exact edge labels do not fit 5 stages under 1240 px; the Mermaid chart stays as fallback | [#11 report](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/11#issuecomment-6619523035), [PR #23 check](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/23#issuecomment-6619558236) |
| Me | Synthetic data generation uses a free OpenRouter model, falls back to DeepSeek V4.1 Flash or Qwen, and never uses Mistral or the judges' family | Keep the generator and the judges apart | [#2 comment](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/2#issuecomment-6621137014) |
| AI caught, I confirmed | A pasted line was a handover block meant for a build session, not an instruction to the planning chat; a retyped copy of a research note had drifted from the original, which comparing file hashes showed | Check before acting on pasted text; compare hashes before trusting a copy | [PR #41](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/41) (lessons), [build-plan handover](build-plan.md) |
| My check framework | #12 reopened after the planning chat's REWORK, which the first Sonnet check had not matched | The planning chat found 4 links, not 5, and a dead footnote link; the Sonnet check passed the same commit four minutes later | [REWORK](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/22#issuecomment-6619494692), [Sonnet PASS](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/22#issuecomment-6619557865), [reopen](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/12#issuecomment-6620281249) |

### Timeline

Dates are DD/MM/YYYY, times UTC.

1. 02/11 to 03/11: planning chat. Ten-question session, six research reports, three adversarial reviews, two fix rounds. [PR #19](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/19) merged 03/11 10:20.
2. 03/11 10:16 to 10:23: work orders [#1](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/1) to #18 created (#14 to #18 are my own steps); [PR #21](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/21) adds the build-plan handover.
3. 04/11 00:43 to 00:45: I approve the rule and permission files ([PR #20](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/20), [#18](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/18)). The build starts at 00:44 on [#1](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/1#issuecomment-6619362439), a day later than planned, and pre-flight finds no `.env`, so no live step can run ([#14](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/14#issuecomment-6619370521)).
4. 00:46 to 01:17: the two-pager ([PR #22](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/22)) and diagrams A and C ([PR #23](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/23)) merge; the check sends #23 back once. #22 merges at 01:14 after a Sonnet check passed the same commit four minutes after the planning chat's REWORK.
5. 01:19: Jev dropped, Clef via OpenRouter ([#14](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/14#issuecomment-6619892001)); the scaffold ([PR #24](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/24)) merges after one REWORK.
6. 01:20 to 02:22: codex stalls, Sonnet builds #3, #4, #5, #6, #8 and #9; every pull request gets a Sonnet check ([PR #34](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/34) needed one REWORK). All seven reported builds are offline.
7. 01:45: #12 reopened; the key is relayed as set, so deferred live steps are released ([#12](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/12#issuecomment-6620281249), [#14](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/14#issuecomment-6620282175)).
8. 02:22: first build session writes its handover on [#13](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/13#issuecomment-6620814544); by 02:30 I estimate 2 hours of my own time.
9. 02:43 to 02:45: the gap review creates [#37](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/37), [#38](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/38), [#39](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/39) and [#40](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/40); I rule on the data generator ([#2](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/2#issuecomment-6621137014)).
10. 02:57 to 03:00: after Sonnet checks, five planning pull requests merge in order: [#25](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/25), [#29](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/29), [#31](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/31), [#41](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/41), [#42](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/42). agy is blocked on [#7](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/7#issuecomment-6621294130) and Sonnet builds the offline part.
11. 03:32 to 03:45: the halving model ([PR #43](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/43), [#37 report](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/37#issuecomment-6621848260)) finds halving idea-to-customer time not plausible within 18 months: 79% of baseline at month 18 on mid inputs, 51% on high, 95% with AI alone. Part 1 ([PR #44](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/44), [#38 report](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/38#issuecomment-6622016484)) now says so, in place of the earlier 12-month question line.
12. 04:33 to 12:09: [PR #45](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/45) (Phoenix), [PR #46](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/46) (synthetic data), [PR #47](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/47) (this file's first version, 07:02), [PR #48](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/48) (#7 evals and first live run, 07:56), [PR #49](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/49) (#10 evidence, 11:48) and [PR #50](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/50) (#28 Part B telemetry, 12:09) merge; [#2](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/2) closes. Open at about 12:30: #7 (partial), #10 (partial; issue stays open for live Phoenix wiring), #13 (review-fix PRs #51 and #52 open), #28 (until its telemetry refreshes), #39 (this telemetry follow-up); #40 not started. Submission is planned for the morning of 05/11/2026 ([build-plan handover](build-plan.md)).

### Blind spots

1. The build slipped a full day: it started 04/11 at 00:44, not 03/11 ([#1](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/1#issuecomment-6619362439), [PR #20](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/20)).
2. The docs carried the wrong checkout path; the fix needed a rule-file approval ([PR #31](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/31), [#14](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/14#issuecomment-6619892001)).
3. The brief's PDF was saved inside the repo and had to be excluded from git locally ([PR #41](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/41), handover lessons).
4. Live steps on closed issues were deferred while the API key was missing ([#14](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/14#issuecomment-6620282175)).
5. The plan assumed codex would build. It built 1 of 12 done or partial work orders, #2's offline generator ([PR #33](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/33); [#2 report](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/2#issuecomment-6623164926)). In #1, #5 and #6 it stopped or built nothing, in #10 two attempts built nothing ([#10 report](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/10#issuecomment-6629808276)), and in #4 its rework hit the usage limit. Sonnet built the other 11 ([#1](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/1#issuecomment-6619922654), [#4](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/4#issuecomment-6620686088), [#5](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/5#issuecomment-6620321224), [#6](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/6#issuecomment-6620106234)).
6. A merge on [PR #22](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/22) went through on its first commit while a REWORK stood. The planning chat's REWORK came seven minutes after the Done report; the first Sonnet check passed the same commit four minutes later, and the merge relied on that PASS. Two independent checks disagreed and nothing forced a re-check (see [#12 reopen](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/12#issuecomment-6620281249)).

### Human gates

In this build:

| Gate | Who passes it | Evidence | Status |
|---|---|---|---|
| Rule and permission files (AGENTS.md, `.claude/settings.json`, `.github/`) | Me | [#18](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/18), [PR #20](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/20), [PR #31](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/31), [PR #42](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/42) | Passed |
| Key, credit and spend (OpenRouter key limit USD 10; spend above an issue's cap) | Me | [#14](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/14) | Key set (relayed); credit balance not reported |
| Publishing: making the repo public, after a clean scan | Me | [#17](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/17) | Open |
| My picks: the real override examples, PM review of 20 items (optional) | Me | [#16](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/16), [#15](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/15) | Open |
| Each merge | The orchestrator, after a Sonnet check PASS; a gated pull request also needs my written GO | [AGENTS.md](../AGENTS.md), [build-plan section 8](build-plan.md) | In force |

In the proposed factory ([architecture](architecture.md), [diagrams](diagrams.md), [delegation](delegation.md)): five gates, each passed by a named person and never by an agent, plus routing promotions.

| Gate | Who passes it |
|---|---|
| 1. Accept an opportunity | The PM |
| 2. Approve the intent document | The Trio (PM, Designer, Tech Lead) |
| 3. Review each pull request; no agent merges its own work | An engineer |
| 4. Announce and approve the release bundle | The release owners (platform team with product ops; the docs do not name the approver) |
| 5. Accept the drafts (release notes, help articles, change notices) | The PM or product marketing |
| Routing promotions: a cheaper engine for a class after 50 tasks with a Wilson 95% lower bound within 5 points of the incumbent; Clef routing without an engineer after 50 labelled outcomes per class and a lower bound of at least 0.75 | A weekly review by the platform team; a third failed check goes to a named engineer |

### Agent time, tokens and spend per engine

Source: [reports/factory/build-telemetry.csv](../reports/factory/build-telemetry.csv) (47 rows across 13 work orders; columns in its [README](../reports/factory/README.md)), as summarised in the generated block of [delegation.md section 10](delegation.md) by `scripts/telemetry_summary.py` ([#28](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/28) Part B). As of 04/11/2026 about 12:30 UTC; refreshes when #7 and #13 close. The CSV is canonical. An earlier version of this table read the first nine final reports. The CSV now also holds #2, #7 and #10, and it merges #4's checker figures (77k measured plus about 40k estimated) into one 117k estimated row under its basis rule. Tokens are totals as the reports gave them, not split into input and output. "Estimated" means the report marked the figure `(estimated)`, `~` or `about`; "not reported" means no figure. The last two engine rows come from the per-subagent totals the harness reported for the L3 session, not from the CSV.

No engine reported its own time. The Agent time column is the sum of `wall_minutes` over that engine's build rows: wall minutes from Started to final report comment, includes waiting, not engine time. Spend is live model USD from the reports.

| Engine | What it did | Tokens measured | Tokens estimated | Rows not reported | Agent time (wall minutes) | Live USD |
|---|---|---|---|---|---|---|
| Opus (orchestrator) | Dispatch, merge | 0 | 107,000 (rows for #1, #2, #3, #5, #6, #7, #8, #9, #10) | 0; no Opus row for #4, #11, #12, #13 | no build rows | not reported |
| Sonnet builder | Built #1, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12; #13 in progress | 1,767,000 | 0 | 3 (#11, #12, #13) | 1,006.1 over 11 build rows | USD 0 on 7 rows (#1, #3, #5, #6, #8, #9, #10); not reported on 5 (#4, #7, #11, #12, #13) |
| Sonnet L2 | Two-pager (#12) and diagrams (#11); counted in the builder row | not reported | not reported | #11 and #12 build and check rows | counted in the builder row (#11 8.9, #12 1.0) | not reported |
| Sonnet checker | Checked each pull request | 876,000 | 187,000 (#4 117,000, #9 70,000) | 2 (#11, #12) | no build rows | not reported |
| Sonnet live runs and rework | Live model runs (#2 518,000, #7 215,000, #10 94,000) and the #4 rework (85,000) | 912,000 | 0 | 0 | no build rows | USD 1.27 estimated (#2 0.27, #7 1.0); #10 live run not reported |
| Codex GPT-6.1 Terra and Sol | Built #2's offline generator (PR #33); attempted #1, #5, #6, #10; reworks on #4, #6; two Sol reviews of #13 | 0 | 0 | 9 (all 9 rows) | 268.1 on #2's build row, includes the author's answers | not reported |
| agy (Gemini) | One turn on #7; blocked headless, wrote nothing | 53,000 | 0 | 0 | no build rows | not reported |
| Sonnet subagents of the L3 session | Research note, halving-model builder, Part 1 writer, #39 writer and refresh, Part B builder, checks and re-checks of #37, #38, #47, #50 and the five planning PRs | 1,778,758 over 17 runs: the 11 earlier runs 1,135,803 plus six since 642,955 (#39 refresh 104,570; #47 check 105,194 and re-check 70,782; Part B builder 143,223; #50 check 115,045 and re-check 104,141) | 0 | 0 | not measured | not reported |
| Haiku subagents of the L3 session | Halving doc, Part 1 PDF render, evidence gathering for this file | 361,802 over 3 runs: halving doc 105,580; Part 1 PDF render 91,506; #39 evidence gathering 164,716 | 0 | 0 | not measured | not reported |
| Total (CSV rows) | | 3,608,000 | 294,000 | 14 | 1,274.2 over 12 build rows | USD 1.27 estimated |

The Total row adds measured to measured and estimated to estimated, never one to the other, and counts rows with no figure instead of adding them. The L3 subagents alone total 2,140,560 measured over 20 runs (Sonnet 1,778,758, Haiku 361,802). The harness does not report the L3 orchestrator's own tokens, and these figures are kept out of the CSV total.

Live model spend: USD 0 measured on the build rows of #1, #3, #5, #6, #8, #9, #10; USD 1.27 estimated on the live runs (#2 USD 0.27, #7 USD 1.0); not reported for #4, #11, #12 and #13. The OpenRouter key limit is USD 10 for the whole build ([architecture](architecture.md)).

My own time: about 2 hours by 04/11/2026 02:30 (my estimate), within the 4-hour ask. The plan was about 22 hours of agent time ([build-plan section 11](build-plan.md): 20.25 h on L1 plus 1.75 h on L2), much of it while I slept. The build rows' wall minutes sum to 1,274.2 (about 21.2 hours). That is more than the 11.8 hours from 00:44 to about 12:30 on 04/11, because work orders ran in parallel, so it is waiting plus working time and not a like-for-like measure against the plan.
