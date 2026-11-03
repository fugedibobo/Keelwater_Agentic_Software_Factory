# Keelwater: product lifecycle diagnosis and 90-day plan

Andras Fugedi, 03/11/2026

**Thesis.** When build effort approaches zero, the constraint moves left, to deciding what to build, and right, to release, enablement and adoption by regulated customers.

Coding and testing take about 25-35% of idea-to-launch time ([Bain](https://www.bain.com/insights/from-pilots-to-payoff-generative-ai-in-software-development-technology-report-2025/), FOUND), so even infinitely fast coding cannot halve lead time (INFERRED, Amdahl's law). Review is slowing too: across 655 firms, coding agents raised PR volume about 36% and submission-to-approval time 56% ([Harvard/Jellyfish](https://fion.ac/jellyfish.pdf), FOUND); vendor telemetry shows median time in review up more than fivefold ([Faros 2026](https://faros.ai/blog/ai-acceleration-whiplash-takeaways), FOUND, correlational). In the words of [DORA 2025](https://cloud.google.com/blog/products/ai-machine-learning/announcing-the-2025-dora-report), AI "amplifies what's already there". Halving timelines needs the left and right of build to shrink and review to keep pace.

Assumed: Gong (sales calls), Fireflies (other calls), Intercom with Fin (support), FullStory (sessions), HubSpot (accounts), Notion, Shortcut, and Metabase on production Postgres. Customer data stays in Keelwater's AWS VPC, fully audited.

## 1. Where the lifecycle loses time and value

- **Unconsolidated feedback.** Four routes (sales, support, onboarding, account management), four tools. PMs hear the loudest account and miss problems spread across many.
- **Status work.** About a third of PM time goes on status, data chasing and "what shipped?" (self-reported).
- **Disagreeing metrics.** Each tool computes its own; Metabase queries production with no shared definitions.
- **No shared spec.** Intent is re-explained in meetings and review comments; engineers and agents guess.
- **Unwritten decisions.** Reasoning is lost and settled arguments reopen.
- **Review queues.** PR volume rises; review capacity does not.
- **Release friction.** Daily releases push change cost onto customers, who retrain claims handlers and must evidence controlled change.

The common cause is missing shared artefacts: every handoff passes through someone's memory or a meeting. AI sped up each step and left the joins untouched.

Evidence needed and missing: value-stream timing per squad (idea, spec, PR, merge, release, adoption); PR review wait; feedback volume and signal share per route; each metric from each tool side by side; retraining cost per release from three customers; the share of decisions with a written rationale; a two-week PM time diary.

## 2. The lifecycle in an agentic world

I define the product lifecycle as seven stages: Sense, Decide, Define, Build, Release, Enable, Learn. Agents read, draft and check; people own five gates.

| Stage | Agents, pipelines, skills | Human gate (who) | Artefact |
|---|---|---|---|
| Sense | Nightly Signal Engine: connectors, decision-model triage, extraction with verified quotes | None; PMs audit 5% of dropped noise | Insights linked to source |
| Decide | Clustering, formula ranking, cited briefs, judges; PM Q&A skill | **Opportunity accept** (PM) | Accepted opportunity, decision log entry |
| Define | Intent-doc agent; mockup from design-system components | **Intent sign-off** (Trio) | Intent doc, factory job |
| Build | Platform factory: coding agents, guardrails, code evals, preview, demo video | **Code merge** (engineers; platform-owned) | Merged PR behind a flag |
| Release | Bundle assembler: groups flagged changes; drafts notes, change notice, per-customer impact | **Customer release bundle** (PM + customer success) | Bundle manifest, notice |
| Enable | Help-article drafts; enablement videos; sales pull agent (pre-demo video); follow-up brief within 30 minutes of a call, rep sends | **External comms accept** (PMM) | Articles, videos |
| Learn | Adoption from session analytics and flags against the intent doc's outcome metric | None; monthly review | Outcome report, back to Sense |

**Handoffs.** Each stage passes a typed artefact with a status (proposed, accepted, intent drafted, in factory, shipped, enabled, measured). An agent can only move an item into the state its stage owns; only a named person passes a gate; every move is logged with actor, inputs and model version. The intent doc (problem, evidence, outcome metric, acceptance criteria, non-goals) is the contract with the factory.

**Noise and accuracy.** A decision model costing fractions of a cent per item drops chatter before any expensive model runs, and 5% of drops are audited so missed signal is measured. Code then checks that every quote appears in its source and every citation resolves. Judges from a different model family test each brief for faithfulness, real signal and duplication, and count as trusted only when true-positive and true-negative rates against PM labels both reach 0.90 on 100+ held-out examples ([Husain](https://hamel.dev/blog/posts/llm-judge/), FOUND practice); until then briefs show as unverified. Ranking is a formula PMs can read and challenge.

**Deploy daily, release in bundles.** Code reaches production daily behind flags; customers get an announced monthly bundle with a preview beforehand, and its flags are retired afterwards. Engineering keeps its pace and customers control their rate of change. It also helps insurers evidence control: the EU's [Digital Operational Resilience Act, Art. 9](https://www.digital-operational-resilience-act.com/Article_9.html) expects ICT changes to be "recorded, tested, assessed, approved, implemented and verified in a controlled manner" (FOUND). No rule I found sets a notice period, so the value is evidence of control (INFERRED).

## 3. Shared infrastructure

Standardise whatever crosses a squad boundary, feeds a cross-squad comparison or must survive an audit. Squads own their judgement.

| Standard across squads (product ops owns) | Set by each squad |
|---|---|
| Signal schema and core taxonomy | Taxonomy extensions under core buckets |
| Intent-doc template, factory job schema | Own skills and extra template sections |
| Decision log format and location | Ranking weights |
| Model gateway and routing rules | Prompts within guardrails |
| Eval harness and judge registry | Judge thresholds above the shared floor |
| Telemetry and audit on every agent step | Digest cadence and channel |
| One metric dictionary | Squad metrics, defined in the dictionary |
| Access control | Visibility within the squad |

## 4. The first 90 days

Everything runs on a scheduled harness that product ops owns, inside the VPC, because the platform team's leading factory candidate cannot run always-on agents.

**Day 30.** Running: the Signal Engine nightly for one pilot squad on support tickets and sales calls. Users: the pilot PM and designer; all five PMs for a half-day labelling about 50 items each, roughly 250 labels to seed the judges and a held-out set. Baseline: value-stream timing for every squad from Shortcut, git and release logs, plus the PM diary. Learned: signal share per route, whether ranking matches PM judgement, where lead time goes.

**Day 60.** Running: all four routes plus session analytics (idle time stripped in code, a small model picks interaction windows, only those reach a capable model); judges calibrated or still flagged unverified; intent-doc handoff for the pilot and a second squad; decision log live; a bundle pilot with the three largest customers. Users: two Trios, customer success, three customers. Learned: acceptance rate, judge agreement, whether intent docs cut review back-and-forth, how customers take to bundles.

**Day 90.** Running: all five squads on intake; outtake drafts live (release notes, help articles, change notices, follow-up briefs); intent-doc schema ready for the factory's launch next quarter. Videos and the pull agent wait for the factory's demo artefacts. Users: all PMs, product marketing, customer success, sales. Learned: pilot against control, and where the bottleneck moved. Output: a recommendation to leadership with data.

## 5. What I will not touch, and the platform contract

- **Build harness.** The platform team's; a second harness would split two engineers' effort.
- **Code-review policy.** Engineering owns quality; I supply review-wait data.
- **Squad structure.** I have no authority, and changing structure with tooling would hide which one worked.
- **Design system.** Designers already prototype on it; intent docs reference its components.
- **Daily deploys.** Bundling happens at release, so deploys stay daily.

The platform remit stops at product and design, which is where this layer sits. I ask the platform team for an intake API accepting the intent doc and a versioned factory job schema we co-own; model gateway access with per-team routing and cost tags; one telemetry standard (OpenTelemetry into self-hosted Phoenix) so a trace runs from feedback to merged PR; preview environments and demo videos from each build, which Enable reuses; and a flag service with per-customer cohorts. I own the lifecycle agents and their harness, the schemas, evals and judges, and PM adoption and change management, which is the harder half.

## 6. What to tell leadership and what to measure

Tell the board plainly that coding speed alone cannot halve delivery. In a [McKinsey study](https://www.mckinsey.com/industries/technology-media-and-telecommunications/our-insights/how-generative-ai-could-accelerate-software-product-time-to-market) of 40 PMs, a 40% productivity gain moved time to market about 5% (FOUND). In 90 days expect PM time back (my target: status work from a third of the week to under a tenth), feedback-to-decision latency from weeks to days, every build decision written, and faster release that customers can absorb. Halving is a 12-month question, answered with pilot data.

Before more squads join the factory, compare converted and unconverted squads against their day-30 baselines: idea-to-customer-available lead time, PM hours on status, PM acceptance of ranked opportunities, judge agreement with PMs, and PR review wait.

What would change my recommendation:

- **Acceptance below about 30% after calibration.** The engine misses what PMs value; pause roll-out and rework taxonomy and ranking with them.
- **Lead time flat because review dominates.** Fund review capacity (smaller PRs, intent-linked review, agent pre-review) ahead of more intake.
- **Customers rejecting bundles.** Drop bundles and give each customer flag-level control.

Part 2, a working Signal Engine with its evals and Signal Board, is in this repo; start at the README.
