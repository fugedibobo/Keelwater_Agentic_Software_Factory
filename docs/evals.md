# Evals: how the Signal Engine measures and keeps its accuracy

Andras Fugedi, 03/11/2026, revised after review round 1. Status: design for the demo build. Expands section 6 of docs/architecture.md and uses its stage numbers, enums and CLI.

**Summary.** Every failure mode has a check: deterministic code first, then regression suites against ground truth planted in synthetic data (seed 42 for tuning, seed 43 held out, plus a two-batch stability replay), then three binary LLM judges, then blind PM labels and a weekly noise audit. A judge version is trusted only when its TPR and TNR against at least 50 blind PM labels per class both have a Wilson 95% lower bound of at least 0.75. In the demo no judge gets there, and the board says so.

---

## 1. The three questions

| Question | Short answer | Detail |
|---|---|---|
| How is accuracy maintained? | Code checks what code can; planted ground truth scores every change on a tuning and a held-out seed; certified judges cover the rest. | §3, §4, §5 |
| How is noise kept out? | Five filters in sequence, each measured (below). | §2, §6 |
| How do you know the judge is right? | Blind PM labels, TPR and TNR with Wilson intervals; trust is earned above the bar and lost on drift or any prompt or model change. | §5 |

**Five noise filters.**
1. **Segment (code):** internal speakers (kept only as unquotable context), Intercom admin notes, Fin replies and idle session time go before any model. Measured by run reconciliation.
2. **Triage (decision model):** drop at p <= 0.10. Measured by the noise-drop rate (planted) and the noise-audit miss rate (40 drops a week, §6).
3. **Extract (cheap LLM plus code):** an insight needs a problem and a quote found in the snippet. Measured by the quote verification rate.
4. **Rank (formula):** one account scores low on breadth. Measured by noise-theme suppression and the adversarial probe.
5. **Signal judge, then the PM:** "is this a product problem a squad could act on?", and reject reason codes. Measured by judge TPR/TNR and PM acceptance rate.

---

## 2. Failure modes and what catches each

**D** deterministic (every run); **GT** planted ground truth (every change, seeds 42 and 43); **J** LLM judge; **PM** a reason code or blind label; **NA** noise audit.

| Stage | Failure mode | Caught first by | Also caught by |
|---|---|---|---|
| 1 Segment | An employee's words treated as the customer's | D: speaker mapping via attendee emails and `config/teams.yaml`; unresolved speakers quarantined | GT: attribution |
| 2 Triage | Real complaint dropped as chatter | GT: signal recall | NA: miss rate |
| 2 Triage | Renewal price haggling kept | GT: noise-drop rate, noise-theme suppression | J: signal; PM `not_product_signal` |
| 3 Extract | Hallucinated or altered quote | D: quote verifier | J: faithfulness |
| 3-4 Extract, Enrich | Wrong account (broker, wrong insurer, guessed personal email) | D: account rules and join assertion | GT: attribution incl. join traps |
| 5 Cluster | Over-merged (misfiling fused with bulk upload) | GT: purity, over-merge count | PM `mixed_problems` (kept for the coherence judge, designed only) |
| 5 Cluster | Split, or forked between runs | GT: split count; stability replay | PM merge |
| 5 Tag | Shipped work re-proposed, real problem hidden as shipped, post-ship feedback lost | GT: tagging with hard negatives and post-ship feedback | J: duplicate (disagreement goes to a PM queue); PM `already_shipped` / `already_on_roadmap` |
| 6 Rank | Loud single account outranks a broad problem; score does not match factors | D: score recomputation | GT: exact top-6 set, adversarial probe |
| 7 Brief | Unsupported claim, inflated scope or ARR, conflict shown as consensus | D: citation and number checks | J: faithfulness; PM `evidence_wrong` |
| 10 Handoff | Quote or account name in the factory job | D: schema plus de-identification check | none needed |
| any | Wrong enum, missing or extra field | D: schema validation | stage fallback; run fails if unrecoverable |

---

## 3. Deterministic checks

### 3.1 Schema validation

- **Raw exports (stage 0)** against per-source JSON Schemas (Gong integer ms, Fireflies float seconds, Intercom `ai_agent` keys, HubSpot strings or `null`), the same schemas the generator uses. A failing record is quarantined with an `audit_event`.
- **Model outputs (stages 2, 3, 5, 7, 8, 10, 11)** into the Pydantic models in `signal_engine/contracts.py` with `extra="forbid"`: architecture section 7 enums, `bucket` from `config/taxonomy.yaml`, severity 1-4, probabilities in [0, 1], quotes 5-60 words.
- **Factory job (stage 10)** against `docs/contracts/factory_job.schema.json`, then a de-identification check fails it if any verified quote (normalised, 5 or more words) or any account or person name from the store appears in its text.
- **On failure:** one retry with the errors appended, then the stage fallback (triage: the one fallback model, then `untriaged`; extraction: reject; brief: evidence-only view, `check_status = failed_checks`). Every failure is an `audit_event`.

### 3.2 Quote verification (stage 3)

The quote must be in **the insight's own snippet text**, never `context_text`, so a verified quote is the customer's own words. Normalisation, both sides: NFKC and case-fold; curly quotes, dashes and non-breaking spaces to plain forms; for Gong and Fireflies only, drop the fillers `um`, `uh`, `er`, `erm`, `ah`; remove punctuation except `£`, `%`, in-word apostrophes and `.` or `,` between digits; collapse whitespace.

| Rule | Detail |
|---|---|
| Exact / normalised | raw quote is a substring of the snippet (`exact`), or after normalisation (`normalised`) |
| Ellipsis | split on `...` or `…`; each fragment of 3 or more words must match, in order |
| FullStory | the "quote" is one line of the deterministic window rendering, e.g. `Claim > Documents: click "Document type" select, rage x5`; exact only |
| No fuzzy matching | synthetic text has no recognition errors, so a fuzzy branch would never run (ADR-005) |
| On failure | one retry ("copy it verbatim"), then `failed`: excluded from clustering and counted |

The matched span is stored, so the board highlights the exact words.

The extraction call also carries the typed `states_product_problem` field (prompt `extract@2`); a `no` is dropped, written as an `extract.dropped` audit event and counted, so `kept for extract = insights + dropped_at_extract + failed` holds on every run. Quote verification is measured on the insights that remain; the ground-truth suites see the effect as fewer noise snippets in clusters.

### 3.3 Account attribution (stages 0 and 4)

No model chooses an account: the connector resolves `raw_record.account_id` and code copies it. Gong: the HubSpot object in `context[].objects`, else `External` email domains. Intercom: `source.author.email`. Fireflies: non-Keelwater `meeting_attendees[].email`. FullStory: the session `userId`. Domains match HubSpot `properties.domain` (lower-case, `www.` stripped); of duplicates, the `customer` record with the latest `hs_lastmodifieddate` wins. A personal email gives `null` and `unresolved`; two customer domains give `null` and `ambiguous`; broker and adjuster domains are ignored. Enrich never fills a `null`. Assertion every run: `insight.account_id == raw_record.account_id`.

### 3.4 Citation integrity (stage 7)

Briefs cite `[i:<insight_id>]`. All must hold:
1. Every cited id exists, is verified and belongs to this opportunity.
2. Every bullet under "Evidence" and "Who is affected", and every sentence with a number, cites.
3. Every number about accounts, mentions, routes, renewals or ARR equals the computed value at the stated precision ("£8.9m" must round from the total); the writer receives these as fields.
4. Text in quotation marks equals, after normalisation, the quote of an insight cited in that sentence.
5. Every customer name belongs to a cited insight's account.
6. Three or more insights means at least three distinct citations, from two routes when the opportunity spans two.

One retry with the failure list; then the board shows the evidence only, naming the failed check.

### 3.5 Score, tag and run integrity

- `score.total` recomputed from stored factors and the hashed `config/ranking.yaml`, to 1e-9; recency and renewal use the manifest `as_of`.
- A `shipped` opportunity scores only post-ship evidence; `on_roadmap` carries roadmap = 0.5.
- Reconciliation: snippets = keep + drop + low_confidence + untriaged; insights = verified + failed.
- Lineage: every `triage`, `insight`, `brief`, `judgement` and `outtake` row has a `call_id` whose `model_call` names it as target.
- The `audit_event` hash chain re-walks unbroken, and the triggers reject a test UPDATE.
- No aws or self-hosted base URL lies outside `config/vpc_endpoints.yaml`.

Any mismatch fails the run.

---

## 4. Ground-truth suites

Answers live only in `data/ground_truth.yaml` (seed 42) and `data/holdout/ground_truth.yaml` (seed 43); the pipeline never reads them.

### 4.1 Matching output to the planted answer

1. **Snippet label:** `signal:<theme>` if a signal-theme mention in the same raw record falls in `[start_ms, end_ms]`; else `noise_theme:<theme>`, `noise`, or `unlabelled` (counted, excluded from triage metrics).
2. **Opportunity label:** the most common theme among its insights; **purity** = that theme's share.
3. **Recovered:** an opportunity carries the label with purity >= 0.6 and at least 50% of the theme's mentions.
4. **Oracle order:** the same ranking code over the true inputs, so ranking errors measure evidence lost upstream, not the weights PMs own.

### 4.2 Seed 42 (`eval --suite ground-truth`)

Below any floor, the suite fails. Gates that could not fail on this data were removed.

| Area | Metric | Target | Floor |
|---|---|---|---|
| Triage | Signal recall: planted signal mentions not dropped ÷ all | >= 0.95 | 0.90 |
| Triage | Noise-drop rate: noise-only snippets dropped ÷ all noise-only | >= 0.75 | 0.60 |
| Triage | Bucket accuracy on signal snippets | >= 0.85 | 0.75 |
| Triage | Noise-audit estimate (§6) beside the exact miss rate | reported | none |
| Extract | Quote verification rate | >= 0.97 | 0.93 |
| Extract | Account attribution, incl. expected `null`s | 1.00 | 1.00 |
| Cluster | Real themes recovered | 6/6 | 6/6 |
| Cluster | Mean purity | >= 0.85 | 0.75 |
| Cluster | Split themes / over-merges (>= 25% thresholds) | 0 / 0 | 1 / 1 |
| Cluster | Contradictory signal: PASS one opportunity, both stances cited; WARN split by stance; FAIL a stance lost | PASS | WARN |
| Tag | Shipped and roadmap themes tagged; no tag on the two hard negatives; both post-ship mentions in post-ship feedback | all | all |
| Rank | Top-6 set equals the six real themes | yes | yes |
| Rank | Adversarial probe (one Strategic renewing account, severity 4, three routes) below all six | yes | yes |
| Rank | Noise-theme opportunities in the top 10 | 0 | 0 |
| Rank | Designed close pairs and Kendall τ against the oracle | reported | none |
| Brief | Citation failures after retry | 0 | 0 |
| Brief | Faithfulness pass rate | reported | gated once the judge is trusted |

### 4.3 Held-out seed 43 (`eval --suite holdout`)

About 40% of the volume, with three themes and one noise theme seed 42 lacks (docs/data.md §6.4). Prompts, taxonomy, thresholds and judges are tuned on seed 42 and frozen before seed 43 runs; both seeds are reported side by side. Floors: signal recall 0.85, quote verification 0.93, attribution 1.00, themes recovered 2/3 (target 3/3), purity 0.75, no noise theme in the top 10; top-3 set reported. A failure blocks the change; the fix is checked on seed 42 only, then seed 43 re-runs once.

### 4.4 Stability replay (`eval --suite stability`)

`run --batch sep` (`as_of` 01/10/2026) into a fresh store, then `run --batch oct` (`as_of` 03/11/2026) appended. Every real theme has at least three mentions in each month. It passes when every planted-theme opportunity after September keeps its id, no planted theme forks across two opportunities each holding >= 25% of it, and September memberships only grow.

### 4.5 What the suites do not prove

Real-world accuracy: counts are small, synthetic customers are tidy, and one author wrote generator and pipeline (seed 43 and the taxonomy leak scan limit that). Blind PM labels and the noise audit measure the real thing.

---

## 5. LLM judges

### 5.1 Three binary judges

Code already catches invented quotes, wrong accounts and score errors. Cluster coherence is designed but not built in v1: seed 42 purity and over-merge metrics cover it in the demo, and `mixed_problems` rejections are stored for it.

| Judge | Runs on | Question (pass = yes) | Typical fail | Evidence seen |
|---|---|---|---|---|
| `signal` | the opportunity behind each brief | Is this a problem with Keelwater's product a squad could act on? | price haggling; customer's own IT outage; how-to; praise | title, problem statement, up to 12 quotes with route and date |
| `faithfulness` | each brief | Is every claim supported by the cited evidence and fact sheet, nothing overstated, no cited contrary evidence omitted? | "all motor customers"; ARR rounded up; conflict as consensus | brief, cited insights, fact sheet (accounts, ARR, mentions, routes, renewals) |
| `duplicate` | each brief **and** every tagged opportunity | Is the core problem still open, not solved by a shipped story or covered by a roadmap item? | re-proposing bulk upload; hiding misfiling as shipped | statement; top 5 stories and roadmap pages by similarity, with status and dates |

`duplicate` runs on tagged items because a real opportunity wrongly tagged shipped gets no brief; its disagreement goes to a PM queue and never removes the tag.

### 5.2 Prompt outline

```text
<role>
You check one property ({judge}) of a product-feedback opportunity for Keelwater, a claims-handling software company. You do not rewrite anything.
</role>
<definition>
{Pass and fail definitions, 5-8 lines, from the rubric notes below.}
</definition>
<evidence>
{The judge-specific inputs from section 5.1, as JSON.}
</evidence>
<task>
Write a critique of 2-5 sentences naming the claim, quote or item you checked and what you found. Then give the verdict. If any single item fails, the verdict is fail.
</task>
<output>
JSON only: {"critique": string, "verdict": "pass" | "fail"}
</output>
```

No few-shot examples in v1, so labels never change a prompt behind its version. Temperature 0, JSON-schema output, critique before verdict; judges see what the brief writer saw, never ground truth. Rubric notes:
- **signal:** fail if the cause is outside the product (pricing, contracts, the customer's IT, staffing), a help article answered it, or it is praise; a feature request or described workaround is signal.
- **faithfulness:** fail on an uncited claim, a number off the fact sheet, scope wider than the cited accounts, a paraphrase in quotation marks, or an ignored contrary citation.
- **duplicate:** compare the problem, not the area; an unstarted or in-progress spike is not shipped.

### 5.3 Judge model

Demo `z-ai/glm-5.3` (reasoning always on, effort low; fallback `deepseek/deepseek-v4.1-flash`), aws `global.zai.glm-5.3` (global routing cannot guarantee UK data residency). The brief and handoff writer is Qwen3.8 Max, the extractor Qwen3.8 Flash and the data generator Qwen3 VL 235B Instruct, so no judge grades its own family's text. The DeepSeek fallback is used for both writing and judging, so a brief written by DeepSeek is never graded by the DeepSeek judge: that judgement is stored as `not_independent`, shown, and excluded from pass counts. About 33 calls a run; the price is the live-run figure in the README, not an estimate here.

### 5.4 From board actions to labels

Each label is a `label` row (judge, target, verdict, critique, origin, blind, split, weight, actor) plus an audit event. Reason codes are the architecture section 7 enum.

| Action | Label | Blind? |
|---|---|---|
| Accept | `signal` pass, `duplicate` pass | no |
| Reject `not_product_signal` | `signal` fail | no |
| Reject `already_shipped` / `already_on_roadmap` (reference required) | `duplicate` fail | no |
| Reject `evidence_wrong` (note required) | `faithfulness` fail | no |
| Reject `mixed_problems` | none in v1 | n/a |
| Reject `low_value` / `other`; park; reassign; merge; split | none (ranking and clustering feedback) | n/a |
| Edit brief, "was the original wrong?" yes | `faithfulness` fail, diff kept | no |
| Label panel | pass or fail per applicable judge | **yes**: verdict and critique hidden until saved |

Non-blind labels are anchored on a visible verdict: dev only, never certification. Faithfulness passes come only from the label panel. When two PMs disagree, both labels stay and the item leaves certification until settled; PM-to-PM agreement is reported as the ceiling for any judge.

### 5.5 Splits

Per opportunity, once: `sha256(opportunity_id) mod 100`, 0-29 `dev`, 30-99 `held_out`. A judge is never certified on an item it was iterated on. Held-out is scored once per candidate version (`eval --suite judges --qualify`).

### 5.6 Certification and revocation

Trust belongs to one judge version (`<judge>@<prompt version>+<model id>`) and needs both:
1. at least 50 blind `real_pm` labels per class (human pass, human fail) in `held_out`;
2. a Wilson 95% lower bound of at least 0.75 on TPR and on TNR. The target point estimate is 0.90; with 50 per class the bound needs 44 of 50 (44/50 gives 0.76, 43/50 gives 0.74).

TPR is the share of human passes the judge passes, TNR the share of human fails it fails; both are always shown, because an always-pass judge scores 95% agreement when 5% of briefs are bad. The weekly label-panel sample is stratified by judge verdict so fails are not starved; each label stores its inclusion weight, rates are weighted, and the Wilson bound uses the effective sample size.

**Revocation:** on the latest 50 blind held-out labels per class, trust goes when the Wilson 95% *upper* bound of TPR or TNR falls below 0.75, which does not flap on one bad week. Any prompt or model change creates a new version in `uncalibrated` that re-qualifies on existing labels with one `--qualify` run; the move from demo to aws profile is such a change (architecture N3). Grants and revocations are audit events.

### 5.7 What the board shows

| State | On each brief | PM behaviour |
|---|---|---|
| `uncalibrated` | verdict marked "not yet calibrated", critique on expand | reviews every brief |
| `calibrating` | "calibrating: n of 50 per class" beside each verdict | reviews every brief |
| `trusted` | "checked" or "needs attention" per judge | failing briefs move to a needs-attention lane |
| `revoked` | "trust revoked dd/mm/yyyy: reason" | reviews every brief |

Deterministic failures are named, not badged. Judges never accept, reject or hide anything.

---

## 6. Noise audit

A fixed, stratified sample of **40** dropped items a week, whatever the volume, so PM effort stays flat at 10x or 100x: 25 with 0.05 < p <= 0.10 (near the threshold, where misses concentrate) and 15 with p <= 0.05. A PM marks each noise or real signal in the Monday session. `audit_weight` = stratum size ÷ items sampled from it, and the miss rate is the weighted share marked real signal. In the demo, ground truth plays the reviewer over the replay's drops, and the estimate is shown beside the exact miss rate.

---

## 7. Labels in the demo

No Keelwater PMs, so no judge in the demo can be trusted.

| Origin | What it is | Used for | Certifies? |
|---|---|---|---|
| (ground truth) | seeds 42 and 43 | §4 suites | no |
| `synthetic_seed` | 60 constructed items per judge (`labels seed --n 60`) | iterating prompts on dev; showing the machinery | never |
| `live_reviewer` | labels a reviewer adds in the board | showing labels flow | never |
| `real_pm` | Keelwater PMs in production, label panel | certification | yes, when blind |

Seed sets, all built by construction from ground truth (none is hand-labelled), split by theme so no theme is in two splits:
- **signal:** 30 passes from bundles of 3-8 signal-theme insights; 30 fails from noise themes and noise-only snippets.
- **duplicate:** 30 fails pair shipped and roadmap themes with their items; 30 passes include the hard negatives.
- **faithfulness:** 30 passes by construction: briefs from the real brief prompt over seeded bundles of planted opportunities that clear every deterministic check, marked `synthetic_seed` and not read or labelled by the author; 30 fails each apply one controlled defect (unsupported claim, changed number, misattributed quote, flipped stance, inflated scope, removed contrary evidence), applied by the Qwen generator with the span recorded. Constructed defects are cleaner than real ones.

Synthetic or not: §4 metrics and the noise-audit rate are synthetic; `synthetic_seed` agreement is synthetic; `live_reviewer` agreement is real clicks on synthetic data (tiny n, with intervals); "calibrating: n of 50" shows 0 in the demo; acceptance rate is real clicks, nothing pre-seeded; cost, latency and tokens are real `model_call` rows from the recorded live run.

---

## 8. Drift watch and change control

### 8.1 Three drift metrics

The Monday label panel takes 20 judged items (stratified by verdict; topped up from ranks 11-30 on `signal` and `duplicate`) plus the 40 audit items: about 45 minutes for one PM, rotating.

| Metric | Window | Healthy | Warn | Alert and action |
|---|---|---|---|---|
| Label-panel agreement (weighted TPR, TNR per judge) | weekly, and latest 50 per class | >= 0.90 | < 0.85 | revocation rule (§5.6) |
| Noise-audit miss rate | weekly | <= 3% | > 5% | > 10%: tighten the drop threshold to p <= 0.05 and run the triage suite |
| PM acceptance rate, top 10 | rolling 4 weeks | >= 50% | < 40% | < 30%: taxonomy and ranking review with PMs |

Rubrics are revisited monthly against fail critiques, because grading shifts what reviewers think the criteria are (the EvalGen finding).

### 8.2 Change control

- **Versioning:** prompts in `prompts/<stage>/<name>.md` with a front-matter `version`; `prompt_version = <name>@<semver>+<first 8 hex of sha256>`; a live run refuses a changed hash without a bump. Model ids pinned in `config/models.yaml`; config changes are audit events.
- **Suites:** a change runs `eval --suite all` (seed 42, seed 43, stability, judges on dev), re-running from the first changed stage with earlier stages cached. Reports go to `reports/eval/<suite>-<run_id>.json` and are compared with `reports/eval/baseline/`, which moves only with a merged passing change.
- **Gates:** boolean gates (recovery, top-6 set, probe, tagging, attribution, citations, noise suppression, stability) allow no drop; noise-drop rate and purity at least baseline - 0.02 and the floor; signal recall at most one more mention missed; judge dev agreement at least baseline - 0.02; +25% cost or +50% latency needs a written reason.
- **Designed, not built in v1:** Phoenix datasets and experiments showing baseline and candidate side by side (v1 only mirrors spans with `--phoenix`); and a triage backend swap between two in-VPC backends (self-hosted Clef now, a ModernBERT/SetFit classifier later): offline comparison on 500 or more labelled snippets, thresholds re-fitted to equal signal recall, two weeks in shadow, one week as a 10% canary with the audit raised on that slice, cut-over and rollback by configuration. Gate: recall at least the incumbent's, noise-drop within 5 points, bucket accuracy within 3, p95 latency under 1.5 s. The demo runs Clef through OpenRouter, which is not in this path.

---

## 9. What reviewers can verify themselves

All four run in replay with no keys, under two minutes each, exit 0 when every floor holds, and write a report under `reports/eval/`.

```text
keelwater eval --suite ground-truth
keelwater eval --suite holdout
keelwater eval --suite stability
keelwater eval --suite judges
```

Expected shape (placeholders):

```text
$ keelwater eval --suite ground-truth
run <run_id>  profile=replay  seed=42  as_of=03/11/2026  data=sha256:<hash>
leak check     PASS  0 theme ids or fact phrases in data/raw, prompts/ or config/
deterministic  PASS  schema 0 | quotes n/N | citations 0 | accounts 0 | scores 0 | audit chain ok
triage   recall 0.xx | noise-drop 0.xx | bucket 0.xx | audit est 0.xx vs exact 0.xx
cluster  recovered n/6 | purity 0.xx | split n | over-merged n | contradictory PASS
tag      shipped ok | roadmap ok | hard negatives 0 | post-ship n/2
rank     top-6 set yes | probe below six yes | noise in top 10 0 | tau 0.xx
overall  PASS   report: reports/eval/ground-truth-<run_id>.json

$ keelwater eval --suite judges
judge         origin          dev TPR  dev TNR  held-out TPR/TNR (95% CI)  state
signal        synthetic_seed  0.xx     0.xx     -                          (never certifies)
signal        real_pm         -        -        -                          calibrating: 0 of 50 per class
```

Worth trying: reject a brief with `evidence_wrong`, label five briefs blind, and re-run the judges suite to see the `live_reviewer` row change; or read any critique, which names the claim it checked.

---

## 10. Known limits

- **Small numbers:** six planted themes on seed 42, three on seed 43; the demo shows the mechanism, not high accuracy.
- **Label budget:** 50 blind PM labels per class per judge is more than the day-30 session gives, especially fails; the weekly label panel closes the gap over weeks (INFERRED), and until then judges show "calibrating".
- **Implicit labels are selective and anchored,** so they never certify.
- **Ranking sensitivity:** a single strategic, renewing account with all-recent evidence would score about 14.6 on seed 42 and enter the top six; the board shows breadth as its own factor.
- **Rubrics drift;** monthly review and versioned prompts keep it visible.
