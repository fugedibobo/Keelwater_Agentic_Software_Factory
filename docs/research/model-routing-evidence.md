# Model routing evidence for an AI coding software factory

Scope: published evidence, gathered 04/11/2026, for building a delegation ruleset that routes each task to the cheapest adequate Anthropic Claude or OpenAI Codex model and benchmarks open-weight challengers (GLM 5.3, DeepSeek V4.1 Flash, Qwen). No benchmark was run. FOUND = read at the URL (page date given if shown); INFERRED = reasoning stated. Prices are USD per million tokens (in/out). Most pages were read through a summarising fetch tool, so re-check any figure you will contract on. Earlier Anthropic prices in docs/research/model-options-and-prices.md (02/11/2026) were re-checked and still match.

## Q1 Anthropic

FOUND platform.claude.com/docs/en/about-claude/pricing (no page date):

| Model | In/out | Cache write 5m/1h | Cache read | Batch in/out |
|---|---|---|---|---|
| Haiku 5.5 (prompt up to 100K) | 0.10/0.50 | 0.125/0.20 | 0.01 | 0.05/0.25 |
| Haiku 5.5 (over 100K) | 0.50/2.50 | 0.625/1 | 0.05 | 0.25/1.25 |
| Sonnet 5.5 | 2/10 | 2.50/4 | 0.10 | 1/5 |
| Opus 5.5 | 4/20 | 5/8 | 0.20 | 2/10 |
| Fable 5.1 (and Mythos 5.1) | 10/50 | 12.50/20 | 0.25 | 5/25 |

- Batch API is 50% off. Cache read is 0.05x input for Opus/Sonnet 5.5, 0.025x for Fable 5.1, 0.1x for Haiku. Fast mode for Opus 5.5 is 8/40 (not with Batch). The Haiku 100K threshold counts cache reads and writes.
- Effort tiers: low, medium, high, xhigh, max; no separate effort price (so effort costs only through output tokens). Default medium (Opus, Haiku) and high (Sonnet) on the API; Claude Code runs medium. FOUND code.claude.com/docs/en/sub-agents; startdebugging.net (28/10/2026, secondary).
- Vendor claim: Opus 5.5 at default effort uses about 40% less cost than Opus 5 and matches GPT-6 Astra on Terminal-Bench 4.0 for about 40% of the cost. FOUND anthropic.com/claude-opus-5-5 (22/09/2026). Vendor-reported.

## Q2 OpenAI Codex

FOUND developers.openai.com/api/docs/pricing (latest dated note 30/07/2026):

| Model | Standard in/cached/out | Batch/Flex | Fast |
|---|---|---|---|
| gpt-6.1-sol | 2/0.10/10 | 1/0.05/5 | 4/0.20/20 |
| gpt-6.1-terra | 1/0.05/5 | 0.50/0.025/2.50 | 2/0.10/10 |
| gpt-6-luna | 0.10/0.01/0.50 | 0.05/0.005/0.25 | 0.20/0.02/1 |
| gpt-6-astra | 10/1/50 | 5/0.5/25 | 20/2/100 |
| gpt-5.3-codex | 1.75/0.175/14 | n/a | 3.50/0.35/28 |

- Sol: prompts over 272K cost 2x input and 1.5x output. Released 29/09/2026. FOUND aicatchup.com/news/openai-gpt-6-1-sol (updated 28/10/2026, secondary).
- Effort tiers for Sol: low, medium (default), high, xhigh, max. Vendor-reported cost and score per task for Sol, from the same secondary page:

| Sol effort | DeepSWE score / cost | Terminal-Bench Science score / cost |
|---|---|---|
| low | 64.4% / $0.17 | 43.7% / $1.79 |
| medium | 73.0% / $0.42 | 47.6% / $2.34 |
| high | 75.2% / $0.65 | 51.1% / $2.76 |
| xhigh | 71.9% / $0.79 | 53.7% / $2.89 |
| max | 71.9% / $1.57 | 57.0% / $5.47 |

- INFERRED: on DeepSWE, high is the cost-quality peak (xhigh and max cost 1.2x and 2.4x for lower score); on Terminal-Bench Science each step up still buys points, max costs 3x low.
- Artificial Analysis (via amplifying.ai/coding-agents/codex, snapshot 09/06/2026), Codex harness, 358 tasks, pass@1 over 3 runs: GPT-5.5 xhigh 65.3 index, $4.33/task, 4.8M tokens; medium 60.4, $2.21, 2.8M tokens. So xhigh cost 1.96x for 4.9 points on an older model.
- Terra has no listed effort tiers in OpenAI's model-selection page (FOUND learn.chatgpt.com/docs/model-selection.md; ChatGPT-oriented, undated). It is described for scoped code fixes. "Terra" benchmark data is for GPT-5.6 Terra, not 6.1 (see Q4).

## Q3 Open weights

| | GLM 5.3 | DeepSeek V4.1 Flash (1017) | Qwen "4" |
|---|---|---|---|
| Release | 13/08/2026 launch, weights public by 28/08/2026 | 17/10/2026 snapshot | Qwen 4 NOT released |
| Licence | custom GLM-5.3 Licence (security review if licensee revenue over $10bn/12 months) | MIT | n/a |
| Params | 744-753B total, 40B active | 763B total (HF); OpenRouter says 552B backbone, 8B/16B active (sources disagree; active not on HF) | n/a |
| Context | 1,048,576 | 1M | n/a |
| OpenRouter price | typical 1.40/4.40 (cached 0.26) | 0.035-0.30 in / 0.30-1.20 out by provider; DeepSeek direct 0.15/0.60 | Qwen3.8-2.4T-A95B: 2/6 |
| GPUs | 8x H200/H20 (FP8); 8x B200 for full 1M context | not found; INFERRED about 763GB in FP8 fits 8x H200 (1.1TB) | not found |

Sources: kingy.ai/blog/glm-5-3-specs-benchmarks-api-how-to-use (13/08/2026, updated 28/08); artificialanalysis.ai/models/glm-5-3; huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017; openrouter.ai/deepseek/deepseek-v4.1-flash-1017; openrouter.ai/qwen/qwen3.8-2.4t-a95b (release 12/08/2026, 2.4T total, 95B active, 1M context, licence not stated).

- Qwen 4: FOUND claudegpt.si/news/qwen-4-release-date (29/10/2026, secondary): Alibaba said at Apsara on 22/09/2026 that Qwen 4 is "in training"; no size, date, tier names, price or open-weight status announced; no Qwen 4 on Hugging Face. Variant lists online are unconfirmed. The largest real open model is Qwen3.8-2.4T-A95B (INFERRED: 2.4T parameters is a multi-node deployment; no GPU figure found).
- Z.ai also has GLM-5.3-Flash (MIT). Not in the question; used in Q4 only as a caution.

## Q4 Coding benchmarks

Comparison table (blank = not found; vendor = self-reported):

| Model | In/out | SWE-bench Verified | SWE-bench Pro | Terminal-Bench | Cost or tokens per task | Source |
|---|---|---|---|---|---|---|
| Opus 5.5 | 4/20 | not found | 89.9% (vendor scaffold, version unstated) | TB 4.0: 66.4% (xhigh, Claude Code, 5 trials) | AA Coding Agent Index 61.7 at max, $11.42/task; vendor: default effort about 1/5 of Opus 5 max cost | anthropic.com/claude-opus-5-5; morphllm.com/swe-bench-pro; cellcog.ai AA summary (23/10/2026) |
| Sonnet 5.5 | 2/10 | not found | V2: 95.79 +/-1.30 (mini-swe-agent, xhigh) | TB 4.0: 70.6% (medium) | AA index 59.3 (max); cost not found | anthropic.com/claude-sonnet-5-5 (28/09/2026); labs.scale.com SWE-Bench Pro V2 (22/09/2026) |
| Haiku 5.5 | 0.10/0.50 | not found | V2: 87.23 +/-2.36 (mini-swe-agent, high) | TB 4.0: 39.2% pass@1 | not found | anthropic.com/claude-haiku-5-5 (07/10/2026) |
| GPT-6.1 Sol | 2/10 | not found (OpenAI stopped reporting it) | V2: 96.11 +/-1.24 (mini-swe-agent, xhigh) | TB-Science: 57.0% at max | AA: Codex, max, index 54.1, $1.50/task; table above | labs.scale.com; aicatchup.com; cellcog.ai |
| GPT-6.1 Terra | 1/5 | not found | not found (GPT-5.6 Terra: 92.37, Codex xhigh) | not found | not found | labs.scale.com |
| GLM 5.3 | 1.40/4.40 | not found | V2: 95.60 +/-1.30 (mini-swe-agent, max) | TB 2.1: 88.2 (Z.ai-reported, mixed settings); TB 4.0: not found | AA: 140M output tokens on its Intelligence Index, "very verbose" | labs.scale.com; kingy.ai; artificialanalysis.ai |
| DeepSeek V4.1 Flash | 0.15/0.60 direct | not found | not found (V4 Flash-Max 52.6%, vendor) | TB 4.0: 42.3 (Claude Code harness, vendor) | AA: Codex, max, index 47.3, $0.39/task | HF card; cellcog.ai; morphllm.com |
| Qwen3.8-2.4T (not Qwen 4) | 2/6 | not found | 67.7% (vendor) | AA: TB 2.1 82.0, TB 4.0 11.1 | not found | openrouter.ai/qwen/qwen3.8-2.4t-a95b |

Harness cautions:
- Scale's V2 leaderboard (FOUND, 22/09/2026, 642 tasks) mixes harnesses. Entries labelled Claude Code or Codex use those; the rows above use mini-swe-agent at different efforts. Scores near 96-99% leave little separation (INFERRED: V2 is close to saturation for the top group, so use it to rule models out, not to rank them). The older "Pro" figures (Opus 5.5 89.9, Qwen 67.7, Sonnet 5 63.2, GPT-5.6 Sol 64.6) are vendor scaffolds, not comparable to V2.
- SWE-bench Verified: OpenAI stopped reporting it on 23/02/2026 after finding 59.4% of 138 unsolved problems had flawed tests or specs, and all frontier models tested could reproduce verbatim fixes (contamination). It recommends SWE-bench Pro. FOUND openai.com/index/why-we-no-longer-evaluate-swe-bench-verified. Treat any Verified figure as weak evidence.
- Terminal-Bench versions differ (2.1, 3.0, 4.0 are not comparable; GLM's TB 2.1 88.2 against TB 4.0 numbers of 39-70 shows this). Opus 5.5 TB 4.0 ran with production safeguards that may have lowered the score (Anthropic).
- Capital & Compute "cost per task" (capitalandcompute.net, 29/10/2026) is a modelled shared task (1.5M input tokens, 90% cached, 40K output) for every model, so it reflects price only, not tokens used. Do not use it as a cost-per-task measure.
- AA Coding Agent Index v2.0 gives cost but no token counts (FOUND via secondary page). The only model-specific token figures found: GPT-5.5 xhigh 4.8M vs medium 2.8M per task.

## Q5 Routing and cascades

- General baseline: RouteLLM (ICLR 2025, via getunblocked.com) cut cost about 75-85% while keeping about 95% of GPT-4 quality; this is chat, not agents. FOUND secondary.
- Enterprise-routing preprint, arXiv 2609.28919 (24/09/2026): classifier routing of Claude Code traffic recovers 14-21% of spend (24% with no pauses, 7.4% with pause-heavy users). Most saving comes from picking the cheapest capable model at session start. A mid-task switch pays back only after 8-291 requests (cache loss). 12.5% of moved turns were false downgrades; corrections (over a third of the bill) were never moved. No quality score; equal quality assumed. FOUND.
- Scrouting, arXiv 2608.04804 (05/08/2026): a cheap repository scout routes to cheap fixers on SWE-bench Pro Python (266 tasks): 159 solves versus 158 for Opus 4.6 solo, reported cost per solve $0.230 against $1.274 (about 18%). A reviewer note says the appendix ledger implies about $0.544 per solve (about 43%); the handoff gain was +1.8 points, not significant (p=0.401). Treat the saving as 2.3x to 5.5x, not proven. Older models. FOUND via pith.science.
- Advisor split: Opus 5.5 with a Fable 5.1 advisor scored 1.7 points above Opus alone at about 2.1x cost, "at the edge of run-to-run noise". FOUND startdebugging.net (28/10/2026, secondary, cites Anthropic internal benchmark). INFERRED: do not pay for a top-tier advisor by default.
- Anthropic guidance: subagents exist partly to "control costs by routing tasks to faster, lower-cost models like Haiku"; a user-defined Explore subagent with model haiku overrides the built-in; model field accepts haiku/sonnet/opus/fable/inherit; subagent calls count toward usage limits. Haiku 5.5 "pairs well with Opus 5.5 and Sonnet 5.5 as a subagent" for narrow work (compaction, summarisation); for complex agentic coding Sonnet or Opus remain better. FOUND code.claude.com/docs/en/sub-agents; anthropic.com/claude-haiku-5-5 (07/10/2026).
- OpenAI guidance: start demanding agents on gpt-6.1-sol; gpt-6-luna is the "lower-cost option for lighter subagent work"; subagents inherit parent model and effort; high effort for reviewers, low for straightforward work; subagent workflows use more tokens than a single agent. FOUND learn.chatgpt.com/docs/agent-configuration/subagents.md (undated).
- Evidence gap: no source measured a Claude/Codex mixed pipeline end to end with quality and cost together.

## Q6 Failure and rework

- Agent PR acceptance (AIDev, 7,156 filtered PRs; MSR 2026, arXiv 2602.08915v2, 07/05/2026): Codex 77.9%, Cursor 74.5%, Claude Code 71.9%, Copilot 68.0%, Devin 61.6%. By task: chore 84.0%, docs 82.1%, feat 66.1%, fix 66.0%, test 61.5%, perf 55.4%. Reviews per PR: Copilot 4.94 vs Codex 1.39 (not shown causal). Rework not measured directly. FOUND. INFERRED: about a third of agent PRs are rejected even for current tools, so the cost of a failed attempt includes the human review time spent before rejection.
- Stack Overflow 2025 survey (via getunblocked.com, secondary): 66% cite "almost right, but not quite" AI output as a top frustration; 45% say debugging AI code takes longer.
- Variance: the same task varied up to 30x in tokens on SWE-bench Verified (arXiv 2026 "How Do AI Agents Spend Your Money?", via getunblocked.com, secondary).
- Pricing a failed cheap attempt (INFERRED, not a published method): expected cost per accepted result = (C_cheap + R_review) / p_cheap, where p is pass@1 and R_review is human or reviewer-model time; escalate when that exceeds C_strong / p_strong. Retries are not free of cache loss (arXiv 2609.28919: switching mid-task is costly), so escalate at session start rather than mid-task when the task type has a low p_cheap (test, perf, fix).

## Gaps

- Not found: SWE-bench Verified for any current model; SWE-bench Pro V2 for Opus 5.5, GPT-6.1 Terra, DeepSeek V4.1 Flash and Qwen; Terminal-Bench scores on one version for all models; tokens per task by model and effort (except GPT-5.5 and the Sol table).
- Not found: pass@k data for any listed model; published review-time cost per failed AI PR; DeepSeek and Qwen GPU requirements from a primary source; GLM-5.3 Terminal-Bench 4.0 score.
- Qwen 4 is unreleased, so no challenger data exists for it; Qwen3.8-2.4T is the nearest.
- Many figures are vendor-reported or from aggregators read through a summarising tool; Terra, Luna and Sol are named inconsistently across sources (5.6 vs 6.1), so confirm model IDs before pinning.
