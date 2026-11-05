# Delegation ruleset for the engineering factory

Author: product operations. Date: 04/11/2026. Status: proposal to the platform team, who own the factory ([ADR-011](decisions.md)). Scope: Claude and Codex models only, for the factory's coding agents and for the product lifecycle layer's agents. Evidence: [model-routing-evidence.md](research/model-routing-evidence.md), gathered 04/11/2026. FOUND means read at a source; INFERRED means reasoning stated in the text.

## 1. Why

Building everything on the top model at API prices is the fastest way to lose budget. Most tasks in a factory are small and checkable, and a cheap model passes them. The top model earns its price only where a wrong answer is costly to find or to undo.

Routing therefore follows the cost of being wrong. This is the same principle as the Signal Engine's model routing ([ADR-002](decisions.md)): cheap tiers for work that code or a reviewer can check, strong tiers for work that cannot be undone easily.

## 2. Task classes and default engines

| Class | Examples | Builder | Effort | Reviewer (other family) | Token cap per task (INFERRED) |
|---|---|---|---|---|---|
| T0 mechanical | Formatting, renames, lint fixes, dependency bumps, docs, tests from a written spec | Haiku 5.5 | low | Codex GPT-6 Luna | 0.5M |
| T1 routine | One change inside one module, with tests | Codex GPT-6.1 Terra (fallback Sonnet 5.5) | medium | Sonnet 5.5 | 1.5M |
| T2 cross-module | Several modules, unclear spec, migrations, performance | Sonnet 5.5 or GPT-6.1 Sol | medium | The other family: Sol reviews Sonnet, Sonnet reviews Sol | 3M |
| T3 crown jewel | Claims payments and reserves, authentication, the audit chain, architecture, incident root cause | A T1 or T2 engine builds; Opus 5.5 plans and reviews | high for the reviewer | Opus 5.5 adversarial review; Sol at high effort if a Claude engine built it | 5M |
| Search | Read-only search and exploration | Haiku 5.5 | low | none (read-only) | 0.5M |
| Orchestration | Split, route and check work | Opus 5.5, never writes production code | medium | none | not capped per task |

- The token caps are starting values, INFERRED from the only token figures found: 2.8M tokens per task at medium effort and 4.8M at xhigh for one older Codex model (FOUND, see the note, Q2). Change them from telemetry.
- Effort tiers are low, medium, high, xhigh and max on both vendors. Effort has no separate price; it costs only through output tokens (FOUND).

## 3. Rules

```text
<routing>
Classify every task as T0, T1, T2 or T3 before any build starts, and write the class in the task record.
Build a task with the engine listed for its class in the routing table, never with a higher one by default.
A T3 task is planned by Opus 5.5 and built by a T1 or T2 engine; the planner does not write production code.
The orchestrator splits, routes and checks; it does not write production code.
Read-only search and exploration use Haiku 5.5.
Effort starts at the lowest tier that passed for that class; maximum effort is never the default.
Subagents receive file paths and acceptance tests, not pasted file contents.
</routing>
<review>
The reviewer of a task is from a different model family than its builder: Codex builds and Claude reviews, or Claude builds and Codex reviews.
Every pull request is reviewed before merge; the reviewer returns findings, not a rewrite.
Adversarial review is used for T3 only.
A person passes gate 3 for every merge; no agent merges its own work.
</review>
<escalation>
A failed check allows one rework at the same tier, and the rework starts with a failing test that reproduces the problem.
A second failure moves the task up one tier.
A third failure goes to a named engineer; the task stops and no further agent attempt runs (stop-loss).
Escalation happens at the start of a new session, not mid-task, because a mid-task switch loses the prompt cache.
</escalation>
<budgets>
Every task has a token cap from the routing table; the task stops when it reaches the cap and counts as a failed check.
Every task carries a cost tag with team, work order and class through the model gateway.
A call without a cost tag is rejected by the gateway.
</budgets>
<context>
Prompt caching is on for shared context.
Shared context is read first and kept stable, so the cache is reused across subagents.
</context>
```

## 4. Telemetry recorded per agent task

| Field | Meaning |
|---|---|
| Task class | T0, T1, T2 or T3 |
| Work order | The issue the task serves |
| Engine and model id | The tool and the exact model id used |
| Effort | The effort tier |
| Tokens in, out, cached | As reported by the gateway |
| Cost | USD, from the gateway's cost tag |
| Wall time | Minutes from start to check result |
| Check result | Pass or fail on the first check |
| Rework count | Number of reworks before merge |
| Reviewer findings | Count and severity |
| Outcome | Merged or rejected |
| Escaped defect | Linked later from incidents |

These records land in the same OpenTelemetry traces in Phoenix and the same audit tables as the pipeline ([ADR-010](decisions.md)). Phoenix is for reading; `model_call` and `audit_event` stay the source of truth.

## 5. Self-improvement

The routing table is versioned config. A weekly review reads it against the telemetry above.

- **Promote a cheaper engine for a class** when, on at least 50 tasks of that class, its first-check pass rate has a Wilson 95% lower bound no more than 5 points below the incumbent's point estimate, and its escaped-defect rate is not higher.
- **Demote** (move the class up one engine) on the reverse: on at least 50 tasks, the current engine's first-check pass rate has a Wilson 95% upper bound more than 5 points below the point estimate of the engine one tier up, or its escaped-defect rate is higher.
- The sample rule is the one that certifies the judges: at least 50 labels per class and a Wilson 95% lower bound ([evals.md](evals.md), [ADR-006](decisions.md)).

## 6. Open-weight challengers

| Challenger | Status (04/11/2026, FOUND) | Why track it |
|---|---|---|
| GLM 5.3 | Weights public by 28/08/2026; custom licence | Self-hosting inside the VPC; price pressure on the vendors |
| DeepSeek V4.1 Flash | MIT licence; 17/10/2026 snapshot | Same |
| Next large Qwen | Qwen 4 is unreleased: announced as "in training", no size or date. The nearest real model is Qwen3.8-2.4T-A95B | Same |

Challengers run in shadow on replayed factory tasks: past accepted pull requests with their hidden tests, which are the factory's own benchmark. They never touch live code. They are promoted only by the rule in section 5. Public leaderboards are used to rule models out, not to rank them.

## 7. Clef as the router and the telemetry triager

Clef (`cloudflare/clef`) is an open-weight decision model with a 65k context. It answers typed questions with probabilities and writes no text (FOUND, [decision-models-and-telemetry.md](research/decision-models-and-telemetry.md)). It is the same kind of model the Signal Engine uses for triage ([ADR-003](decisions.md)).

**Router.** At work-order intake, before any session starts, Clef answers four typed questions: task class T0 to T3 (choice), touches a crown-jewel path (yes or no), spec clear enough to build (yes or no), and expected size (score 1 to 4). It acts at intake because most of the routing saving comes from choosing at session start, and a mid-task switch pays back only after 8-291 requests (FOUND, [research note](research/model-routing-evidence.md), Q5).

```text
<router>
Code, not Clef, decides T3: any change touching a path on the crown-jewel list is T3 whatever Clef says.
Below the confidence threshold, the work order routes one class up, never down.
A work order with an unclear spec goes back to its author, not to a builder.
Clef's choice is used without an engineer confirming it only after at least 50 labelled outcomes per class and a Wilson 95% lower bound of at least 0.75.
Until then Clef runs in shadow beside the routing table and the miss rate is reported weekly.
</router>
```

The "one class up" rule exists because the cited routing study had 12.5% false downgrades (FOUND).

**Telemetry triager.** Each night Clef reads one compact summary per agent task, built by code. It holds the section 4 fields, the check result, the reviewer findings and the last error lines. Clef never reads a raw trace: one agent task can run to 4.8M tokens (FOUND, research note, Q2), and Clef's context is 65k. It answers three typed questions:

- Did the task fail (yes or no)?
- What was the failure cause (spec gap, wrong tier, flaky test, tool or environment error, model error, other)?
- Does it need a person's look (yes or no)?

Its labels feed the weekly routing review in section 5 and the rework statistics. A person reviews a fixed weekly sample, as in the Signal Engine's noise audit. Root-cause analysis stays with a strong model or an engineer: a decision model sorts, it does not explain.

**Why Clef for both (INFERRED).** It is cheap and fast: $0.24 per million input tokens and a 209 ms median, both vendor-reported (FOUND). Its open weights can run inside the VPC next to the telemetry, so trace data never leaves. It comes from a different model family than the Claude and Codex builders, so it does not grade its own family's work.

Designed, not built in this demo.

## 8. Evidence

Prices are USD per million tokens. Blank means not found. "Vendor" means self-reported. Full sources and cautions are in the [research note](research/model-routing-evidence.md).

| Model | In/out | SWE-bench Pro | Terminal-Bench | Cost per task | Label and source |
|---|---|---|---|---|---|
| Opus 5.5 | 4/20 | 89.9% (vendor scaffold) | 4.0: 66.4% (xhigh) | $11.42 (max effort) | FOUND: vendor page; Artificial Analysis summary |
| Sonnet 5.5 | 2/10 | V2: 95.79 | 4.0: 70.6% (medium) | | FOUND: vendor page; Scale leaderboard |
| Haiku 5.5 | 0.10/0.50 | V2: 87.23 | 4.0: 39.2% | | FOUND: vendor page; Scale leaderboard |
| GPT-6.1 Sol | 2/10 | V2: 96.11 | Science: 57.0% (max) | $1.50 (Codex, max) | FOUND: Scale; secondary page; Artificial Analysis summary |
| GPT-6.1 Terra | 1/5 | | | | FOUND: OpenAI pricing page; no benchmark found |
| GLM 5.3 | 1.40/4.40 | V2: 95.60 | 2.1: 88.2 (vendor, not comparable) | | FOUND: Scale; vendor-reported |
| DeepSeek V4.1 Flash | 0.15/0.60 | | 4.0: 42.3 (vendor) | $0.39 (Codex, max) | FOUND: model card; Artificial Analysis summary |
| Qwen3.8-2.4T (not Qwen 4) | 2/6 | 67.7% (vendor) | 4.0: 11.1 | | FOUND: OpenRouter listing |

V2 scores come from one harness at different efforts and sit near saturation. Terminal-Bench versions are not comparable with each other.

- **Routing saves a modest share.** A classifier that routed Claude Code traffic recovered 14-21% of spend, mostly by choosing the cheapest capable model at session start. A mid-task switch paid back only after 8-291 requests. Equal quality was assumed, not measured (FOUND, preprint).
- **A cheap scout can match a top model.** On 266 SWE-bench Pro tasks, a cheap scout routing to cheap fixers solved 159 against 158 for Opus 4.6 alone, at a reported cost per solve of $0.230 against $1.274. A reviewer note puts the saving nearer 43% of the cost, and the quality gain was not significant (p=0.401). Older models (FOUND, preprint).
- **A top-tier advisor is not worth it by default.** Opus 5.5 with a Fable 5.1 advisor scored 1.7 points higher at about 2.1x the cost, at the edge of noise (FOUND, secondary).
- **About a third of agent pull requests are rejected.** Acceptance was 61.6% to 77.9% by tool across 7,156 filtered PRs; by task, tests 61.5% and performance 55.4%, chores 84.0% (FOUND, MSR 2026). Rework was not measured directly.
- **Gaps.** No source measured a mixed Claude and Codex pipeline end to end, with quality and cost together. Cost per task varies up to 30x for the same task (FOUND, secondary).

## 9. Cost scenario (INFERRED)

Assumptions, all INFERRED unless marked FOUND:

- 100 tasks a day: T0 45, T1 35, T2 15, T3 5.
- Opus 5.5 costs $11.42 a task (FOUND, at max effort). Other engines are scaled from it by list-price ratio at equal tokens: Haiku 5.5 at 1/40, Terra at 1/4, Sonnet 5.5 at 1/2. GPT-6.1 Sol has a FOUND $1.50 a task, but T2 uses the higher Sonnet figure, so the result is conservative.
- T3 costs one full Opus 5.5 task for planning and review, plus a Terra build.
- 30% of T0 and T1 tasks fail once and escalate one tier (from the roughly one-third rejection rate). All-Opus has no rework.
- Review by the other family and orchestration are not costed for T0 to T2. The Opus baseline at max effort is likely high for routine work, so the saving is probably overstated.

The script is [scripts/delegation_cost.py](../scripts/delegation_cost.py). It asserts that the routed total is lower and that totals equal the sum of the parts. Its output:

```text
class  tasks  unit_usd  rework_usd  total_usd
T0        45      0.29       38.54      51.39
T1        35      2.85       59.95     159.88
T2        15      5.71        0.00      85.65
T3         5     14.28        0.00      71.38
All Opus 5.5 : 1142.00 USD per day
Routed       : 368.30 USD per day
Saving       : 67.8%
```

## 10. Measured on this build

This repo was built with the same pattern: an Opus orchestrator, Codex Terra and Gemini via agy as builders, and Sonnet subagents checking every pull request. Gemini was used here only to save cost on a non-critical demo. It is not part of the Keelwater proposal.

Tokens per model are measured from the session logs by scripts/measure_tokens.py (reports/factory/tokens-by-model.csv; method and price sources in reports/factory/README.md). The table is generated: do not edit it by hand.

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

<!-- tokens:end -->

Pass rates and reworks per work order and engine task come from reports/factory/build-telemetry.csv, refreshed by scripts/telemetry_summary.py (#28 Part B; columns explained in reports/factory/README.md). The block below is generated from that file: do not edit it by hand.

<!-- measured:start -->

11 done, 2 partial, 0 in progress: refreshed on 05/11/2026
(55 rows across 13 work orders.)

First-check pass rate, reworks and share of building, per engine (build rows only; rows without a PASS or REWORK first check are left out of the rate).

| Engine | First check passed | Pass rate | Reworks | Build rows | Share of build rows |
|---|---|---|---|---|---|
| opus | 0 of 0 | n/a | 0 | 0 | 0% |
| sonnet | 7 of 12 | 58% | 5 | 12 | 92% |
| codex | 1 of 1 | 100% | 0 | 1 | 8% |
| agy | 0 of 0 | n/a | 0 | 0 | 0% |

Total reworks (REWORK verdicts on build pull requests): 5.
Codex and agy built 1 of 13 done or partial work orders (8%); their share of all 13 build rows is 8%.

<!-- measured:end -->
