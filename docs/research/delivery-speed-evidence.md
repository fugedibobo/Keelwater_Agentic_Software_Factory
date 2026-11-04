# Research: where idea-to-customer time sits, and what AI has measurably moved

Researched 04/11/2026 for work order #37. FOUND = read at the source URL on 04/11/2026 (all S-numbers below were accessed that day). INFERRED = my reasoning from named FOUND figures. No benchmark was run. Companies and people are named only as publishers or authors of a source.

## Answer

Published evidence puts only about 25-35% of idea-to-launch time in writing and testing code (S1, FOUND), so the rest sits in deciding, specifying, review wait, release and customer uptake. I found no published stage-by-stage split of the whole journey; the shares below are INFERRED around that one anchor and one decision-latency figure. Measured AI effects are large where the task is isolated coding (about -20% to -56% task time) and small or negative at firm level: PRs rose about 36% but issues resolved rose a borderline 13.7%, and review wait rose about 56-60% (S3). Weighting my mid effects by my mid shares gives about -8% on idea-to-customer time at full adoption (range +5% to -27%; INFERRED arithmetic). AI alone does not halve lead time; review and decision latency are the stages to watch.

## 1. Share of idea-to-customer elapsed time by stage

Low and high are per-stage plausible bounds, not scenarios; only the mid column sums to 1.00.

| Stage | Low | Mid | High | Basis |
|---|---|---|---|---|
| Discovery and decision | 0.15 | 0.27 | 0.35 | INFERRED: S2 says 70% of large enterprises take at least 1-2 months for key decisions; against an assumed 6-month cycle (S18, not re-verified) that is 17-33% |
| Specification | 0.08 | 0.13 | 0.18 | INFERRED: no published share found; sized as the remainder before build |
| Build | 0.16 | 0.20 | 0.23 | INFERRED: S1 coding and testing together 25-35% (FOUND); split about two to one |
| Review | 0.03 | 0.07 | 0.12 | INFERRED: S3 baseline submission-to-merge 3.56 days (FOUND) is about 2% of 180 days; raised for re-review and idle time (S16: half of PRs idle over 50% of their life, secondary) |
| Test | 0.09 | 0.10 | 0.12 | INFERRED: remainder of S1's 25-35% |
| Release | 0.05 | 0.10 | 0.15 | INFERRED: no measured share; Keelwater's monthly bundle adds up to four weeks (Part 1) |
| Adoption | 0.07 | 0.13 | 0.20 | INFERRED: unknown; no published time-to-adopt benchmark found |

Check on S1: build + test mid = 0.30, inside 25-35%.

## 2. Measured AI effect on stage time (fractional change; negative = faster)

Low = least benefit, high = most benefit.

| Stage | Low | Mid | High | Basis |
|---|---|---|---|---|
| Discovery and decision | 0.00 | -0.10 | -0.30 | INFERRED: S18 (secondary only) reports PM productivity +40% but time to market only about -5%; decision latency is organisational (S2). No direct measurement |
| Specification | 0.00 | -0.15 | -0.35 | INFERRED: same source and gap; drafting is fast, sign-off is not |
| Build | -0.04 | -0.20 | -0.40 | FOUND ranges: S7 -4% (new developers) and -18% (returning), S9 +26.08% weekly PRs (about -21% time), S8 55.8% faster on one isolated task, S1 10-15% productivity. Mid and high INFERRED from these. S6 (+19% slower, early 2025) sits below the low |
| Review | +0.56 | +0.15 | -0.30 | Low FOUND: S3 agents, time to approval +56.1%, backlog +59.9%, active review +58.5%. High INFERRED: S11 cut overdue-PR resolution 60%, applied to the roughly half of PR life that is idle (S16). Mid INFERRED: between them, as S3 finds 79.1% of firms use AI review tools and the bottleneck persists |
| Test | +0.15 | 0.00 | -0.15 | INFERRED: no measured test-stage time found; S5 reports bugs per developer +54% and S12 delivery stability -7.2% (per the post, increment not stated), which argue for rework |
| Release | +0.05 | 0.00 | -0.15 | INFERRED: no measured effect found; S1 says manual release steps "choke" the gains |
| Adoption | 0.00 | 0.00 | -0.10 | INFERRED: no evidence either way (S14's onboarding 91 to 49 days is for developers, not customers) |

Queue and volume evidence (FOUND): S3 agents PRs opened +35.7%, issues resolved +13.7% (assistants +25.2% and +2.0%, not significant); S4 PRs merged +98%, PR size +154%, review time +91%, no company-level DORA correlation; S5 median time in review +441.5%, PRs merged unreviewed +31.3% (S5 compares each firm's lowest and highest adoption periods, so it overstates a fixed-baseline change); S12 per 25% rise in adoption, code review speed +3.1% but delivery throughput -1.5% and stability -7.2%. Reference points: S10 Google's median review latency was under 4 hours (2018), Microsoft's median time to approval 24 hours.

## 3. Published adoption curves

| Source | Shape | Label |
|---|---|---|
| S9 | Treated developers: 8.5% sign-up in two weeks, 42.5% after two reminders (one firm); with training, about 60% plateau after 1-2 months, 69.4% by 04/2024 (another); 30-40% never tried it | FOUND |
| S3 | Firms adopting an agent: near 0 (10/2024) to 91.0% (01/2026). Individuals inside an adopting firm: 37.6% at 16 months (assistants), 35.3% at 12 months (agents); the authors call both lower bounds | FOUND |
| S4 | Weekly use above 60% began only in the last two to three quarters at most firms | FOUND |
| S5 | 80% of teams exceed 50% weekly active users (04/2026) | FOUND |
| S14 | 91% adoption overall; one large enterprise went from under 10% to about 70% regular use; 22% of merged code AI-authored (self-reported) | FOUND |
| S15 | Use or plan to use 76% (2024) to 84% (2025); daily use 47.1%; agents daily 14.1% | FOUND |
| Month-by-month ramp for a trained rollout | Mid: 8% at month 1, 60% by month 10, flat | INFERRED: S9's trained plateau of about 60%; S3's 35-38% is the untrained floor |

No source publishes a monthly curve of share of work done with AI; the draft ramp below is reasoned from these points.

## 4. What would change this

- A per-squad value-stream timing (Part 1 names it as missing) replaces every INFERRED share.
- A measured review wait for Keelwater: if baseline review is over 12% of lead time, review becomes the largest lever.
- A decision log showing decisions taking days, not 1-2 months, shrinks the discovery share.
- A published full-lifecycle AI study (not coding tasks) would replace the discovery, specification and test effects.
- Newer tools: S7 says developers are likely faster now than in early 2025, so the low build effect may be too cautious.

## 5. Gaps

- No published share of elapsed time for discovery, specification, release or customer adoption: unknown.
- No measured AI effect on test, release or adoption stages: unknown.
- S18 (McKinsey, 40 project/product managers, 40% PM productivity, about 5% time to market): the primary page timed out, so only search summaries were read; the wording "project" or "product" managers is unresolved.
- Not verified: ASOS flow-efficiency survey (HTTP 403), CircleCI 2026 report (HTTP 403), DORA full reports (effect sizes beyond blog posts), DX, Pendo and LinearB primary tables (only vendor pages or secondary summaries).
- S3 is a job-market paper, not peer reviewed; S4, S5 and S14 are vendor telemetry, correlational, and partly self-reported.

## Sources (all accessed 04/11/2026)

- S1 https://www.bain.com/insights/from-pilots-to-payoff-generative-ai-in-software-development-technology-report-2025/ (23/09/2025)
- S2 https://productboard.com/ebook/2024-product-excellence-report (2024)
- S3 https://fion.ac/jellyfish.pdf (version dated 01/11/2026)
- S4 https://www.faros.ai/blog/ai-software-engineering (23/07/2025)
- S5 https://faros.ai/blog/ai-acceleration-whiplash-takeaways (12/04/2026)
- S6 https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/ (10/07/2025)
- S7 https://metr.org/blog/2026-02-24-uplift-update/ (24/02/2026)
- S8 https://arxiv.org/abs/2302.06590 (13/02/2023)
- S9 https://economics.mit.edu/sites/default/files/inline-files/draft_copilot_experiments.pdf (02/2025)
- S10 https://sback.it/publications/icse2018seip.pdf (2018)
- S11 https://arxiv.org/abs/2011.12468 (revised 17/06/2022)
- S12 https://cloud.google.com/blog/products/devops-sre/announcing-the-2024-dora-report (23/10/2024)
- S14 https://getdx.com/blog/ai-assisted-engineering-q4-impact-report-2025/ (updated 04/11/2025)
- S15 https://survey.stackoverflow.co/2025/ai (2025)
- S16 https://dev.to/vitalii_petrenko_dev/the-hidden-cost-of-slow-code-reviews-data-from-8-million-prs-5fei (secondary, reports LinearB data on 8.1M PRs)
- S18 https://www.mckinsey.com/industries/technology-media-and-telecommunications/our-insights/how-generative-ai-could-accelerate-software-product-time-to-market (31/05/2024 per search summary; page not loaded)

## Model inputs (draft)

```yaml
# Stage shares: mid sums to 1.00. low/high are per-stage bounds, not scenarios.
stage_shares:
  discovery_decision: {low: 0.15, mid: 0.27, high: 0.35, label: INFERRED, source: "S2 plus 6-month cycle assumption (S18)"}
  specification:      {low: 0.08, mid: 0.13, high: 0.18, label: INFERRED, source: "no published share; remainder before build"}
  build:              {low: 0.16, mid: 0.20, high: 0.23, label: INFERRED, source: "S1 coding+testing 25-35%"}
  review:             {low: 0.03, mid: 0.07, high: 0.12, label: INFERRED, source: "S3 3.56-day baseline; S16 idle share"}
  test:               {low: 0.09, mid: 0.10, high: 0.12, label: INFERRED, source: "S1 remainder of 25-35%"}
  release:            {low: 0.05, mid: 0.10, high: 0.15, label: INFERRED, source: "no measured share; Part 1 monthly bundle"}
  adoption:           {low: 0.07, mid: 0.13, high: 0.20, label: INFERRED, source: "unknown; no benchmark found"}

# AI effect on stage time: fractional change, negative = faster. low = least benefit, high = most.
ai_effect:
  discovery_decision: {low: 0.00,  mid: -0.10, high: -0.30, label: INFERRED, source: "S18 (secondary), S2"}
  specification:      {low: 0.00,  mid: -0.15, high: -0.35, label: INFERRED, source: "S18 (secondary)"}
  build:              {low: -0.04, mid: -0.20, high: -0.40, label: INFERRED, source: "FOUND S7, S9, S8, S1; mid/high reasoned"}
  review:             {low: 0.56,  mid: 0.15,  high: -0.30, label: INFERRED, source: "low FOUND S3; high from S11 and S16; mid reasoned"}
  test:               {low: 0.15,  mid: 0.00,  high: -0.15, label: INFERRED, source: "no measurement; S5, S12 argue rework"}
  release:            {low: 0.05,  mid: 0.00,  high: -0.15, label: INFERRED, source: "no measurement; S1"}
  adoption:           {low: 0.00,  mid: 0.00,  high: -0.10, label: INFERRED, source: "no evidence"}

# Share of work done AI-assisted, months 1..18.
adoption_ramp:
  label: INFERRED
  source: "S9 trained plateau about 60%; S3 untrained 35-38% at 12-16 months"
  low:  [0.03, 0.05, 0.08, 0.11, 0.14, 0.17, 0.20, 0.23, 0.26, 0.29, 0.31, 0.33, 0.34, 0.36, 0.37, 0.38, 0.38, 0.38]
  mid:  [0.08, 0.16, 0.25, 0.33, 0.40, 0.46, 0.51, 0.55, 0.58, 0.60, 0.60, 0.60, 0.60, 0.60, 0.60, 0.60, 0.60, 0.60]
  high: [0.30, 0.50, 0.60, 0.64, 0.67, 0.69, 0.70, 0.71, 0.72, 0.72, 0.72, 0.72, 0.72, 0.72, 0.72, 0.72, 0.72, 0.72]
```
