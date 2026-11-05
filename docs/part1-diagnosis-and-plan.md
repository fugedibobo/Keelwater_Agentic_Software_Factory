# Keelwater: product lifecycle diagnosis and 90-day plan

Andras Fugedi, 03/11/2026

> **Assumed (invented or from conversation)**
>
> - Tools: Gong, Fireflies, Intercom with Fin, FullStory, HubSpot, Notion, Shortcut, and Metabase on production Postgres
> - Customer data stays in Keelwater's AWS VPC, audited; open-weight models are self-hosted
> - The platform's leading harness cannot run always-on agents; the factory launches next quarter
> - A head of data engineering is being hired; PMs can give a labelling half-day

<!-- separate callouts -->

> **The point.** As build cost falls, the constraint moves left to deciding what to build and right to release and adoption.
>
> - Coding and testing are about 25-35% of idea-to-launch time ([Bain](https://www.bain.com/insights/from-pilots-to-payoff-generative-ai-in-software-development-technology-report-2025/)).
> - Halving needs 50 points, so even zero build time leaves about 20 to find in Decide, Define and release (estimated).
> - Section 6 shows my model does not find them within 18 months.

## 1. Where the lifecycle loses time and value

AI sped up the steps but not the joins, and the joins run through memory and meetings. Value leaks at five of the seven stages:

| Sense | Decide | Define | Build | Release | Enable | Learn |
|---|---|---|---|---|---|---|
| Four feedback routes nobody consolidates, so PMs hear the loudest account | Decisions go unwritten, so settled arguments reopen | Intent goes unwritten, so engineers and agents guess at it | Faster coding fills review queues | Daily releases make customers retrain claims handlers | — | — |

- A third of PM time goes on status, data chasing and "what shipped?" (self-reported); each tool has its own metrics.
- Across 655 firms, coding agents raised PR volume about 36% and submission-to-approval time 56% (Harvard/Jellyfish working paper).
- **Evidence missing:** value-stream timing per squad, PR review wait, signal share per route, each tool's metrics side by side, retraining cost per release, a two-week PM time diary.

## 2. The lifecycle in an agentic world

The PDLC (product development lifecycle) runs from customer signal to measured outcome in seven stages. Agents read, draft and check; named people pass five gates.

| Stage | Agents and pipelines | Gate (who) | Artefact |
|---|---|---|---|
| Sense | Nightly Signal Engine: triage, extraction, verified quotes | None; 40 drops audited weekly | Insights |
| Decide | Clustering, formula ranking, cited briefs, judges | Accept (PM) | Decision log entry |
| Define | Intent-doc agent; mockup generated from it on the real design-system components | Sign-off (Trio, designer included) | Intent doc, factory job |
| Build | Platform factory | Merge (engineers) | PR behind a flag |
| Release | Bundle assembler: notes, notices, customer impact | Bundle (PM, customer success) | Bundle manifest |
| Enable | Help articles, videos, post-call briefs | Comms (product marketing manager) | Articles, videos |
| Learn | Adoption against the intent doc's outcome metric | None | Outcome report |

- **Handoffs.** Each stage passes a typed artefact with a status. Agents move items only into states their stage owns, only named people pass gates, and every move is logged.
- **Platform contract.** The intent doc and its factory job; the job cites evidence by reference, so quotes stay in the VPC.
- **Skills.** One shared library: versioned, evaluated, owned by product ops, with squads adding their own. First five: intent-doc writer, release-notes drafter, SQL against the metric dictionary, call summary to insight, change-notice drafter. The human skill: using AI well.
- **Designers.** Customer quotes and session-recording moments feed them directly; the designer signs off the generated mockup within the Trio gate.
- **The factory.** A delegation meta-harness: signal in, it orchestrates people and sub-harnesses (the platform team's coding harness, Codex, a hosted or open-weight model) and passes the human gates. Its operating rules are the [delegation ruleset](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/blob/main/docs/delegation.md); owning the coding harness is not required.
- **Noise.** A sub-cent decision model drops chatter; 40 sampled drops a week measure what it misses.
- **Accuracy.** Code checks every quote, citation and number. Three judges from another model family (faithfulness, signal, duplication) stay "calibrating" until 50 blind PM labels per class put each one's true-positive and true-negative rates' 95% lower bound at 0.75.
- **Deploy daily, release in bundles.** Code ships daily behind flags; customers get an announced monthly bundle with a preview, the controlled change the EU's [Digital Operational Resilience Act, Art. 9](https://www.digital-operational-resilience-act.com/Article_9.html) expects. Customers wait up to four weeks, so I track idea-to-production-behind-flag and idea-to-customer separately and offer opt-in early access.

## 3. Shared infrastructure

Standard is whatever crosses squads, feeds a comparison or must survive an audit.

| Standard (product ops owns) | Set by each squad |
|---|---|
| Signal schema and core taxonomy | Taxonomy extensions, ranking weights |
| Intent-doc template, factory job schema, decision log, skill library | Own skills added to the library, extra template sections |
| Model gateway and routing rules | Prompts within guardrails |
| Eval harness and judge registry | Judge thresholds above the shared floor |
| Telemetry, audit, access control | Digest cadence, in-squad visibility |
| One metric dictionary: v0 (about 10 lifecycle metrics) in 60 days, the rest later with data engineering | Squad metrics, defined in it |

## 4. The first 90 days

- Everything runs in the VPC on a product-ops job runner, moving to the platform harness if it schedules.
- **My ask:** one engineer for 90 days and platform support for the intake API; without the engineer, day 90 covers three squads, not five.

| | Day 30 | Day 60 | Day 90 |
|---|---|---|---|
| **Running** | • Signal Engine nightly for a volunteer pilot squad on tickets and sales calls<br>• A Shortcut "what shipped" digest for every squad | • All routes plus sessions<br>• Intent-doc handoff for two squads, with decision log and metric dictionary v0<br>• Flags and bundle manifest in the digest<br>• A bundle pilot with three large customers | • Intake for three to five squads, by staffing<br>• Outtake drafts (release notes, help articles, change notices, follow-up briefs) |
| **Users** | The pilot Trio; all PMs for a labelling half-day | Two Trios, customer success | PMs, product marketing, sales |
| **Learned** | Signal share per route, value-stream baselines | Acceptance, judge agreement, review churn | Pilot against control; where the bottleneck moved |
| **Decision point** | **Go:** the pilot PM accepts three of the top 10 in 30 minutes | **Go:** acceptance above 30%, no pilot customer leaves bundles | **Go:** compare pilot and control before adding squads (section 6) |

Adoption is the harder half:

- The VP Product sponsors it; the pilot squad volunteers.
- I give first: the digest removes status reporting before PMs label.
- Labelling happens in the Monday review, where the board replaces the weekly feedback meeting.
- Metrics: weekly active PMs, % of decisions with written rationale, % of customer-visible changes flagged.

## 5. What I will not touch, and the platform contract

| I leave alone what another team owns, and anything that would blur the pilot | The platform contract |
|---|---|
| • The coding-agent harness is the platform team's; a second would split two engineers<br>• Engineering owns code-review policy; I supply review-wait data<br>• Squad structure: changing it with tooling would hide which worked<br>• The design system itself; I only generate mockups on its components<br>• The warehouse and metrics beyond v0, which come later with data engineering | **I ask the platform team for:** an intake API, a co-owned versioned job schema, gateway access with per-team cost tags, OpenTelemetry into self-hosted Phoenix, previews and demo videos, and per-customer flag cohorts.<br>**I own:** the lifecycle agents, job runner, schemas, evals, judges and adoption. |

## 6. What to tell leadership and what to measure

- **Tell the board** that halving idea-to-customer is not plausible within 18 months. In my [halving model](https://github.com/fugedibobo/Keelwater_Agentic_Software_Factory/blob/main/docs/halving-model.md) the mid case reaches 79% of today's lead time at month 18 (high 51%, AI alone 95%), decided mainly by the discovery-and-decision and release process effects, which are estimated, not measured.
- **Coding speed alone cannot:** in a [McKinsey study](https://www.mckinsey.com/industries/technology-media-and-telecommunications/our-insights/how-generative-ai-could-accelerate-software-product-time-to-market) of 40 PMs, a 40% productivity gain moved time to market about 5%.
- **Achievable:** in 90 days, status work down from a third of PM time to under a tenth, feedback-to-decision in days, every build decision written; by month 18, about a fifth off lead time (estimated).
- **Board tracker:** monthly, lead time toward 50% and throughput toward 2x.

Before adding squads, compare pilot and control on both lead times, throughput, decision latency, release time, status hours, acceptance, judge agreement and review wait. My recommendation changes if:

- pilot decision time falls by half and release time by 70%: halving nears (high case 51%), so I add squads sooner;
- acceptance stays below 30% after calibration: rework taxonomy and ranking with PMs first;
- review dominates lead time: fund review capacity (smaller PRs, agent pre-review) first;
- customers reject bundles: give each customer flag-level control instead.

Part 2, the working Signal Engine, is in this repo; start at the README.
