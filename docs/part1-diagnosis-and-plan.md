# Keelwater: product lifecycle diagnosis and 90-day plan

Andras Fugedi, 03/11/2026

Assumed (invented or from conversation): Gong, Fireflies, Intercom with Fin, FullStory, HubSpot, Notion, Shortcut, and Metabase on production Postgres; customer data stays in Keelwater's AWS VPC, fully audited; the platform's leading harness cannot run always-on agents; the factory launches next quarter; a head of data engineering is being hired; open-weight models will be self-hosted; PMs can give a labelling half-day.

As build cost falls, the constraint moves left to deciding what to build and right to release and adoption. Coding and testing are about 25-35% of idea-to-launch time ([Bain](https://www.bain.com/insights/from-pilots-to-payoff-generative-ai-in-software-development-technology-report-2025/), FOUND[^1]). Halving needs 50 points, so even zero build time leaves about 20 to find in Decide, Define and release (INFERRED).

## 1. Where the lifecycle loses time and value

- Feedback arrives by four routes and nobody consolidates it, so PMs hear the loudest account.
- A third of PM time goes on status, data chasing and "what shipped?" (self-reported).
- Each tool computes its own metrics.
- With no shared spec, engineers and agents guess at intent.
- Decisions go unwritten, so settled arguments reopen.
- Across 655 firms, coding agents raised PR volume about 36% and submission-to-approval time 56% (Harvard/Jellyfish working paper, FOUND).
- Daily releases push change cost onto customers, who retrain claims handlers.

Every handoff runs through someone's memory or a meeting; AI sped up the steps and left the joins alone.

Evidence missing: value-stream timing per squad, PR review wait, signal share per route, each tool's metrics side by side, retraining cost per release, a two-week PM time diary.

## 2. The lifecycle in an agentic world

Agents read, draft and check; named people pass five gates.

| Stage | Agents and pipelines | Gate (who) | Artefact |
|---|---|---|---|
| Sense | Nightly Signal Engine: triage, extraction, verified quotes | None; 40 drops audited weekly | Insights |
| Decide | Clustering, formula ranking, cited briefs, judges | Accept (PM) | Decision log entry |
| Define | Intent-doc agent, design-system mockup | Sign-off (Trio) | Intent doc, factory job |
| Build | Platform factory | Merge (engineers) | PR behind a flag |
| Release | Bundle assembler: notes, notices, customer impact | Bundle (PM, customer success) | Bundle manifest |
| Enable | Help articles, videos, post-call briefs | Comms (product marketing manager) | Articles, videos |
| Learn | Adoption against the intent doc's outcome metric | None | Outcome report |

**Handoffs.** Each stage passes a typed artefact with a status. Agents move items only into states their stage owns, only named people pass gates, and every move is logged. The intent doc (problem, evidence, outcome metric, acceptance criteria, non-goals) and its factory job form the platform contract; the job cites evidence by reference, so quotes stay in the VPC.

**Noise and accuracy.** A sub-cent decision model drops chatter; a weekly sample of 40 drops measures what it misses. Code checks every quote, citation and number. Three judges from another model family test faithfulness, signal and duplication; each stays "calibrating" until 50 blind PM labels per class put the 95% lower bound of its true-positive and true-negative rates at 0.75.

**Deploy daily, release in bundles.** Code ships daily behind flags; customers get an announced monthly bundle with a preview, evidence of the controlled change the EU's [Digital Operational Resilience Act, Art. 9](https://www.digital-operational-resilience-act.com/Article_9.html) expects (FOUND). Customers then wait up to four weeks, so I track idea-to-production-behind-flag and idea-to-customer separately and offer opt-in early-access cohorts.

## 3. Shared infrastructure

Standard is whatever crosses squads, feeds a comparison or must survive an audit.

| Standard (product ops owns) | Set by each squad |
|---|---|
| Signal schema and core taxonomy | Taxonomy extensions, ranking weights |
| Intent-doc template, factory job schema, decision log | Own skills, extra template sections |
| Model gateway and routing rules | Prompts within guardrails |
| Eval harness and judge registry | Judge thresholds above the shared floor |
| Telemetry, audit, access control | Digest cadence, in-squad visibility |
| One metric dictionary | Squad metrics, defined in it |

## 4. The first 90 days

Everything runs in the VPC on a scheduled job runner that product ops owns, moving onto the platform harness if it gains scheduling. My ask: one engineer seconded for 90 days and platform support for the intake API; without the engineer, day 90 covers three squads, not five.

**Day 30.** Running: the Signal Engine nightly for a volunteer pilot squad on tickets and sales calls; a Shortcut "what shipped" digest for every squad. Users: the pilot Trio; all PMs for a labelling half-day (about 250 labels). Learned: signal share per route, value-stream baselines. Go: the pilot PM accepts three of the top 10, reviewed in 30 minutes.

**Day 60.** Running: all routes plus sessions (code cuts idle time, a small model picks windows); intent-doc handoff for two squads; the decision log; flags and bundle manifest in the digest; a bundle pilot with three large customers. Users: two Trios, customer success. Learned: acceptance, judge agreement, review churn. Go: acceptance above 30% and no pilot customer leaves bundles.

**Day 90.** Running: intake for three to five squads, by staffing; outtake drafts (release notes, help articles, change notices, follow-up briefs); the intent-doc schema ready for launch. Users: PMs, product marketing, sales. Learned: pilot against control; where the bottleneck moved.

Adoption is the harder half:

- The VP Product sponsors it; the pilot squad volunteers.
- I give first: the digest removes status reporting before PMs label.
- Labelling happens in the Monday review (blind label panel, noise sample).
- The board replaces the weekly feedback meeting.
- The factory accepts only signed intent docs.
- Metrics at 30/60/90 days: weekly active PMs, % of decisions with written rationale, % of customer-visible changes flagged.

## 5. What I will not touch, and the platform contract

- The coding-agent harness is the platform team's; a second would split two engineers.
- Engineering owns code-review policy; I supply review-wait data.
- Squad structure: I have no authority, and changing it alongside tooling would hide which worked.
- The design system, which designers already prototype on.
- The metric dictionary waits for the head of data engineering.

I ask the platform team for an intake API, a co-owned versioned factory job schema, gateway access with per-team cost tags, OpenTelemetry into self-hosted Phoenix, previews and demo videos, and per-customer flag cohorts. I own the lifecycle agents and job runner, schemas, evals, judges and adoption.

## 6. What to tell leadership and what to measure

Tell the board that coding speed alone cannot halve delivery: in a [McKinsey study](https://www.mckinsey.com/industries/technology-media-and-telecommunications/our-insights/how-generative-ai-could-accelerate-software-product-time-to-market) of 40 PMs, a 40% productivity gain moved time to market about 5% (FOUND). In 90 days expect status work down from a third of PM time to under a tenth, feedback-to-decision in days, and every build decision written. Halving is a 12-month question.

Before adding squads, compare pilot and control squads on both lead times, status hours, acceptance, judge agreement and review wait. My recommendation changes if:

- acceptance stays below 30% after calibration: rework taxonomy and ranking with PMs first;
- review dominates lead time: fund review capacity (smaller PRs, agent pre-review) before more intake;
- customers reject bundles: give each customer flag-level control instead.

Part 2, the working Signal Engine, is in this repo; start at the README.

[^1]: FOUND: in the cited source. INFERRED: my reasoning from sources.
