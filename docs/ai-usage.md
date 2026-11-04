# How AI was used on this task

Author: Andras Fugedi. Living log, started 02/11/2026. The short "How I used AI" account handed in with the task is drawn from the real entries below; nothing here is invented.

## Division of labour

| Part of the task | What did it | My role |
|---|---|---|
| Clarifying the goal | An orchestrating Claude session ran a structured "grill me" interview: ten numbered questions, each with a recommended answer | Answered; overrode four recommendations: open-weight models instead of a paid frontier API for the demo, a public repo instead of private sharing, a one-day demo build instead of a production-grade plan, and keeping the Jev decision model the AI had dismissed |
| Research | Six parallel research subagents (web search, public docs, public GitHub repos), each returning findings labelled FOUND (checked at source) or INFERRED (reasoned), saved to docs/research/ | Set the questions, read the summaries |
| Design | The orchestrator wrote docs/architecture.md; subagents drafted the evals, data, board, decisions and diagram specs from it | Set direction and constraints; ruled on trade-offs |
| Review | Independent subagents attacked the design from three angles (product leadership, engineering leadership, one-day feasibility) | Accepted or rejected findings |
| Build (03/11/2026) | Claude Code orchestrating codex workers from GitHub issues used as work orders, with human gates | Kept keys, the spend limit, approvals and judgement calls for myself |
| Writing | Drafted by AI, edited for plain English | Final read of everything reviewers see |

Time: about 4 hours of my own time across the whole task; agent time for the overnight planning plus about 22 hours planned for the build (docs/build-plan.md), much of it while I slept. Running a lot of autonomous work and keeping it honest is the skill this role needs, so the repo shows the working: issues, pull requests, review notes, test evidence.

## Where I trusted the output and where I did not

Trusted as it came:
- Record shapes for the source tools (Gong, Intercom, Fireflies, FullStory, HubSpot): the research cites each vendor's API reference, and the synthetic data copies those field names. Good enough for a demo; a real connector would be built against the live API.
- Mechanical work: scaffolding, schemas, synthetic data assembly, test plumbing, provided the tests ran.

Checked or overrode:
- Any number that will be quoted to leadership. Market-size estimates for claims software ranged from USD 0.5bn to USD 35bn between research firms (a 64x spread), so I dropped market size entirely.
- Productivity claims. The research surfaced vendor telemetry next to randomised trials; the two-pager leans on the trials and labels the rest.
- Model ids and prices, which change weekly. The build probes each id before use.

## Things the AI got wrong or led me towards, and how they were caught

1. **It doubted a real product.** My notes from an earlier conversation mention "Jev", a small decision model I want for triage. The orchestrator assumed it was a transcription error and suggested replacing it with a generic phrase. I knew it was real; research then confirmed Jev launched in September 2026, after the model's training data. Lesson: a model's knowledge cut-off shows up as confident scepticism about new tools. I now ask it to search before it doubts.
2. **It nearly put a non-compliant service in the production design.** Once Jev was confirmed, the obvious design was "use Jev for triage". Research showed Jev is US-hosted with closed weights, so it cannot run inside a private AWS network, which is a hard requirement. The design now uses Jev only in the demo and names a self-hosted, Apache-2.0 decision model (Clef-flash) or a classifier trained on PM labels for production, behind the same interface.
3. **It proposed paying for a frontier model API for the demo.** I overrode this: the demo defaults to open-weight models through one OpenAI-compatible interface, which is cheaper and matches the private-network, open-weight direction the design argues for. A frontier model is an optional profile.
4. **I proposed reusing public datasets; the evidence said no.** I suggested public sales-call and support-ticket datasets. Research found none that were B2B and freely redistributable (gated, non-commercial or consumer-retail), so the demo uses synthetic data with a planted ground truth. That turned out better: the planted themes give the evals an answer key.
5. **Self-review caught inconsistencies between AI-written docs.** Subagents writing the evals and data specs flagged faults in the architecture the orchestrator wrote: the same model family generating the data and judging it, recency maths that would break byte-for-byte replay, a triage threshold that left a gap, and corroboration counting tools instead of feedback routes. All were fixed before the build.
6. **It kept a closed-weight hosted model in the demo.** On 04/11/2026 I replaced Jev with Clef for demo triage. The AI's plan had kept a closed-weight hosted model as a demo-only dependency; I chose open, self-hostable weights so the demo matches the production path.

(Entries from build day are added below as they happen.)
