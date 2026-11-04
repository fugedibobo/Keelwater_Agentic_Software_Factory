# Synthetic data: specification and generator

Andras Fugedi, 03/11/2026, revised after review round 1. Status: design for the demo build. Implements assumption A3 and the planted ground truth in section 6 of docs/architecture.md; commands follow its section 11.

**Summary.** All demo data is invented: 30 fictional insurers and 4 prospects, about 200 records across seven tools in each tool's native export shape. A seeded generator plants a known answer and writes it only to a ground-truth file, so the pipeline can be scored but cannot cheat. Seed 42 is the tuning set; seed 43 is a smaller held-out set with unseen themes, never used for tuning. An LLM writes the words; code builds every id, timestamp, account link and FullStory event. The output is committed.

---

## 1. Why synthetic

No public set is both licence-clean and close to B2B claims software (docs/research/datasets-and-source-schemas.md, 02/11/2026): the best sales-call sets are gated or generic SaaS, the support-ticket sets are non-commercial or consumer retail, no onboarding or account-review corpus exists, and the open clickstream set has no rage, dead or error clicks. The deciding reason is the ground truth: recall and rank of real themes can only be measured if we know what they are. What we copy exactly is each tool's record shape (section 7).

## 2. Assumptions (flagged)

- **D1.** Data window 01/09/2026-31/10/2026; `as_of = 03/11/2026`, so "recent" means dated 04/10/2026 or later and "renews within 90 days" means by 01/02/2027. `run --batch sep` uses `as_of = 01/10/2026`.
- **D2.** Keelwater has about 180 enterprise customers; the demo uses 30 plus 4 prospects. All ARR figures are invented.
- **D3.** Where vendor documentation does not show a field's values or shape, the generator assumes one, marked ASSUMED or INFERRED in section 7.
- **D4.** Every company, person and domain is invented, and every domain ends in `.example`. The generator prompt forbids real company and person names, and a check allows only names from the spec files (section 8.2).
- **D5.** No health data. The insurers write motor, home, commercial and specialty lines only.
- **D6.** `config/teams.yaml` maps Keelwater staff emails to teams; it gives each Fireflies call its route and, with attendee emails, tells internal speakers from customers.

## 3. Keelwater product surface and taxonomy

The triage buckets in `config/taxonomy.yaml` describe product areas in neutral words: no description may contain a planted theme's title or fact phrase (seed 42 or 43), and the leak scan covers this file (section 9).

```yaml
# config/taxonomy.yaml
version: 2
buckets:
  - id: fnol_intake
    name: First notice of loss and intake
    description: Recording a new claim and the first details about the loss.
  - id: triage_assignment
    name: Triage, assignment and fraud referral
    description: Deciding who handles a claim and how it is prioritised, including referral for fraud review.
  - id: documents_evidence
    name: Documents and evidence
    description: Files and other evidence held on a claim, and how handlers find and manage them.
  - id: reserves_payments
    name: Reserves and payments
    description: Reserves, payments and recoveries on a claim.
  - id: supplier_network
    name: Suppliers
    description: Repairers, loss adjusters and other third parties a claim relies on.
  - id: customer_comms
    name: Customer communications
    description: Outbound messages from a claim to the people involved in it, and what they contain.
  - id: reporting_mi
    name: Reporting and MI
    description: Management information and reports drawn from claims data.
  - id: admin_permissions
    name: Administration
    description: Administration of the Keelwater workspace, such as user accounts, access and settings.
  - id: integrations_api
    name: Integrations and API
    description: Connections between Keelwater and other systems.
  - id: release_change
    name: Product updates and rollout
    description: How Keelwater's own product updates are rolled out and how their arrival is handled.
```

## 4. Accounts

30 fictional insurers and 4 prospects. The top five accounts hold 53% of the £15.44m total; the median is £270,000 (the `value` denominator), so the nominal ARR for prospects and unresolved insights is £135,000; eight accounts renew within 90 days of 03/11/2026 (A01, A03, A06, A10, A15, A16, A20, A25). The line of business is used only by the generator for personas; Enrich reads ARR, tier and renewal date and nothing else.

| Key | Name | Line | Tier | ARR (GBP) | Renewal |
|---|---|---|---|---|---|
| A01 | Hollinbrook Home Insurance | home | Strategic | 2,400,000 | 15/01/2027 |
| A02 | Wexmoor Motor | motor | Strategic | 1,950,000 | 30/06/2027 |
| A03 | Marrowgate Commercial | commercial | Strategic | 1,600,000 | 12/12/2026 |
| A04 | Callowfield Auto Assurance | motor | Strategic | 1,250,000 | 31/03/2027 |
| A05 | Thistlecombe Mutual | home | Strategic | 980,000 | 01/09/2027 |
| A06 | Quillon Business Insurance | commercial | Enterprise | 860,000 | 20/01/2027 |
| A07 | Saltmarsh Specialty | specialty | Enterprise | 740,000 | 15/05/2027 |
| A08 | Pendleford Motor Mutual | motor | Enterprise | 690,000 | 28/02/2027 |
| A09 | Brackwater Homecover | home | Enterprise | 610,000 | 10/10/2027 |
| A10 | Stannary Commercial | commercial | Enterprise | 540,000 | 05/12/2026 |
| A11 | Ravensgill Insurance | motor | Enterprise | 470,000 | 30/04/2027 |
| A12 | Tidewell Marine & Cargo | specialty | Enterprise | 420,000 | 31/07/2027 |
| A13 | Linnet House Insurance | home | Enterprise | 360,000 | 14/03/2027 |
| A14 | Holloway Reach Underwriting | commercial | Enterprise | 320,000 | 22/08/2027 |
| A15 | Tarnholt Drive Cover | motor | Enterprise | 290,000 | 09/01/2027 |
| A16 | Ashcombe Property Mutual | home | Growth | 250,000 | 30/11/2026 |
| A17 | Penhallow Specialty Risks | specialty | Growth | 230,000 | 18/06/2027 |
| A18 | Cindermill Trade Cover | commercial | Growth | 210,000 | 03/04/2027 |
| A19 | Selsby Motor | motor | Growth | 190,000 | 27/09/2027 |
| A20 | Elderfold Home | home | Growth | 170,000 | 21/12/2026 |
| A21 | Brantwick Commercial | commercial | Growth | 150,000 | 11/05/2027 |
| A22 | Ormsgill Cyber | specialty | Growth | 135,000 | blank in HubSpot |
| A23 | Orrinbury Fleet Insurance | motor | Growth | 120,000 | 16/02/2027 |
| A24 | Kilnsey Household | home | Growth | 105,000 | 07/07/2027 |
| A25 | Greystock Liability | commercial | Growth | 92,000 | 25/01/2027 |
| A26 | Duncastle Auto | motor | Growth | 80,000 | 19/08/2027 |
| A27 | Fellbrook Fine Art & Specie | specialty | Growth | 70,000 | 13/03/2027 |
| A28 | Farrowdene Home | home | Growth | 60,000 | 02/06/2027 |
| A29 | Calderwick Commercial | commercial | Growth | 52,000 | 24/09/2027 |
| A30 | Merrow Vale Motor | motor | Growth | 45,000 | 08/04/2027 |
| P1 | Harrowfield Fleet Mutual | motor | prospect | none | none |
| P2 | Brindlecombe Home | home | prospect | none | none |
| P3 | Sallowmere Motor | motor | prospect | none | none |
| P4 | Quarrendon Commercial | commercial | prospect | none | none |

**HubSpot is deliberately messy**, matching the assumption that it is heavily customised:
- 36 records: 30 customers, 4 prospects (`lifecyclestage: "opportunity"`, no ARR) and 2 stale duplicates (A06 and A15, older `hs_lastmodifieddate`, out-of-date ARR).
- ARR sits in the custom property `keelwater_arr_gbp` in mixed formats (`"2400000"`, `"1,250,000"`, `"£610k"`, `"540000.00"`).
- The default `annualrevenue` holds the insurer's own revenue, a trap for anyone who reads it as ARR.
- One renewal date is `null` (A22) and one tier is lower-case (`"enterprise"`).

## 5. Volumes per source (seed 42)

| Source | Route | Records | Composition | Text by |
|---|---|---|---|---|
| Gong | sales | 25 calls | 18 with customers, 7 with prospects; 8 long (40-60 turns), 17 short | LLM |
| Intercom | support | 60 conversations | 22 resolved by Fin, 12 escalated from Fin, 26 human only | LLM |
| Fireflies | onboarding, account_management | 22 calls | 10 onboarding sessions, 12 account reviews (QBRs) | LLM |
| FullStory | sessions | 40 sessions, about 1,200 events | 10 themed, 11 false-positive, 19 clean; 10 over 90 minutes, mostly idle | code |
| HubSpot | none (reference) | 36 companies | section 4 | code |
| Shortcut | none (reference) | 12 stories | 6 completed, 3 in progress, 3 not started | LLM (short) |
| Notion | none (reference) | 10 pages | 7 roadmap items, 3 release-note pages | LLM (short) |

Expected load: about 1,250 snippets, 350-450 kept after triage (INFERRED from turn counts).

## 6. Planted ground truth

Routes: S sales (Gong), U support (Intercom), O onboarding (Fireflies), A account_management (Fireflies), X sessions (FullStory). A FullStory mention is one session showing the pattern.

### 6.1 Seed 42 themes

| Id | Kind | Bucket | Sev | S | U | O | A | X | Mentions | Accounts |
|---|---|---|---|---|---|---|---|---|---|---|
| `rt-doc-type-misfile` | real | documents_evidence | 3 | 0 | 4 | 3 | 2 | 4 | 13 | A01 A02 A03 A05 A07 A09 A13 A18 |
| `rt-reserve-approval-queue` | real | reserves_payments | 3 | 3 | 3 | 0 | 4 | 0 | 10 | A02 A04 A07 A08 A11 A14 P1 |
| `rt-fnol-duplicate-claims` | real | fnol_intake | 3 | 2 | 4 | 2 | 0 | 3 | 11 | A01 A04 A08 A11 A15 A19 A23 P3 |
| `rt-repairer-status-blind` | real | supplier_network | 3 | 3 | 2 | 0 | 4 | 0 | 9 | A02 A04 A08 A19 A26 P1 |
| `rt-mi-export-mismatch` | real | reporting_mi | 2 | 1 | 4 | 0 | 2 | 3 | 10 | A01 A03 A05 A06 A10 A12 A16 |
| `rt-unannounced-ui-change` | real | release_change | 4 | 2 | 3 | 2 | 5 | 0 | 12 | A01 A02 A03 A04 A06 A10 A13 P2 |
| `cx-auto-assignment` | contradictory | triage_assignment | 2 | 0 | 4 | 4 | 0 | 0 | 8 | more automation: A02 A04 A11; less: A03 A07 A12 |
| `sh-bulk-upload` | shipped | documents_evidence | 2 | 2 | 3 | 2 | 0 | 0 | 7 | A05 A09 A16 A20 A24 P4 |
| `rm-milestone-updates` | roadmap | customer_comms | 2 | 2 | 3 | 0 | 3 | 0 | 8 | A01 A05 A09 A13 A16 A21 |
| `nz-renewal-pricing` | noise | none | none | 4 | 2 | 0 | 4 | 0 | 10 | A01 A02 A06 A10 A15 A20 |
| `nz-customer-it-outage` | noise | none | none | 0 | 5 | 2 | 2 | 0 | 9 | A03 A08 A12 A17 A22 |
| `lt-welsh-templates` | probe | customer_comms | 4 | 2 | 2 | 0 | 2 | 0 | 6 | A01 only |

**Dates.** For every real, contradictory and roadmap theme and the probe, half the mentions (rounded down) are dated 04/10/2026 or later; each real theme has at least three mentions in each month (for the stability replay, docs/evals.md §4.4). Five shipped-theme mentions predate the release on 06/10/2026; two follow it.

Descriptions (what the generator briefs the LLM with):
- **rt-doc-type-misfile.** Uploaded documents are auto-classified under the wrong type (garage estimates under "Correspondence"), so handlers re-file them and sometimes miss evidence. FullStory: rage clicks on the "Document type" select after upload.
- **rt-reserve-approval-queue.** A reserve change above a handler's authority waits in one approver's queue with no delegation when they are away, so claims stall.
- **rt-fnol-duplicate-claims.** The same loss reported by phone and web portal creates two claims, with no warning at intake. FullStory: dead clicks on a disabled "Link to existing claim" button.
- **rt-repairer-status-blind.** No live repair status from garages, so handlers phone suppliers to chase progress; they call it a daily blocker.
- **rt-mi-export-mismatch.** MI dashboard totals disagree with the CSV export (UTC versus UK local cut-off), so finance distrusts the figures. FullStory: error clicks on "Export CSV", then repeated exports.
- **rt-unannounced-ui-change.** Unannounced interface changes move or rename controls, forcing retraining and causing errors; customers ask for notice, a preview and fewer, bundled changes.
- **cx-auto-assignment (contradictory).** Large motor accounts want more automatic assignment (by postcode, skill, workload); commercial and specialty accounts want it off for complex claims. The honest answer is per-team configuration.
- **sh-bulk-upload (shipped).** Upload many documents to a claim at once. Shipped 06/10/2026 (Shortcut story 4127); the two later mentions must appear as post-ship feedback.
- **rm-milestone-updates (roadmap).** Automatic SMS and email updates to policyholders at claim milestones: Notion page "Policyholder milestone notifications", In progress, target Q1 2027.
- **nz-renewal-pricing (noise).** Renewal price complaints, concentrated in high-ARR accounts, so it would rank highly if triage let it through.
- **nz-customer-it-outage (noise).** "Keelwater is down" reports caused by the customer's own sign-on provider, VPN or email; it reads like a bug report.
- **lt-welsh-templates (adversarial probe).** One Strategic account (A01, renewing in January) asks for Welsh-language letter templates through sales, support and its account manager, and calls it a renewal blocker. Genuine signal, built as the strongest single-account candidate; it must rank below all six real themes.

**One-off requests**, one mention each, from Growth-tier accounts at severity 1-2: keyboard shortcuts in claim notes (U), saved filters on the claims list (U), dark mode (U); webhook retries (S), a higher API rate limit for nightly sync (S); custom claim-reference format (O), mapping sign-on groups to roles (O); audit-log export for admins (A), a sandbox for testing fraud rules (A), splitting a payment across several payees (A). They are correct whether kept as small opportunities or left unclustered.

### 6.2 Expected outcomes and designed ranking (seed 42)

Scores apply the architecture section 4 formula to the true inputs, with recency 0.5 for every theme; the eval does not trust this table and recomputes the oracle from `ground_truth.yaml` and the real dates (docs/evals.md §4.1).

| Theme | Accounts | Customer ARR | Renewing <= 90 days | Routes | Expected outcome | Score | Rank |
|---|---|---|---|---|---|---|---|
| rt-unannounced-ui-change | 8 | £8.96m | 4 | 4 | ranked | 27.6 | 1 |
| rt-doc-type-misfile | 8 | £8.85m | 2 | 4 | ranked | 20.0 | 2 |
| rt-fnol-duplicate-claims | 8 | £5.41m | 2 | 4 | ranked | 18.5 | 3 |
| rt-reserve-approval-queue | 7 | £5.42m | 0 | 3 | ranked | 15.6 | 4 |
| rt-repairer-status-blind | 6 | £4.16m | 0 | 3 | ranked | 13.9 | 5 |
| rt-mi-export-mismatch | 7 | £7.05m | 5 | 4 | ranked | 13.1 | 6 |
| cx-auto-assignment | 6 | £6.43m | 1 | 2 | one opportunity; brief cites both stances | 9.2 | 7 |
| lt-welsh-templates | 1 | £2.40m | 1 | 3 | below all six real themes | 7.3 | 8 |
| rm-milestone-updates | 6 | £4.75m | 2 | 3 | tagged on_roadmap, roadmap 0.5 | 5.4 | 9 |
| sh-bulk-upload | 6 | £2.12m | 2 | 3 | tagged shipped; 5 pre-ship mentions not ranked; 2 listed as post-ship feedback | n/a | n/a |
| nz-renewal-pricing | 6 | £6.21m | 5 | 3 | dropped at triage; none in top 10 | n/a | n/a |
| nz-customer-it-outage | 5 | £3.08m | 1 | 3 | dropped at triage; none in top 10 | n/a | n/a |

Customer ARR excludes prospects (scored at the nominal £135,000). The top-6 set is exactly the six real themes. Two pairs are close by design and reported, not gated: doc-type vs FNOL (20.0 vs 18.5) and repairer vs MI export (13.9 vs 13.1). With all its mentions recent the probe would score 14.6, so its dates follow the same rule.

**Hard negatives** test tagging in both directions:
- `rt-doc-type-misfile` shares a bucket with shipped bulk upload and a not-started spike, "Document classifier confidence threshold" (story 4133): **not** tagged shipped.
- `rt-reserve-approval-queue` shares a bucket with the "Reserve history audit export" roadmap page (Planned): **not** tagged on_roadmap.

### 6.3 Realistic noise mix

Calls carry pleasantries (about 35% of customer turns), scheduling (about 45 turns), 6 one-off pricing haggles and Keelwater-only stretches; Intercom carries admin notes on 25 conversations, 12 password resets and 10 how-to questions resolved by Fin, about 15 thanks and closers, and 6 praise mentions across sources; FullStory carries 6 sessions of habitual double-clicks registered as rage clicks (`fs_rage_count` 3 on "Save", no error) and 5 of dead clicks on static headings.

**Distractors** put theme vocabulary into non-themed records ("document type" in a how-to question), so keyword matching fails. **Replies to paraphrases:** some mentions are a customer agreeing with an employee's summary ("Yes, exactly that"), so the problem lives in the preceding internal turn, attached as context.

**Join traps** (expected account in ground truth): 2 Intercom conversations from personal addresses (`@mailbox.example`): `null`, unresolved. 1 Gong call attended by a broker (`@crestline-brokers.example`) and the customer: the customer. 1 Fireflies call with two customer domains: `null`, ambiguous. 2 HubSpot duplicates: the canonical record.

### 6.4 Seed 43: the held-out set

Same accounts, HubSpot, Shortcut and Notion files; about 40% of the volume; three real themes and one noise theme unseen in seed 42. Never used for tuning (docs/evals.md §4.3).

Gong 10 calls, Intercom 24 conversations, Fireflies 8 calls (4 onboarding, 4 QBRs), FullStory 16 sessions.

| Id | Kind | Bucket | Sev | S | U | O | A | X | Mentions | Accounts |
|---|---|---|---|---|---|---|---|---|---|---|
| `ho-payee-bank-details` | real | reserves_payments | 3 | 2 | 3 | 0 | 2 | 0 | 7 | A03 A05 A08 A11 A14 A21 |
| `ho-role-setup` | real | admin_permissions | 2 | 0 | 3 | 3 | 0 | 2 | 8 | A02 A06 A09 A12 A16 A19 A24 |
| `ho-letter-joint-names` | real | customer_comms | 3 | 2 | 3 | 0 | 2 | 0 | 7 | A01 A04 A07 A10 A13 A15 |
| `hz-invoice-admin` | noise | none | none | 1 | 3 | 0 | 2 | 0 | 6 | A02 A03 A17 A20 A25 |

- **ho-payee-bank-details.** Third-party payee bank details cannot be checked before payment, so payments bounce and are re-issued days later.
- **ho-role-setup.** Admins cannot copy an existing role, so a new team means ticking dozens of permission boxes per user; mistakes lock handlers out. FullStory: bursts of checkbox clicks.
- **ho-letter-joint-names.** With joint policyholders, letters merge only one name or the wrong one, and complaints follow.
- **hz-invoice-admin (noise).** Requests to change purchase-order numbers or billing contacts on Keelwater's own invoices.

Plus four one-offs from Growth-tier accounts at severity 1-2 (print a claim summary (U), filter tasks by due date (U), export notes as PDF (O), bulk-close stale tasks (A)) and the same noise categories. Designed scores: payee 15.2, role setup 10.6, joint names 16.7; no one-off can exceed 2.4, so the top-3 set is the three themes.

## 7. Native record shapes

Each file copies its tool's export shape (full field lists in docs/research/datasets-and-source-schemas.md). What matters for the pipeline:

| Tool | File | Shape | Times | Speaker side and account | Assumed |
|---|---|---|---|---|---|
| Gong | `gong/calls.json`, `gong/transcripts.json` | `POST /v2/calls/extensive` and `/v2/calls/transcript` responses | sentence `start`/`end` integer ms; `duration` seconds | `speakerId` joins `parties[]` (`affiliation` Internal/External, `emailAddress`); account from the HubSpot object in `context[].objects` | none |
| Intercom | `intercom/<id>.json`, one conversation each | retrieved conversation with `conversation_parts` | Unix seconds | `author.type` user, admin or bot; `part_type: "note"` is internal; account from `source.author.email` | `resolution_state` and `last_answer_type` values ASSUMED (`assumed_resolution`, `confirmed_resolution`, `routed_to_team`, `abandoned`; `ai_answer`, `custom_answer`); `content_sources` shape and Fin as `author.type: "bot"` INFERRED |
| Fireflies | `fireflies/<id>.json` | GraphQL `transcript(id)` | sentence `start_time`/`end_time` float seconds | speakers are names, mapped to emails through `meeting_attendees`, the host and `config/teams.yaml`; unmatched speakers quarantined | `date` as epoch ms, `duration` in minutes INFERRED |
| FullStory | `fullstory/events.ndjson`, `fullstory/sessions.json` | warehouse event rows; session-list rows | ISO 8601 UTC | `userId` email in the session row joins the account | `target_text`, `target_selector`, `source_properties` contents ASSUMED; session row INFERRED |
| HubSpot | `hubspot/companies.json` | CRM companies list; every value a string or `null` | ISO strings | `properties.domain` | list envelope INFERRED; ARR, tier and renewal in `keelwater_arr_gbp`, `keelwater_tier`, `renewal_date` |
| Shortcut | `shortcut/stories.json` | stories | ISO | none | `completed_at` INFERRED; it drives the post-ship cut |
| Notion | `notion/pages.json` | pages of the roadmap data source: `Name` (title), `Status`, `Target` (date), `Problem` (rich_text) | ISO | none | none |

Rage, dead and error clicks are `click` events, not separate types, for example:

```json
{"event_id": "e9f1c2a07b", "event_time": "2026-10-14T08:31:52.114Z", "session_id": "7741203", "event_type": "click", "event_properties": {"fs_rage_count": 5, "fs_dead_count": 0, "fs_error_kind": null, "target_text": "Document type"}, "source_properties": {"page_name": "Claim > Documents"}}
```

## 8. Generator design

### 8.1 Command

```text
keelwater generate --seed 42             # data/raw/** and data/ground_truth.yaml; --force to overwrite
keelwater generate --seed 43             # held-out set into data/holdout/ from generator/spec/holdout/
keelwater generate --seed 42 --dry-run   # plan and cost estimate; no model calls
```

### 8.2 Steps

| # | Step | Engine | What it does |
|---|---|---|---|
| 1 | Plan | code, seeded RNG | Reads the spec (`accounts.yaml`, `people.yaml`, `glossary.yaml` shared; `themes.yaml`, `noise.yaml` per seed), creates every record and assigns each mention to one respecting route, account, date rule and stance (0-3 mentions a record, at most 2 per theme). The plan stays in the git-ignored `generator/build/`. |
| 2 | Write | LLM | One call per text record (129 for seed 42, 42 for seed 43). Returns private JSON: turns or parts, each tagged with a mention id, a noise category or neither. |
| 3 | Assemble | code | Converts to native shapes (timing from word counts at about 150 words a minute), adds noisy metadata (section 9, rule 3), strips every tag and records each mention's locator and `at_ms`. |
| 4 | FullStory | code | Random walks over a page graph; injects theme patterns, false positives and 20-110 minute idle gaps. |
| 5 | HubSpot | code | The 36 company records with the planted mess. |
| 6 | Verify | code | Checks below; a failing record is regenerated twice at most, then the run aborts. |
| 7 | Emit | code | Raw files sorted by source id, then the ground-truth file. |

Verification (step 6):
- every file validates against the per-source JSON Schemas the connectors use;
- every planted mention sits in a customer turn of 8 or more words (or a short agreement after an internal turn carrying the problem) with one of its theme's synonym terms;
- mention counts per theme, route and month equal the spec, and the date rule in §6.1 holds;
- no theme id, title or fact phrase appears in the raw files;
- no 6-word sequence occurs in more than two mentions of one theme;
- every capitalised person or company name appears in `people.yaml`, `accounts.yaml` or `glossary.yaml`; any other name fails the record.

### 8.3 Per-record prompt (outline)

```text
<role>
You write one realistic {source} record for Keelwater, a claims-handling software company used by UK insurers.
</role>
<record>
{Type and length (e.g. "Gong discovery call, 40-60 speaker turns"), date, participants with names, roles and companies from the list given, register, and for Intercom whether Fin answers first and escalates.}
</record>
<mentions>
{For each planted mention: the problem in plain words, ONE fact chosen at random from the theme's fact list, the speaker's role, stance where relevant, severity, and form (complaint, workaround, feature ask, question). Write it in the speaker's own words; do not reuse the wording given here.}
</mentions>
<noise>
{Required noise for this record: pleasantries, scheduling, a pricing aside, internal chatter, and so on.}
</noise>
<rules>
Customers speak like claims staff, not product managers. No headings or bullets inside speech. Use only the people and company names given above; never use the name of any real company, product or person. Mention no feature not in the product glossary. Tag each turn with its mention id, noise category or null.
</rules>
<output>
JSON matching the schema for {source}.
</output>
```

### 8.4 Model, determinism and caching

- **Model.** `qwen/qwen3-vl-235b-a22b-instruct` (USD 0.21 / 1.90 per million tokens, from the OpenRouter model list), temperature 0.8. Mistral Large was dropped because the data is invented and should cost almost nothing. Free OpenRouter models failed the 3-record smoke (empty or over-length output, an account policy block, or turn counts out of range); `deepseek/deepseek-v4.1-flash` with reasoning off is the recorded fallback (it failed the smoke on content rules). No pipeline stage uses Qwen VL, so no judge reads text its own family wrote. `provider.data_collection` is `allow` for the generate stage only, because the data is synthetic with no customer content (reason recorded in config/models.yaml); every other stage keeps `deny`.
- **Structured slots.** The response schema is built per record: the turn band, the noise categories and one slot per planted mention (opaque labels m1, m2, ... in place of ids) and per required element (Fin bot turn, escalation reply, admin note, required noise, how-to distractor). Code inserts and tags those turns, so the "missing X" checks hold by construction; checks that forbid things or judge text (unknown names, forbidden phrases, synonym presence) stay as validators, with the failed rule fed back into each regeneration prompt.
- **Seed.** The seed drives every code-side choice.
- **Cache.** Responses are cached by request hash in the committed `generator/cache/`, so a seed reproduces its data byte for byte offline; without the cache only the text changes.

### 8.5 Output layout

```text
data/
  raw/                gong/, intercom/ (60 files), fireflies/ (22 files), fullstory/, hubspot/, shortcut/, notion/
  ground_truth.yaml   read only by signal_engine/evals
  holdout/
    raw/              same layout at seed 43 volumes
    ground_truth.yaml
generator/
  spec/*.yaml  spec/holdout/*.yaml  cache/   (committed)       build/ (git-ignored)
```

A dataset's `data_hash` is the SHA-256 over its `raw/**` in sorted path order, with LF line endings (`.gitattributes` sets `eol=lf`).

### 8.6 Ground-truth schema

```yaml
schema_version: 1
generated: {seed: 42, generator_version: 0.1.0, model: qwen/qwen3-vl-235b-a22b-instruct, raw_sha256: "<hash>"}
as_of: 2026-11-03                  # reference date for recency
window: {from: 2026-09-01, to: 2026-10-31}
accounts:                          # key -> canonical HubSpot record
  A01: {hubspot_id: "18452001001", name: Hollinbrook Home Insurance}
themes:
  - id: rt-doc-type-misfile
    kind: real                     # real | contradictory | shipped | roadmap | noise | probe | one_off
    title: Uploaded documents filed under the wrong type
    bucket: documents_evidence     # null for noise
    severity: 3                    # null for noise
    stances: []                    # contradictory only, e.g. [more_automation, less_automation]
    product_ref: null              # shipped: {source: shortcut, id: 4127}; roadmap: {source: notion, id: "<page uuid>"}
    hard_negatives: [{source: shortcut, id: 4133}, {source: shortcut, id: 4127}]
    expected: {outcome: ranked, top6: true}   # ranked | tagged_shipped | tagged_roadmap | suppressed | below_real
    mentions:
      - id: m-0007
        source: intercom           # gong | intercom | fireflies | fullstory
        route: support             # sales | support | onboarding | account_management | sessions
        source_id: "215467"
        locator: {part_id: "9182736455"}   # gong sentence_start_ms; fireflies sentence_index; fullstory event_ids
        at_ms: 38000               # matched against snippet start_ms..end_ms
        account: A03               # null on a join trap
        occurred_at: 2026-10-14T09:31:12Z
        stance: null
        post_ship: false           # shipped theme only
noise:                             # labelled noise units
  - {source: intercom, source_id: "215502", locator: {part_id: "source"}, at_ms: 0, category: password_reset}
  # categories: pleasantry | scheduling | pricing | internal | password_reset | how_to | praise | closer
fullstory_false_positives:
  - {session_id: "7741988", event_ids: ["e0a1…"], kind: habitual_double_click}   # or static_dead_click
join_traps:
  - {source: intercom, source_id: "215611", expected_account: null, reason: personal email domain}
```

### 8.7 Cost and time (INFERRED)

Seed 42 needs 129 calls, about 150k output and 260k input tokens (Fireflies is the largest share). At USD 0.70 / 2.10 per million tokens that is about USD 0.50 for seed 42 and about USD 0.20 for seed 43, within the generation caps of USD 0.90 and 0.30 with retries (docs/build-plan.md section 9). With 8 parallel calls a full generation takes about 10 minutes. FullStory and HubSpot cost nothing because code writes them.

## 9. Keeping the pipeline honest: no theme markers

The pipeline must find the themes, not read them. Rules, each with a test:

1. **No markers in records:** no theme id, mention id, title or fact phrase under either `raw/`.
2. **Nothing correlates with theme:** random ids, files named and sorted by source id or time.
3. **Metadata stays noisy:** Intercom tags from a simulated agent right about 70% of the time, Gong trackers from keyword lists, Fireflies `ai_filters` from rules.
4. **Phrasing varies:** random fact, voice and form per mention; shared 6-word sequences rejected; distractors.
5. **Ground truth and taxonomy are clean.** Ground truth lives only in the two `ground_truth.yaml` files and `generator/spec/`; connectors read only `raw/`. Tests fail if any module in `signal_engine/` outside `signal_engine/evals/` references those paths or imports `generator` (`cli.py` is exempt, because it registers `generate`), and if any seed 42 or seed 43 theme title or fact phrase appears in `prompts/` or `config/`, including `config/taxonomy.yaml`.
6. **Evals run after the pipeline,** and seed 43 only after tuning on seed 42 is frozen.

## 10. Limits of the synthetic data

- **Condensed transcripts:** 15-60 turns where a real call has hundreds.
- **One writer:** real customers bring typos, cross-talk and recognition errors that ours mostly lack.
- **Planted themes are cleaner than reality,** and one author wrote generator and pipeline; seed 43 and the taxonomy scan limit that bias.
- **No audio or screen share.**
- **FullStory events come from a page graph,** not real DOM detail.
- **Assumed vendor fields** (D3) must be checked against the first real export, when this data retires.
