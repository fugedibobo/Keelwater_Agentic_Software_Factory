# Signal Board: specification

Status: planned, build day 03/11/2026. Author: Andras Fugedi. Consistent with docs/architecture.md (tables are from its section 7; stage numbers from its section 4). Reason codes and judge names match docs/evals.md.

## 1. Purpose and constraints

The Signal Board is the page a PM opens each week. It has two groups of tabs:

- **PM workspace:** Opportunities (with a "since last week" strip and the weekly label panel) and Handoffs. This is where a PM reviews, decides and labels. Target: a PM reviews the top 10 in 30 minutes.
- **Ops console:** Pipeline, Evals, Audit and How it works. This is where product ops, and any sceptical reader, checks what the run did and how far its output can be trusted.

Every action writes an `annotation` row and an `audit_event` row. Actions feed acceptance rates and ranking feedback; only labels from the blind label panel (given without seeing the judge verdict) count towards certifying a judge (evals.md).

| Constraint | Consequence |
|---|---|
| Built in a few hours by a coding agent | One FastAPI app, Jinja templates, about 200 lines of vanilla JS. No build step, no React, no npm. |
| Must open with a double-click | The same templates render a static snapshot to `site/index.html` (`keelwater render static`). Data is inlined as JSON in the page. |
| Static mode must be honest | Actions are disabled and a banner reads: "Static snapshot of run {run_id}, {date}. Actions are disabled. Run the local server to review." |
| Styled with impeccable on the build laptop | One `board.css` with design tokens. impeccable `critique`, `typeset`, `colorize`, `layout` and `polish` run on the Opportunities tab first and on other tabs if time allows, then `npx impeccable detect site/index.html`. |
| Demo data is synthetic | A footer line says so on every tab. |

Layout rule: one template per tab (`templates/{opportunities,handoffs,pipeline,evals,audit,how}.html`) extending `base.html`. A `static` flag in the template context switches the action buttons to disabled and reads data from inlined JSON instead of `fetch()`.

## 2. Shell

```
+--------------------------------------------------------------+
| Signal Board  run 03/11/2026 02:00 (replay)                  |
| Judges: 0 of 3 trusted (calibrating)                         |
| [Banner in static mode: actions disabled]                    |
+--------------------------------------------------------------+
| 0 About this board                                           |
| PM workspace: 1 Opportunities | 2 Handoffs                   |
| Ops console: 3 Pipeline | 4 Evals | 5 Audit | 6 How it works |
+--------------------------------------------------------------+
| (tab content)                                                |
+--------------------------------------------------------------+
| Synthetic data. Keelwater is fictional.                      |
+--------------------------------------------------------------+
```

The board opens on tab 0, About this board: what the board is, what is real and what is simulated, the five steps from feedback to opportunity, what each tab is for and where to start (about 250 words, plain English). Every score on Opportunities and every metric, column header and gate on Evals has an "i" marker that shows a one- or two-sentence definition on hover and keyboard focus; the text lives in `signal_engine/board/metric_help.yaml` (sourced from docs/evals.md, floors added from the code that gates the suites), and a test fails if a metric shown has no entry. Dark is the default theme; a header toggle switches to light and the choice is remembered in `localStorage` (guarded, so the board works without storage).

The judge status in the header comes from the `judge_version` rows (tab 4) and links there. Tabs are real links (`/#opportunities` etc.) so they work with JavaScript off in static mode. The board opens on Opportunities.

## 3. Tab 1: Opportunities (PM workspace)

Purpose: the weekly review. A PM reads what changed, scans the ranked list, opens one, checks the evidence, decides, then clears the week's labels.

```
+--------------------------------------------------------------+
| Since last week: 3 new | 2 up, 1 down | 2 post-ship feedback |
|                  4 decided by other PMs                      |
+--------------------------------------------------------------+
| Filter: bucket [all v]  status [proposed v]  squad [mine v]  |
+--------------------------------------------------------------+
| #1 Bulk reassignment of claims         score 7.4   ^ +2      |
|    [breadth 2.3][sev 3.1][value 1.4][corr 1.5][rec 0.9]      |
|    Checks: quotes ok  citations ok  numbers ok               |
|    Judges: calibrating (faithfulness 23/50 pass, 8/50 fail)  |
|    6 accounts  GBP 1.9m ARR  2 renew <90d                    |
| #2 Audit-trail export is slow          score 6.1   = 0       |
|    Checks: FAILED number check (ARR in brief != store)       |
| #3 Payment-approval confusion          score 5.8   v -1      |
+--------------------------------------------------------------+
| This week's labels: 14 left (6 briefs, 8 noise)  [Open]      |
+--------------------------------------------------------------+
| a accept  m merge  r reject  p park  s squad  e edit  u undo |
+--------------------------------------------------------------+
```

Drill-down (opens as a side panel, `Esc` closes):

```
+--------------------------------------------------------------+
| Bulk reassignment of claims                                  |
| Checks: quotes ok  citations ok  numbers ok                  |
| Judges: signal fail, duplicate pass, faithfulness pass       |
|         (all calibrating: see Evals)                         |
| Brief (cited): "Handlers reassign claims one by one [i14]..."|
+--------------------------------------------------------------+
| Evidence                                                     |
| "I have to do forty of these by hand" - Gong call, 14:32     |
| "can't move a batch of claims" - Intercom conv 88213         |
| "...it takes ages to reassign" - Fireflies, sentence 212     |
| Rage clicks on Reassign - FullStory window 00:41-01:03       |
+--------------------------------------------------------------+
| Accounts: Pendleford Motor Mutual GBP 690k renews 28/02/2027 |
| Unresolved: 2 insights with no account (breadth counts 0)    |
| [Accept] [Merge into...] [Reject v reason] [Park]            |
| [Send to squad v] [Edit]                                     |
+--------------------------------------------------------------+
```

| Item | Detail |
|---|---|
| Data source | `opportunity`, `score` (latest and previous run), `opportunity_insight`, `insight`, `snippet`, `raw_record` (source, source_id, start_ms), `account`, `brief`, `judgement`, `judge_version`, `annotation` |
| Since last week | One strip above the list, from two `score` snapshots and the `annotation` and `audit_event` rows since the previous run: new opportunities, rank movers (up or down by 2 or more), post-ship feedback on shipped opportunities, and decisions other PMs made. Each count filters the list. |
| Score chips | One chip per factor from `score`: breadth, severity, value, corroboration, recency. Modifiers show as extra chips: renewal (x(1 + 0.25 x renewing share of affected ARR)) and on roadmap (x0.5). Hover or focus shows the formula line. |
| Trend | Rank and score change versus the previous run, from two `score` rows: arrow, delta, and "new" when `first_seen_as_of` equals this run's `as_of`. |
| Check line | Replaces a blanket badge. Deterministic checks (quote match, citation integrity, numbers against the store) show "ok" or "FAILED" with the check's name and the mismatch. Each judge shows its verdict (pass or fail) and its status: "calibrating: n of 50 per class" until it is certified, then "trusted". A brief with a failed deterministic check stays collapsed behind the failure until the PM opens it. |
| Evidence links | Gong: call id plus `start_ms` formatted mm:ss. Intercom: conversation id. Fireflies: transcript id plus sentence index. FullStory: session id plus window start and end. In the demo the links point to a local `/raw/{raw_id}` view of the synthetic record; in production they would be deep links built from `source_id`. |
| Quote check | Each quote shows a tick when the quote check matched (exact or normalised, with the matched span). Unmatched quotes never reach the page (stage 3 rejects them). The preceding internal turn kept as context is never shown as a quote. |
| Accounts | Table of affected accounts: name, ARR (GBP), tier, renewal date, number of supporting insights. Missing HubSpot data shows "not in HubSpot", never a guess. Insights with no resolvable account are listed separately and count as zero accounts towards breadth. |
| Actions | Accept, merge (pick a target opportunity), reject (reason code required), park ("needs more evidence", optional note), send to another squad (target squad required), edit (title and problem statement inline), and confirm or remove a proposed shipped or on-roadmap tag. Split is designed but not built in v1. |
| Accept confirmation | Accept opens a dialog: "Accept and draft the intent document?" with the opportunity title and evidence count. Only Confirm sends the request. |
| Undo | Every action shows a toast with Undo for 10 seconds (`u` or the button). Undo writes a reversing `annotation` and `audit_event` and restores the previous status and squad; nothing is deleted, because the audit table is append-only. Intent drafting after an accept starts only when the undo window closes. |
| Reason codes | The architecture section 7 enum, as in evals.md 5.4: `not_product_signal`, `already_shipped` (reference required), `already_on_roadmap` (reference required), `evidence_wrong` (note required), `mixed_problems`, `low_value`, `other` (note required). |
| Weekly labels | The label panel opens as a side panel: a blind sample of briefs, each judged by the PM per judge with the judge verdict hidden, then the week's noise-audit items (tab 4). Labels write `label` rows (blind; origin `real_pm` in production, `live_reviewer` in the demo). |
| Keyboard | `j`/`k` move, `Enter` open, `Esc` close, `a` accept (then `Enter` to confirm), `m` merge, `r` reject, `p` park, `s` send to squad, `e` edit, `u` undo, `l` open labels, `?` shortcut list. Shortcuts are ignored while a text field has focus. |

## 4. Tab 2: Handoffs (PM workspace)

Purpose: show the contract with the platform team in action, and the right-of-build drafts.

```
+--------------------------------------------------------------+
| Accepted opportunities                                       |
| > Bulk reassignment of claims       intent_drafted           |
+--------------------------------------------------------------+
| Intent document (preview)     | Factory job (JSON, v1)       |
| # Intent: bulk reassignment   | { "schema_version": "1",     |
| Problem / Users / Outcome     |   "idempotency_key": "...",  |
| Acceptance criteria / Risks   |   "evidence_snapshot_ids":   |
|                               |     [...],                   |
|                               |   "problem_statement": "..." |
|                               |   ... }                      |
|                               | schema: VALID  [Copy]        |
+--------------------------------------------------------------+
| Outtake drafts: release note | help article | change notice  |
| | post-call follow-up brief         [Accept] [Reject]        |
+--------------------------------------------------------------+
```

| Item | Detail |
|---|---|
| Data source | `handoff` (intent_doc_md, factory_job_json, status), `outtake` (kind, body_md, status, story_ref), `opportunity` |
| Intent document | Rendered Markdown from `intent_doc_md`. Quotes and account names appear here because this page runs inside the VPC. |
| Factory job | `factory_job_json` pretty-printed, with a validity line from validating it against `docs/contracts/factory_job.schema.json` (v1). The job carries evidence snapshot ids, the run manifest hash and a de-identified problem statement, with users affected by tier and role, never by name. An invalid job shows the validation errors and cannot be marked ready. A job the factory rejects shows its reason. |
| Outtake drafts | Four kinds: release note, help article, customer change notice, post-call follow-up brief. Each has accept and reject, writes an `annotation`, and moves `outtake.status`. Accepted means approved by a human, not sent: nothing leaves the demo. |
| Interactions | Copy JSON, copy Markdown, accept or reject a draft with a reason. |

## 5. Tab 3: Pipeline (ops console)

Purpose: show what the last run did to the data, what it cost, and let a sceptic verify that nothing was silently dropped.

```
+--------------------------------------------------------------+
| Run 03/11/2026 02:00  replay  data a41f  config 9c2e         |
+--------------------------------------------------------------+
| Source      raw  snip  kept  insights  opps  briefs          |
| gong         40   312    71        64                        |
| intercom    220   410   118       103                        |
| fireflies    60   388    90        81                        |
| fullstory   150   150    44        39                        |
| TOTAL       470  1260   323       287    19     10           |
+--------------------------------------------------------------+
| Stage     model            p50 ms  tok in/out    cost USD    |
| triage    cloudflare/clef     210  -             0.01        |
| Run spend USD 0.00 of cap 1.50                               |
+--------------------------------------------------------------+
```

(Figures above are illustrative layout only; the page shows the real run.)

| Item | Detail |
|---|---|
| Data source | `run`, `raw_record`, `snippet`, `triage`, `insight` (verified), `opportunity`, `brief`, `model_call` |
| Funnel | One row per source: raw records, snippets, kept by triage, insights verified, opportunities touched, briefs. Each count links to the filtered Audit tab. Dropped counts are shown, not hidden. |
| Per-stage table | Stage, model, profile, calls, p50 and p95 latency, tokens in and out, cost in USD, cached share, and run spend against the run's USD cap. From `model_call` grouped by stage. |
| Decision-model split | Triage `backend` counts: decision model, cheap-LLM fallback, `low_confidence`, `untriaged`. A high fallback share is flagged. |
| Run manifest | `data_hash`, `config_hash`, `prompt_versions`, model ids, profile, seed, batch, `as_of`, status, with a copy button. This is the replay key (N1). |
| Interactions | Click a funnel cell to jump to Audit with the filter set. Toggle between counts and percentages. |

## 6. Tab 4: Evals (ops console)

Purpose: answer "how do you know it is right?" on one page.

```
+--------------------------------------------------------------+
| Ground truth        seed 42 (main)     seed 43 (held out)    |
| Theme recall        6/6                3/3                   |
| Exact top-6 set     yes                n/a                   |
| Loud-narrow probe   rank 8 (below all six)                   |
| Two-batch replay    ids stable, no theme forked              |
+--------------------------------------------------------------+
| Judge         pass labels  fail labels  TPR  TNR  status     |
| faithfulness  23/50        8/50         -    -    calibrating|
| signal        31/50        12/50        -    -    calibrating|
| duplicate     19/50        5/50         -    -    calibrating|
+--------------------------------------------------------------+
| Noise audit: 40 sampled this week, est. miss rate 4% [labels]|
| Label-panel agreement 81%   PM acceptance 62%   [sparklines] |
+--------------------------------------------------------------+
```

(Figures are layout illustration, not results.)

| Item | Detail |
|---|---|
| Data source | the newest `reports/eval/<suite>-*.json` (ground truth for seed 42, held-out seed 43, stability, judges), `judgement`, `judge_version`, `label` (PM labels), `triage` (dropped items sampled for audit), `opportunity` status, `score` |
| Ground truth | Theme recall and the rank of each planted theme on both seeds; the exact top-6 set on seed 42; the adversarial loud-narrow probe's rank (it must sit below all six); the two-batch replay result; designed close pairs as reported values. Shipped and on-roadmap themes must not appear as new proposals. |
| Judges | The three judges (faithfulness, signal, duplicate). For each: blind label counts per class against 50, then TPR, TNR and their Wilson 95% lower bounds once both classes reach 50. A judge is trusted when both lower bounds are at least 0.75 (target point estimate 0.90). Until then the status reads "calibrating: n of 50 per class". Grants and revocations are audit events. |
| Noise audit | A fixed weekly stratified sample of 40 dropped items, weighted towards triage scores between 0.05 and 0.10. The PM labels each "noise" or "missed signal" in the label panel; the miss rate is re-weighted to the full drop population. |
| Drift (v1) | Three lines across runs: weekly label-panel agreement, noise-audit miss rate, PM acceptance rate (share of proposed opportunities accepted or merged). Each is a small SVG line, pre-rendered in static mode. Below its floor, the line takes the warning style and a text alert appears. |
| Interactions | Click a judge to see its disagreements with PM labels (briefs listed, with the judge critique beside the PM label). Non-blind labels from rejections appear here for review but are marked and excluded from the counts. |

## 7. Tab 5: Audit (ops console)

Purpose: prove every model call and human decision is on record.

```
+--------------------------------------------------------------+
| Filter: [model_call|audit_event]  stage [all]  actor [all]   |
| from [   ] to [   ]  run [latest]   [Open Phoenix trace]     |
| Hash chain: verified to event 1,284                          |
+--------------------------------------------------------------+
| 02:03:11 triage cloudflare/clef in a1f3 out 77c2 210ms $0.00  |
| 02:03:12 extract  qwen3.8-... in 19bd out e0a4  640ms $0.00  |
| 09:12:40 audit_event  priya.n  opportunity#7 reject low_value|
| 09:12:44 audit_event  priya.n  opportunity#7 undo            |
+--------------------------------------------------------------+
```

| Item | Detail |
|---|---|
| Data source | `model_call`, `audit_event`, `run` |
| Filters | Table (model_call or audit_event), run, stage, model, actor, date range, cached only. Server-side with query parameters; in static mode the filters run over the inlined rows. |
| Row detail | Expands to hashes, prompt version, tokens, cost, target (`target_type`, `target_id`), and `details_json`. |
| Hash chain | `audit_event` is append-only and hash-chained (`prev_hash`, `hash`). The page re-computes the chain and shows the last verified event, or the first break. Config changes (ranking weights, thresholds, taxonomy) and judge trust grants appear as events. |
| Phoenix link | Shown only when `PHOENIX_URL` is set and reachable; otherwise a disabled link reads "Phoenix not running". Phoenix is the trace viewer; these two tables are the source of truth (ADR-010). |
| Limits | Paged at 100 rows; export to CSV. |

## 8. Tab 6: How it works (ops console)

Purpose: let a reader who has never seen the repo understand the system in two minutes.

```
+--------------------------------------------------------------+
| [ Architecture diagram (Archify HTML, in an iframe) ]        |
| [ PDLC diagram (Archify HTML, in an iframe)         ]        |
+--------------------------------------------------------------+
| 1 Collect  2 Clean  3 Judge relevance  4 Extract + check     |
| 5 Group + rank  6 Brief + review                             |
+--------------------------------------------------------------+
```

| Item | Detail |
|---|---|
| Data source | Static files `docs/diagrams/production-architecture.html` and `docs/diagrams/agentic-pdlc.html`, copied into `site/diagrams/` by the render command. No tables. |
| Embedding | `<iframe>` with a fixed height and an "open full size" link. Archify output is self-contained, so it works from `file://`. |
| Walkthrough | Six plain-English steps: (1) every night Keelwater's feedback is collected from calls, tickets and sessions; (2) what customers said is kept, with the line before it as context that is never quoted, and idle session time is cut; (3) a small fast model decides what is product signal and what is noise, and a person checks a weekly sample of 40 dropped items; (4) a model pulls out the problem and the customer's exact words, and code checks the words really appear in the source; (5) similar problems are grouped, matched to the roadmap and ranked with a formula the PM can read; (6) the top ones get a cited brief, three judges from another model family check it, and a PM accepts, merges, rejects, parks or sends it to another squad. |

## 9. API

FastAPI, JSON, local only. Reads are `GET`; every `POST` writes one `annotation` row (a `label` row for labels) and one `audit_event` row in a single transaction. Request bodies are Pydantic models from `contracts.py`. The static renderer calls the same read functions directly (no HTTP).

| Method and path | Purpose | Writes |
|---|---|---|
| `GET /api/runs/latest` | run row, manifest, status | none |
| `GET /api/since-last-week` | new, movers, post-ship feedback, other PMs' decisions | none |
| `GET /api/opportunities?status=&bucket=&squad=` | ranked list with score factors, trend and check line | none |
| `GET /api/opportunities/{id}` | brief, evidence, accounts, checks, judgements | none |
| `POST /api/opportunities/{id}/accept` body `{confirmed: true}` | accept; handoff drafting starts after the undo window | annotation(accept), audit_event, status to `accepted` |
| `POST /api/opportunities/{id}/merge` body `{target_id}` | merge into another opportunity | annotation(merge), audit_event, status to `merged` |
| `POST /api/opportunities/{id}/reject` body `{reason_code, note}` | reject with reason | annotation(reject), audit_event, status to `rejected` |
| `POST /api/opportunities/{id}/park` body `{note}` | park as "needs more evidence" | annotation(park), audit_event, status to `parked` |
| `POST /api/opportunities/{id}/reassign` body `{squad}` | send to another squad | annotation(reassign), audit_event, squad changed |
| `POST /api/opportunities/{id}/edit` body `{title, problem_statement}` | edit text | annotation(edit), audit_event |
| `POST /api/opportunities/{id}/confirm_tag` | confirm the proposed shipped or on-roadmap tag | annotation(confirm_tag), audit_event, `tag_state` to `confirmed` |
| `POST /api/opportunities/{id}/remove_tag` body `{note}` | remove the proposed tag | annotation(remove_tag), audit_event, `tag_state` to `removed` |
| `POST /api/opportunities/{id}/split` body `{insight_ids}` | move the listed insights into a new opportunity (designed, not built in v1) | annotation(split), audit_event |
| `POST /api/undo` body `{audit_event_id}` | reverse an action within 10 seconds | annotation(undo), audit_event, previous status and squad restored |
| `GET /api/labels/queue` | this week's blind brief sample and noise-audit items | none |
| `POST /api/labels` body `{target_type, target_id, judge, verdict, critique}` | PM label on a brief or noise-audit item | label, audit_event |
| `GET /api/pipeline` | funnel, per-stage cost and latency, manifest | none |
| `GET /api/evals` | ground truth for both seeds, judge counts and status, noise audit, drift | none |
| `GET /api/handoffs` | intent docs and factory jobs with validity | none |
| `GET /api/outtakes?kind=` | drafts | none |
| `POST /api/outtakes/{id}/accept` and `/reject` | decide a draft | annotation, audit_event, `outtake.status` |
| `GET /api/audit?table=&stage=&actor=&from=&to=&page=` | log rows and hash-chain status | none |

How an action writes records (example: reject):

1. The server checks the current status allows the move (state machine in architecture section 7). An agent may not pass a human gate; the actor must be a person, taken from an `X-Actor` header in the demo and from SSO claims in production.
2. In one transaction it inserts `annotation(target_type='opportunity', target_id, actor, action='reject', reason_code, created_at)`, updates `opportunity.status`, and appends `audit_event(at, actor, action='opportunity.reject', target, details_json={reason_code, note, run_id}, prev_hash, hash)`.
3. The response returns the updated row and the `audit_event_id`, so the page re-renders without a reload and the undo toast can reverse it.
4. A rejection with `evidence_wrong` is stored as a faithfulness fail label marked non-blind. It shows in the judge's disagreement review, but only blind label-panel labels count towards certification (evals.md).

## 10. Accessibility basics

- Everything reachable and operable by keyboard; visible focus ring on every control; no keyboard traps outside the accept dialog, which holds focus until Confirm, Cancel or `Esc` and then returns it to the row.
- Contrast at least 4.5:1 for text and 3:1 for chips and borders, checked in light and dark (dark by default, light by the header toggle; `tests/test_board_help.py` computes the ratios from the stylesheet tokens).
- Status is never colour alone: check lines and badges carry words (ok, FAILED, calibrating, VALID), and trend arrows carry signs and numbers.
- Semantic landmarks (`header`, `nav`, `main`); each tab group is a labelled `role="tablist"`; tables have header cells; `aria-live="polite"` on the action result and undo toast.
- The undo toast stays for 10 seconds and does not steal focus; `u` works anywhere outside a text field.
- Respect `prefers-reduced-motion`; no auto-playing animation on the board itself.
- Minimum 16px body text; layout holds at 320px width without horizontal scroll.

## 11. How it would look in production

Not built. The same templates and API, with these changes:

| Area | Change |
|---|---|
| Identity | Company SSO (SAML or OIDC) in front of the app; actor comes from the token. |
| Views | Per-squad default view (buckets mapped to squads); a PM sees all but starts on their own. The ops console is limited to product ops. |
| Digest | The "since last week" strip also goes out as a weekly Slack and Notion digest, linking back to the board. |
| Data | Postgres replaces SQLite; evidence links become deep links into Gong, Intercom, Fireflies and FullStory. |
| Hosting | Runs in the same AWS VPC as the pipeline, behind an internal load balancer. |
| Write-back | Accepted opportunities create a Notion page and a Shortcut epic (out of scope for the demo). |

## 12. Build order for the coding agent

1. Read functions and Pydantic response models over the SQLite store.
2. `base.html` with both tab groups, then the Opportunities tab: since-last-week strip, list with check lines, drill-down, then the action `POST`s with accept confirmation and undo.
3. Label panel, then the Handoffs, Pipeline, Evals and Audit tabs (read-only apart from labels and outtake decisions).
4. How it works tab; `keelwater render static`; banner.
5. impeccable pass on the Opportunities tab; keyboard and contrast checks; `npx impeccable detect site/index.html`.

If time runs out: cut order is Audit filters, then drift lines, then the drill-down side panel (keep a plain page). Opportunities with its check line, the Pipeline funnel, the action writes, accept confirmation and undo are not cut.
