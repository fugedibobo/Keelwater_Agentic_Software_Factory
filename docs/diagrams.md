# Diagram specifications (Archify)

Author: Andras Fugedi. Date: 03/11/2026, revised after review round 1. Consistent with docs/architecture.md. Facts about Archify are from docs/research/diagrams-design-and-video-tools.md.

## 0. Common rules

| Rule | Detail |
|---|---|
| Tool | Archify v3.2.0: the agent writes typed JSON, a Node CLI validates it and renders one self-contained HTML file. Node 18 or later; Edge or Chrome installed; non-elevated shell. |
| Node types | Only seven: `frontend`, `backend`, `database`, `cloud`, `security`, `messagebus`, `external`. |
| Boundary kinds | Only `region` and `security-group`. There is no VPC kind, so the VPC is a `region` boundary labelled exactly "AWS VPC (eu-west-2)". Inner zones are `security-group` boundaries. |
| Canvas | Keep under 1240px wide. The agent places coordinates by hand and the router cannot rearrange boxes, so budget for one repair round on edge crossings. |
| Labels | Short: node labels at most 3 words plus a short sub-label; edge labels at most 4 words. |
| Data | Everything is synthetic or a design; no customer names appear. |

Export steps (all three diagrams):

1. Run `finalize` as the skill does (`node bin/archify.mjs finalize <type> candidate.json out.html --quality showcase --json`) and fix anything it reports.
2. Copy the HTML into `docs/diagrams/` with the file name given in each section.
3. Open the HTML in a browser; press `T` to toggle light and dark and check both.
4. For PNG: open the viewer's `E` menu and export a PNG; save it as `docs/diagrams/<name>.png`. Use it in the README and the PDF.
5. Commit the HTML and PNG together.

Acceptance checks (all three):

- [ ] No overlapping boxes, labels or edges crossing a label.
- [ ] Every text readable at 100% zoom (the finalize check enforces a 6px floor; aim for far above it).
- [ ] No horizontal overflow; canvas under 1240px.
- [ ] Looks correct in both light and dark.
- [ ] Node and edge counts match this document.
- [ ] Every edge has a label.
- [ ] The VPC boundary label reads "AWS VPC (eu-west-2)" and no external SaaS node sits inside it.

---

## A. Production architecture

| Field | Value |
|---|---|
| Purpose | Show that everything touching customer data runs inside Keelwater's own VPC (triage included, on Bedrock from day one), with the audit trail, and where each part of the Signal Engine sits. |
| Archify type | `architecture` |
| File | `docs/diagrams/production-architecture.html` and `.png` |
| Reference example | `examples/production-deployment.architecture.json` (nested `security-group` inside a `region`) |

Boundaries: outer `region` "AWS VPC (eu-west-2)" (id `vpc`); inside it `security-group` boundaries `z_ingest` "Ingestion", `z_triage` "Triage", `z_intel` "Intelligence", `z_store` "Store", `z_audit` "Telemetry and audit", `z_out` "People-facing outputs". Sources sit outside, with no boundary. If six zones will not fit under 1240px, merge `z_triage` into `z_intel` and note it in the file.

Nodes (15):

| id | label | type | zone |
|---|---|---|---|
| ext_calls | Gong and Fireflies | external | outside VPC |
| ext_intercom | Intercom and Fin | external | outside VPC |
| ext_fullstory | FullStory | external | outside VPC |
| ext_hubspot | HubSpot | external | outside VPC |
| s3_raw | S3 raw landing | cloud | z_ingest |
| connectors | Connectors | backend | z_ingest |
| sfn | Step Functions | messagebus | z_ingest |
| triage | Triage (gpt-oss) | backend | z_triage |
| intel | Extract, rank, brief | backend | z_intel |
| bedrock | Bedrock endpoints | cloud | z_intel |
| pg | RDS Postgres + pgvector | database | z_store |
| phoenix | Phoenix | backend | z_audit |
| audit | CloudTrail and audit_event | security | z_audit |
| board | Signal Board | frontend | z_out |
| ext_workspace | Notion, Shortcut, Slack | external | outside VPC |

Edges (from, to, label):

| from | to | label |
|---|---|---|
| ext_calls | connectors | calls via allow-list |
| ext_intercom | connectors | tickets via allow-list |
| ext_fullstory | connectors | sessions via allow-list |
| ext_hubspot | connectors | ARR, tier, renewal |
| connectors | s3_raw | raw export |
| sfn | connectors | nightly trigger |
| s3_raw | triage | segmented snippets |
| triage | intel | product signal |
| triage | bedrock | typed decisions |
| intel | bedrock | typed prompts |
| intel | pg | insights, scores |
| triage | pg | triage decisions |
| intel | phoenix | traces |
| intel | audit | model_call rows |
| pg | board | ranked opportunities |
| board | pg | annotations |
| board | audit | audit_event rows |
| board | ext_workspace | digest, write-back (planned) |

Prompt for the Archify skill:

```
Use archify, type architecture. Canvas width under 1240px. One outer region
boundary labelled "AWS VPC (eu-west-2)". Inside it six security-group zones:
Ingestion, Triage, Intelligence, Store, Telemetry and audit, People-facing
outputs. Four external SaaS sources (Gong and Fireflies, Intercom and Fin,
FullStory, HubSpot) sit OUTSIDE the VPC on the left, and one external
workspace node (Notion, Shortcut, Slack) outside on the right. Use exactly the
15 nodes and 18 edges in docs/diagrams.md section A, with these ids, labels,
types and zones. Every edge has a label of at most 4 words. Dashed edge for
"digest, write-back (planned)". Use the Signal Flow preset. No overlapping
boxes; run finalize with --quality showcase and fix everything it reports.
```

---

## B. Nightly run dataflow

| Field | Value |
|---|---|
| Purpose | Show one run from schedule to Signal Board, with every gate and where items drop out, so a reader can see nothing is silently lost. |
| Archify type | `dataflow` (use `sequence` only if the agent cannot lay out the drop-out branches) |
| File | `docs/diagrams/nightly-run-dataflow.html` and `.png` |

Nodes (17): types follow the nearest Archify meaning.

| id | label | type | zone |
|---|---|---|---|
| schedule | Nightly schedule | messagebus | trigger |
| connect | Connect (schema check) | backend | ingest |
| reject_schema | Bad schema, quarantined | database | drop-out |
| segment | Segment | backend | ingest |
| triage | Triage gate | backend | filter |
| noise | Noise, logged | database | drop-out |
| audit_q | Noise audit (40 a week) | frontend | drop-out |
| extract | Extract insight | backend | intelligence |
| verify | Quote verifier | security | intelligence |
| reject_quote | Rejected, logged | database | drop-out |
| enrich | Enrich (ARR, renewal) | backend | intelligence |
| cluster | Cluster and tag | backend | intelligence |
| rank | Rank (formula) | backend | intelligence |
| brief | Brief writer | backend | intelligence |
| judge | Three judges | security | intelligence |
| board | Signal Board | frontend | output |
| pm | PM review | external | output |

Edges (from, to, label):

| from | to | label |
|---|---|---|
| schedule | connect | start run |
| connect | segment | valid raw |
| connect | reject_schema | invalid |
| segment | triage | customer turns, context |
| triage | noise | p <= 0.10 dropped |
| noise | audit_q | stratified weekly sample |
| triage | extract | signal, conf >= 0.70 |
| triage | extract | uncertain, low_confidence |
| extract | verify | insight + quote |
| verify | enrich | quote found |
| enrich | cluster | ARR, tier, renewal |
| verify | reject_quote | not found after retry |
| cluster | rank | opportunities |
| rank | brief | top N |
| brief | judge | cited brief |
| judge | board | pass or fail + critique |
| board | pm | calibrating until trusted |
| audit_q | pm | miss-rate labels |
| pm | judge | labels calibrate judges |

Prompt for the Archify skill:

```
Use archify, type dataflow. Canvas width under 1240px, flowing left to right
in a main lane with a lower lane for drop-outs. One run, from "Nightly
schedule" to "PM review". Use exactly the 17 nodes and 19 edges in
docs/diagrams.md section B. Gates are the Triage gate, Quote verifier and
Three judges (type security). Items that leave the main lane go to drop-out nodes
(type database) in the lower lane; none may disappear without an edge. Label
every edge with at most 4 words. Add a legend line: "dashed = feedback to
judges and audit". Use the Signal Flow preset. Run finalize with --quality
showcase and fix every reported problem.
```

---

## C. Agentic PDLC

| Field | Value |
|---|---|
| Purpose | Show the seven stages, the five human gates, and which team owns each stage, so ownership and handoffs are explicit. |
| Archify type | `workflow` |
| File | `docs/diagrams/agentic-pdlc.html` and `.png` |

Boundaries: `region` "Product operations layer" (id `pops`) and `security-group` "Platform team: engineering factory" (id `factory`). Release is shared; place it in `factory` and label its gate as product-owned.

Nodes (12):

| id | label | type | zone |
|---|---|---|---|
| sense | Sense | backend | pops |
| decide | Decide | backend | pops |
| g1 | Gate 1: PM accepts opportunity | security | pops |
| define | Define | backend | pops |
| g2 | Gate 2: the Trio (PM, Designer, Tech Lead) approves intent | security | pops |
| build | Build | backend | factory |
| g3 | Gate 3: human PR review | security | factory |
| release | Release | backend | factory |
| g4 | Gate 4: bundle announced and approved | security | factory |
| enable | Enable | backend | pops |
| g5 | Gate 5: PM accepts drafts | security | pops |
| learn | Learn | database | pops |

Edges (from, to, label):

| from | to | label |
|---|---|---|
| sense | decide | ranked signals |
| decide | g1 | opportunity brief |
| g1 | define | accepted |
| define | g2 | intent doc + mockup |
| g2 | build | factory job |
| build | g3 | pull request |
| g3 | release | approved change |
| release | g4 | flag-controlled bundle |
| g4 | enable | released bundle |
| enable | g5 | notes, article, notice |
| g5 | learn | accepted and sent |
| learn | sense | outcomes and labels |

Ownership summary (shown as a small caption in the diagram, and used in the README):

| Stage | Owner | Agent work | Human gate |
|---|---|---|---|
| Sense | Product ops | nightly intake, triage, extraction | none (noise audit samples) |
| Decide | Product ops | cluster, rank, brief, judge | Gate 1: PM |
| Define | Product ops | intent document, mockup draft | Gate 2: the Trio (PM, Designer, Tech Lead) |
| Build | Platform team | factory builds from the job | Gate 3: engineer reviews PR |
| Release | Platform team with product ops | flags, bundle assembly | Gate 4: bundle announced |
| Enable | Product ops | release note, help article, change notice, follow-up brief | Gate 5: PM or product marketing |
| Learn | Product ops | adoption and outcome measurement, labels | none |

Prompt for the Archify skill:

```
Use archify, type workflow. Canvas width under 1240px, flowing left to right.
Seven stages in order: Sense, Decide, Define, Build, Release, Enable, Learn,
with five human gate nodes (type security) between them as listed in
docs/diagrams.md section C. Two boundaries: a region "Product operations
layer" containing Sense, Decide, Define, Enable, Learn and gates 1, 2, 5; and
a security-group "Platform team: engineering factory" containing Build,
Release and gates 3, 4. Use exactly the 12 nodes and 12 edges in the
document. Learn feeds back to Sense with a dashed edge. Add a one-line
caption under the canvas: "Agents do the work; people pass the gates." Use the
Blueprint preset. Run finalize with --quality showcase and fix every
reported problem.
```
