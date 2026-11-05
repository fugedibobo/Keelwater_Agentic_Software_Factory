# How I used AI

Author: Andras Fugedi. How this repo was built with AI: what each model did, where I decided, and what the build would cost at API prices. Token figures are measured from the session logs as of 05/11/2026. The presentation's AI slide is drawn from this file.

## How I used AI, in short

**1. What was used, and for which parts.** Claude did most of the work: an Opus session planned, dispatched work orders and merged; Sonnet subagents built 12 of the 13 work orders, checked every pull request and ran the live steps; Haiku read and searched. Codex, the planned builder, built only #2's offline generator, and agy (Gemini) was blocked on #7. I kept the key, the spend limit, approvals, publishing and the judgement calls. My own time was about 2 hours by 04/11/2026 02:30 (my estimate), within the 4-hour ask.

**2. Where I trusted it and where I overrode it.** I trusted mechanical work (scaffolding, schemas, test plumbing) once the tests ran and a Sonnet check passed. In planning I overrode four AI recommendations: open-weight models rather than a paid frontier API, a public repo, a one-day build, and keeping the Jev decision model the AI had dismissed. I dropped market-size figures that differed 64 times between research firms.

**3. What AI got wrong, and how it was caught.** The design put a closed-weight, US-hosted model (Jev) into production triage; research found it cannot run inside a private network ([#4](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/4), [PR #25](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/25)). A worker's two-pager report said 5 links when the PDF had 4; an independent check caught it after the first Sonnet check had passed the same commit, and the issue was reopened ([#12](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/12), [PR #22](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/22)). A separate cheap agent now checks every Done report against the repo.

## Tokens and cost, by model

One row per model. Totals include cache reads, which make up most of an agent session.

<!-- tokens:start -->

| Model | What it did | Total tokens | Blended rate (USD per million tokens) | API cost equivalent (USD) |
|---|---|---|---|---|
| Opus | Orchestrated, dispatched work orders, merged | 117,094,862 (measured) | 0.39 | 45.98 |
| Sonnet | Built work orders, checked every pull request, ran live steps | 465,529,724 (measured) | 0.21 | 98.51 |
| Haiku | Read, searched, summarised logs | 6,985,263 (measured) | 0.15 | 1.03 |
| Codex Terra | Offline builds, mostly stalled or hit its limit | 35,642,913 (measured) | 0.08 | 2.79 |
| Codex Sol | Adversarial review of the finished build | 1,461,945 (measured) | 0.41 | 0.60 |
| Gemini Argon (agy) | One blocked turn, wrote nothing | 53,000 (measured) | 2.00 | 0.11 |
| OpenRouter pipeline | Ran the product's pipeline stages on open-weight models | 1,510,716 (measured, lower bound) | 0.29 | 0.44 |
| **Total** | | **628,278,423** | **0.24** | **149.48** |

- Blended rate = the cost of every token type at its list price, divided by total tokens. Cache reads cost a tenth or less of normal input, and agent sessions are mostly cache reads, so the blended rate is far below the headline price.
- Claude: summed from the usage fields of the laptop's Claude Code session logs from 03/11/2026, subagents included, each API message counted once. Only token counts and model names are kept.
- Codex: the growth of the running token count in each Codex session run in this repo or its worktrees from 03/11/2026, credited to the model of the turn it happened in. Terra and Sol are priced at the 272K-or-less rates.
- Gemini Argon (agy): the one total its report gave, all counted as input because no split exists. Its published rate is the one in force until 30/11/2026 and doubles on 01/12/2026.
- OpenRouter pipeline: summed from the recorded model responses in the repo's replay cache, one entry per distinct request. Repeated and failed calls are not in it, so it is a lower bound; the rate is the cost each response reported.
- Haiku is priced at the over-100K-prompt rates, which some of its calls reached. Prices were read from the providers' pages on 05/11/2026; sources are in reports/factory/README.md.

At API prices this build would cost a company about USD 149. What it cost me: the Claude and Codex subscriptions I already pay for, which charge no per-token fee, plus OpenRouter spend to date of USD 6.67 of the USD 10 limit on 05/11/2026, the key's own usage figure. The work-order reports gave a subtotal of USD 0.51 measured and USD 1.44 estimated.

<!-- tokens:end -->

## Decisions

| Decided by | What | Why | Evidence |
|---|---|---|---|
| Me, overriding 4 AI recommendations (02/11 to 03/11) | Open-weight models instead of a paid frontier API; a public repo; a one-day demo build; keep Jev, which the AI had dismissed as a transcription error | Cheaper, and it matches the private-network direction. I knew Jev was real; research confirmed it launched in September 2026, after the model's training data | [PR #19](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/19), [build-plan handover](build-plan.md) |
| AI design, caught by research | Jev in production triage; reversed to demo-only | Closed weights and US hosting mean it cannot run inside a private AWS network | [PR #19](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/19), [ADR-003](decisions.md) |
| Me, 04/11 | Clef through OpenRouter for demo triage, with Jev and its key dropped | Self-hostable open weights, so demo and production share a model, and one API key | [#4 body](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/4), [PR #25](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/25) |
| Evidence, over me | Synthetic data instead of the public datasets I proposed | Research found none that were B2B and freely redistributable; the planted themes give the evals an answer key | [PR #19](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/19) |
| AI reviewing AI | Faults found in the architecture the orchestrator wrote: one model family generating and judging the data, recency maths that would break replay, a triage threshold gap, corroboration counting tools instead of feedback routes | Subagents writing the evals and data specs hit them; all fixed before the build | [PR #19](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/19) |
| Me, overriding the AI's status recommendation | Phoenix made mandatory, with traces, labelled datasets and eval experiments | Telemetry is what lets the pipeline improve itself | [#10 body](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/10) |
| Me | Cheaper engines (agy, Terra, Sonnet, Haiku) build non-crown-jewel work and Opus orchestrates only, under a delegation ruleset built on published benchmarks | Conserve paid usage; public evidence was enough for a proposal | [#28](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/28), [PR #29](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/29), [delegation.md](delegation.md) |
| Me, after a gap review | A halving model, which found halving idea-to-customer time not plausible in 18 months; Part 1 now says so | Close the gaps before submission, and say what the numbers support. Its inputs are assumptions | [#37](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/37), [PR #43](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/43), [PR #44](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/44) |
| Me | Capped #7's pipeline fix to one re-run per seed and shipped the honest results. For #13 I chose which review findings to fix and which to document, with one scoped re-check and no third review | Stop an open-ended fix loop. The codex Sol review, a different model family from the Sonnet builders, blocked twice; what remained is stated in the README | [#7 ruling](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/7#issuecomment-6629466310), [#13 ruling](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/13#issuecomment-6629466728) |
| My check framework | #12 reopened after the planning chat's REWORK, which the first Sonnet check had not matched | The planning chat found 4 links, not 5, and a dead footnote link; the Sonnet check passed the same commit | [REWORK](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/22#issuecomment-6619494692), [Sonnet PASS](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/22#issuecomment-6619557865), [reopen](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/12#issuecomment-6620281249) |

## Blind spots

1. The build slipped a full day: it started on 04/11, not 03/11 ([#1](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/1#issuecomment-6619362439), [PR #20](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/20)). Live steps were deferred while the API key was missing ([#14](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/14#issuecomment-6620282175)).
2. The docs carried the wrong checkout path; the fix needed a rule-file approval ([PR #31](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/31)). The brief's PDF was saved inside the repo and had to be excluded from git locally ([PR #41](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/41)).
3. The plan assumed Codex would build. It built 1 of 13 work orders, #2's offline generator ([PR #33](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/33)). In #1, #5 and #6 it stopped or built nothing, in #10 two attempts built nothing ([#10 report](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/10#issuecomment-6629808276)), and in #4 its rework hit the usage limit. Sonnet built the other 12.
4. A merge on [PR #22](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/22) went through while a REWORK stood. The planning chat's REWORK arrived shortly after the Done report, the first Sonnet check then passed the same commit, and the merge relied on that PASS. Two independent checks disagreed and nothing forced a re-check ([#12 reopen](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/12#issuecomment-6620281249)).
5. On 04/11 a check, and the orchestrator, ran the delegation cost script with the system Python 3.9 instead of the repo's 3.12. It printed 368.29 where 3.12 prints 368.30, so the check's REWORK was a false positive and the doc was changed to the wrong figure. [PR #54](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/pull/54) restored 368.30, made the script give the same result on any Python version and added a test.
6. On 04/11 an orchestrator session's teardown loop broke on the spaces in the repo path and deleted every folder under `.worktrees/`, including six worktrees of another session. Every branch still existed and five were fully pushed, so only uncommitted edits in one worktree could have been lost ([#13 comment](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/issues/13#issuecomment-6634265403)).

## Human gates

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
