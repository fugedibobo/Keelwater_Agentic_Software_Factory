# Decision records

Author: Andras Fugedi. Date: 03/11/2026, revised after review round 1. Status of all records: accepted for the demo build. Companion to docs/architecture.md (section references point there). Options are ranked, recommended first.

Index: 001 typed workflow, 002 model gateway, 003 triage decision model, 004 ranking formula, 005 verified quotes, 006 binary judges, 007 storage, 008 synthetic data, 009 Signal Board, 010 telemetry and audit, 011 PDLC and platform contract, 012 release cadence, 013 held-out seed and stability replay.

---

## ADR-001: Typed-step workflow over an autonomous agent for intake

**Context.** Intake must run unattended overnight on thousands of items, cost a predictable amount, and be explainable to a regulated customer's auditor. An agent that chooses its own tools is flexible, but its cost, path and failures vary from run to run.

**Decision.** Intake is a fixed workflow of typed steps (architecture section 4). LLMs interpret text and fill typed fields, code validates, the database enforces. Each stage is idempotent per `run_id` and resumable.

**Options considered.**
1. Typed-step workflow (chosen): testable per stage, bounded cost, clean audit.
2. Workflow with one agentic step for odd inputs: more flexible, harder to bound.
3. Fully autonomous agent with tools: most flexible, least predictable, hardest to audit.

**Consequences.** Odd inputs are handled by explicit fallbacks and an `untriaged` state, not improvisation. New sources need a connector and a segmenter. The platform team's factory still uses agents for build; this decision is about intake only.

**Revisit when.** A stage needs open-ended tool use, for example the PM question-answering agent or the sales "ask before a demo" agent.

---

## ADR-002: One OpenAI-compatible model gateway with profiles

**Context.** The tooling landscape may change within 3 to 6 months, customer data must stay in the VPC in production, and Keelwater wants to avoid vendor lock-in and move to self-hosted open-weight models.

**Decision.** Every model call, triage included, goes through one gateway wrapper around the `openai` SDK with a configurable base URL; a decision-model adapter maps each triage backend to the same record. Profiles in `config/models.yaml` choose endpoint and model per stage: `replay` (recorded responses, no network, the default), `demo` (OpenRouter, Clef for triage), `aws` (Bedrock eu-west-2 through the `bedrock-runtime` VPC endpoint), `self-hosted` (vLLM in the VPC). The demo uses the open weights Bedrock also serves wherever OpenRouter has them, so moving to aws is a configuration change plus one re-qualification run of the eval suites.

**Options considered.**
1. OpenAI-compatible interface plus profiles (chosen): moving environment is configuration; thin and swappable.
2. A routing library such as LiteLLM in front: more features, one more dependency to run inside the VPC.
3. A vendor SDK per provider: native features, locked in, code changes per move.

**Consequences.** Provider-specific features are not used. Every call is logged in `model_call` at one choke point, with `call_id` passed to Bedrock as `requestMetadata` so invocation logs join it; models served only on `bedrock-mantle` (not logged) are called through Converse on `bedrock-runtime`. Judge trust is per model version, so a profile move restarts it on the existing labels. SQLite to Postgres and SSO remain code changes.

**Revisit when.** A required capability exists only in a native SDK, or the gateway needs fallback and budget routing beyond what profiles give.

---

## ADR-003: Decision model for triage; Clef in the demo and the self-hosted profile, in-VPC triage in production from day one

*Revised 04/11/2026: Jev replaced by Clef so demo and production triage can share open weights.*

**Context.** Most incoming snippets are noise. A frontier model on every item is wasteful, slow at volume and buries PMs. Cloudflare Clef (27B, open weights) is a decision model that can be self-hosted on one GPU, and OpenRouter serves it through its Decisions API, so the demo and production can run the same weights.

**Decision.** Triage asks one decision model four typed questions at once (product signal, bucket, severity, signal type), through the gateway. The demo uses Clef (`cloudflare/clef`) through OpenRouter's Decisions API, with `provider.data_collection = "deny"`; it never sees production data. The aws profile runs Bedrock `openai.gpt-oss-20b-1:0` in eu-west-2 from day one, with thresholds fitted on labels (`openai.gpt-oss-120b-1:0` as the one fallback); the self-hosted profile runs Clef, the same weights as the demo, in the VPC, and a ModernBERT/SetFit classifier trained on PM labels is the later option. Any shadow or canary compares two in-VPC backends. Middle-band items proceed as `low_confidence` and outages as `untriaged`; nothing is silently dropped. A fixed weekly sample of 40 drops is audited.

**Options considered.**
1. Decision model with confidence gates and one fallback (chosen): sub-second and fractions of a cent per item.
2. Self-hosted fine-tuned classifier from day one: best long-term, but there are no labels yet.
3. Cheap general LLM for every item: simple, but 10 to 100 times the cost and slower.
4. Keyword or rule filters: cheap, but misses paraphrase and cannot give a bucket.

**Consequences.** The demo calls OpenRouter for one stage and the docs say so; the weights are open, and no closed hosted model sits in the triage path. The aws egress allow-list excludes OpenRouter, and a test fails if any aws-profile host is outside the VPC endpoints list. Labels collected in the board become the training set for the later classifier.

**Revisit when.** About 1,000 labelled triage decisions exist, the noise-audit miss rate exceeds its alert level, or the data-engineering hire changes where classifiers are hosted.

---

## ADR-004: Deterministic ranking formula; the LLM never ranks

**Context.** PMs will only trust a ranked list they can challenge. LLM rankings are unstable between runs and cannot be explained beyond a story.

**Decision.** Score = breadth x severity x value x corroboration x recency x renewal x roadmap (architecture section 4): ARR-weighted severity, recency as the share of recent evidence, renewal as the renewing share of ARR; shipped items score only post-ship evidence. The board shows every factor. Weights live in `config/ranking.yaml`.

**Options considered.**
1. Transparent multiplicative formula (chosen): stable, explainable, tunable by a squad.
2. Formula plus a bounded PM boost per opportunity: adds PM judgement, risks gaming.
3. LLM ranking with justification: catches nuance, but unstable and unauditable.
4. Learned ranking from PM accept/reject: needs far more labels than we have.

**Consequences.** Nuance the formula cannot see (strategic fit) stays with the PM, who can reject or edit. The formula uses HubSpot only for ARR, tier and renewal date, keeping the dependency on messy data small.

**Revisit when.** PM overrides show a consistent bias, or enough accept/reject labels exist to fit and test a learned re-ranker against the formula.

---

## ADR-005: Verified quotes and citations; reject unverifiable output

**Context.** Reviewers and customers will ask "how do you stop it making things up?". An evidence-backed opportunity is only credible if each quote is really in the source and each claim cites real evidence.

**Decision.** Each insight carries a verbatim quote that must be found in its own snippet text (never the attached internal context), exactly or after normalisation (case, whitespace, punctuation, speech fillers); the match type and span are stored. No fuzzy matching. A failure is retried once and then rejected, never shown. Each claim in a brief cites insight ids; every id must exist and belong to that opportunity, or the brief fails.

**Options considered.**
1. Deterministic match and citation-integrity checks, reject on fail (chosen): free, exact, catches most hallucination.
2. Fuzzy semantic matching of quotes: tolerates paraphrase, lets subtle invention through.
3. LLM-only faithfulness judging: flexible, costs a call and can itself hallucinate.

**Consequences.** Some real insights are lost when the model paraphrases; the rejection rate is tracked in the Pipeline tab. The LLM judges (ADR-006) work on top of these checks, not instead of them.

**Revisit when.** The rejection rate on genuine quotes is high (translation, speech-to-text noise), in which case add a bounded fuzzy match with a lower trust label.

---

## ADR-006: Three binary per-failure-mode judges, certified on blind PM labels

**Context.** "LLM as judge" scores are meaningless until shown to agree with humans, and a small labelled set certifies very little: with 25 items per class, 20 of 25 correct has a Wilson 95% interval of 0.61-0.91.

**Decision.** Three judges (faithfulness, signal, duplicate), each returning pass or fail with a critique, run by a model family different from the brief writer and extractor. Cluster coherence is designed, not built in v1. A judge version is trusted when, on the held-out split, it has at least 50 blind real-PM labels per class and a Wilson 95% lower bound of at least 0.75 on both TPR and TNR (target point estimate 0.90). Only label-panel labels made without seeing the verdict count. Until then the board shows "calibrating: n of 50 per class"; in the demo no judge is trusted.

**Options considered.**
1. Binary judges per failure mode, certified on a lower bound (chosen): clear, measurable, honest about small samples.
2. One holistic 1-to-5 quality judge: simple, but opaque and hard to calibrate.
3. Human review only: most accurate, does not scale.

**Consequences.** An honest trust period at the start, likely weeks. PMs carry a labelling cost, kept to about 45 minutes a week (20 judged items, 40 noise-audit drops). Revocation uses the upper bound, so it does not flap. A prompt or model change re-qualifies on existing labels.

**Revisit when.** A judge stays below the bar for a month, or PM labelling time cannot be found.

---

## ADR-007: SQLite for the demo, Postgres with pgvector for production

**Context.** The demo must run on a Windows 10 laptop with Python and no Docker. Production data is already in Postgres, and embeddings need vector search.

**Decision.** One schema (architecture section 7) behind a thin repository layer. SQLite with brute-force cosine similarity in the demo; RDS Postgres with pgvector in production. Metabase reads a reporting schema, not production tables.

**Options considered.**
1. SQLite now, Postgres later behind one repository layer (chosen): zero setup, same shape.
2. Postgres in Docker from the start: closer to production, violates the no-Docker constraint.
3. A hosted vector database: extra vendor touching customer data, rejected.

**Consequences.** No concurrency in the demo. Two SQL dialects to keep compatible; a small test runs the repository layer against both when Postgres is available.

**Revisit when.** First multi-user deployment, or data volume makes brute-force similarity too slow.

---

## ADR-008: Synthetic data with planted ground truth

**Context.** No real Keelwater data is available, public datasets do not match insurer claims handling, and accuracy claims need a known right answer.

**Decision.** Generate synthetic exports in each tool's native shape. Plant six real themes across at least three routes, two noise themes, one contradictory signal, one shipped theme and one on-roadmap theme, and write `data/ground_truth.yaml`. Every run is scored against it.

**Options considered.**
1. Synthetic with planted truth (chosen): licence-clean, measurable recall and precision.
2. A public dataset adapted to the task: realistic text, no ground truth for our themes, licence risk.
3. Hand-written small sample: quick, too small to test ranking or noise.

**Consequences.** Results show the pipeline works on known structure, not on real-world messiness; the docs say so. Realism limits are flagged as assumptions.

**Revisit when.** The first real export arrives; run it through the same checks and keep the synthetic set as the regression suite.

---

## ADR-009: Static-renderable Signal Board plus a local API

**Context.** A reviewer should be able to see the product without installing anything, and a PM should be able to act on it when it runs. The build time is a few hours.

**Decision.** FastAPI serving Jinja templates and a little vanilla JS. The same templates render a static `site/index.html` with actions disabled and a banner. No build step.

**Options considered.**
1. Server-rendered templates with a static export (chosen): one codebase, double-click viewing.
2. A React single-page app: richer, needs a build step and more time.
3. A Streamlit or notebook front end: fast, hard to style and to export statically.
4. Static page only: simplest, but no actions and no labels.

**Consequences.** Limited interactivity offline. Design quality depends on the impeccable pass. The page structure maps to tabs that squads can use as-is.

**Revisit when.** Squads use the board weekly and ask for features (comments, assignments) that need a richer client.

---

## ADR-010: Self-hosted Phoenix plus own append-only audit tables as the source of truth

**Context.** Every agent step needs telemetry, and every model call and human decision must be auditable. Phoenix is open source and self-hostable, but a trace viewer is not an audit record.

**Decision.** Phoenix (self-hosted in the VPC, default credentials replaced, KMS and retention set) for traces. `model_call` and `audit_event` are the audit source of truth. Every derived row (triage, insight, brief, judgement, outtake) carries `call_id`, and `model_call` names its target. `audit_event` is append-only (SQLite triggers block UPDATE and DELETE; an INSERT-only role in production) and hash-chained (`prev_hash`, `hash`), exported nightly to object-locked S3. Trust grants and revocations and config changes (ranking weights, thresholds, taxonomy, models) are audit events.

**Options considered.**
1. Phoenix plus own tables (chosen): rich traces plus a durable, queryable audit record we own.
2. Phoenix only: less to build, audit depends on its retention and schema.
3. Own tables only: simplest, loses trace tooling.
4. A hosted observability product: easiest, sends customer data to another vendor.

**Consequences.** Two writes per call, kept in the gateway wrapper. Phoenix is optional in the demo; Phoenix experiments are designed, not built. The demo actor is the local user (unauthenticated); production uses SSO.

**Revisit when.** Phoenix schema or retention changes, or a product with better eval workflows can be self-hosted.

---

## ADR-011: The PDLC layer owns intake and outtake; the platform team owns build

**Context.** A platform team is building the engineering factory. Their remit excludes product and design, they think in tickets and small changes, and their coding agents may run outside the VPC. Reviewers' concern is where work hands off from step to step.

**Decision.** The PDLC layer (product operations) owns sensing, deciding, defining, enabling and learning. The platform team owns build and the release pipeline. The contract is two artefacts: an intent document, which holds quotes and account names and stays in the VPC, and a factory job that validates against `docs/contracts/factory_job.schema.json` v1. The job carries evidence references (insight ids, run manifest hash), a de-identified problem statement, users affected by tier, testable acceptance criteria, an outcome metric with baseline and query, constraints, non-goals, data classification, trace ids, supersede/cancel, an idempotency key and the gate approvals with actor and time. The factory may reject a job with a reason. Platform asks: a stable job schema, status callbacks into the opportunity state machine, and test and guardrail results attached to each job. Product operations owns: intent quality, the labelled evals, and the human gates.

**Options considered.**
1. Two layers with a schema contract (chosen): clear ownership, testable interface.
2. Product operations also builds a mini factory: faster to start, duplicates platform work.
3. Platform team takes intake too: one team, but outside their remit and skills.

**Consequences.** Product operations has no authority over squads, so adoption relies on the board being useful. No customer text reaches agents outside the VPC; a de-identification check enforces it. The schema is a negotiation item; a bad schema blocks the loop.

**Revisit when.** The factory harness is chosen and live, or the platform team's remit expands.

---

## ADR-012: Deploy daily; release to customers in announced, flag-controlled bundles

**Context.** Keelwater ships daily and leadership will not slow that down. Several large, regulated customers retrain staff when the product changes and have asked for fewer, pre-announced releases.

**Decision.** Deployment stays continuous and every change ships behind a feature flag. Customer-visible release happens in announced bundles on a published cadence, by switching flags. Each bundle has a change notice and enablement material drafted in the outtake step and accepted by a human.

**Options considered.**
1. Daily deploy, bundled flag-controlled release (chosen): keeps engineering speed, gives customers predictability.
2. Slow deployment to match customers: predictable, loses speed and conflicts with leadership.
3. Per-customer flag rollout with no bundles: flexible, hard to communicate and to support.

**Consequences.** Flag hygiene becomes a real cost; stale flags must be tracked. Some customers can opt into early access. Release notes are written per bundle, not per deploy.

**Revisit when.** Customers' feedback shows the cadence is too slow or too fast, or flag debt grows beyond a set threshold.

---

## ADR-013: Held-out seed and stability replay against overfitting

**Context.** One author knows the six planted themes and tunes prompts, taxonomy and judges on the same data, so seed 42 alone could reward tuning to the answer.

**Decision.** A held-out seed 43 (about 40% of the volume, three unseen themes plus one noise theme) is generated once and never used for tuning; it runs only after tuning on seed 42 is frozen, and both are reported. A two-batch replay (September, then October) asserts that opportunity ids persist and no planted theme forks. Taxonomy descriptions may not echo planted-theme wording; the leak scan covers `config/taxonomy.yaml`.

**Options considered.** 1. Held-out seed plus stability replay (chosen). 2. Cross-validation over theme subsets of one seed: no unseen vocabulary. 3. Real data: none is available.

**Consequences.** About USD 0.20 of extra generation and one more suite per change. A held-out failure is fixed on seed 42 only, then seed 43 re-runs once.

**Revisit when.** The first real export arrives and becomes the held-out set.
