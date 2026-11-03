# Research: decision models (Jev, Clef, OpenAI Decisions) and Phoenix telemetry

Researched 02/11/2026. FOUND = checked at the source URL; INFERRED = reasoned.

The owner's "JEV" is a real product. It is Jev, made by TypeSafe AI and launched on 15/09/2026. "OpenAI's quick decision model" is the OpenAI Decisions API, and "Clef" is Cloudflare's family of open-weight decision models. All three answer typed questions with probabilities instead of generating text. Jev's yes/no question type is called "Noul": that is the vendor's spelling, not a typo.

## 1. Jev (TypeSafe AI)

- FOUND: TypeSafe came out of stealth on 15/09/2026. Access is through console.typesafe.ai, with the key stored in `TYPESAFE_API_KEY`. https://flaviocopes.com/jev-api-key/
- FOUND: the founder is Diogo Almeida, an OpenAI alumnus. It is a transformer but not an LLM and not autoregressive, so it cannot write text or act as an agent. https://www.deeplearning.ai/the-batch/models-built-to-do-one-thing-well
- FOUND: TypeSafe raised $870M at a $7.5B valuation. https://fourweekmba.com/ai-jev-maker-typesafe-raises-870m-at-a-7-5b-valuation/
- FOUND: it supports three question types, mixed freely in one call:
  - Noul: probability of "yes"
  - Choice: 1 to 255 options, returned with probabilities and a confidence
  - Score: 2 to 10 ordered levels
  - Source: https://docs.aimlapi.com/api-references/decision-models/typesafe/jev
- FOUND: there is also an experimental "box" type that locates something in an image. Same source.
- FOUND: the API is `POST https://api.typesafe.ai/v1/systemone` with a Bearer token. The body is `{model, state, questions:{key:{type, instructions, criteria}}}` and the response is `{model, answers, usage}`. https://docs.litellm.ai/docs/pass_through/typesafe.md
- FOUND: model names are `jev-latest`, `jev-preview`, `jev-1.13.0` and `jev-1.14.0`. There is no streaming. Same source.
- FOUND: the official SDKs are `typesafe-sdk` for Python (imported as `typesafe_sdk`) and `@typesafe-ai/sdk` for JavaScript. https://flaviocopes.com/jev-api-key/
- FOUND: `jevdecision` on PyPI is a third-party package (v0.1.0) that offers `gate()` and `route(min_confidence, fallback=...)` and can switch to an OpenAI backend. https://pypi.org/project/jevdecision/
- FOUND: pricing is $0.042 per million input tokens, with output free. https://www.eesel.ai/blog/typesafe-jev-pricing
- FOUND: one example call cost $0.0000225 and took 96 ms. https://docs.aimlapi.com/api-references/decision-models/typesafe/jev
- FOUND: latency is 70 to 500 ms by the vendor's own claim; OpenRouter measured a median of 0.21 s. https://innfactory.ai/en/ai-models/typesafe-jev/ and https://www.firecrawl.dev/blog/openai-decisions-api-vs-jev
- INFERRED: "about 0.1 s per decision" is the best case. The typical figure is around 0.2 to 0.5 s.
- FOUND: the default context is 64k tokens, of which at most 32k is the text being judged. A header raises this to 262k, but TypeSafe says that mode is slower and less accurate. Requests are capped at 32 MiB, and every question in a call is answered in one pass. https://innfactory.ai/en/ai-models/typesafe-jev/
- FOUND: the sources disagree on rate limits.
  - One gives 100k tokens/s and 80 requests/s, with 429 and 529 errors to back off from. https://www.factualminds.com/blog/jev-typesafe-ai-aws-guide-2026/
  - Another says limits are set per organisation with no published default. https://innfactory.ai/en/ai-models/typesafe-jev/
- FOUND: the sources also disagree on signups. One says they paused around 22/09. https://flaviocopes.com/jev-api-key/ Another (13/10) says signup is open with $5 of credit. https://aisuccesslabjuliangoldie.com/blog/jev-waitlist/
- FOUND: OpenRouter, Vercel AI Gateway and Cloudflare also serve Jev. https://openrouter.ai/docs/guides/community/jev.md
- FOUND: Jev cannot be self-hosted: weights are closed, there is no EU region and it runs from the US West Coast. TypeSafe offers a DPA with EU standard contractual clauses, does not train on customer data, and gives zero data retention only to enterprise customers through sales. No SOC 2 is documented. https://innfactory.ai/en/ai-models/typesafe-jev/
- FOUND: it is not on Bedrock, PrivateLink or AWS Marketplace, so calling it from a private AWS network needs a NAT gateway out on port 443. https://www.factualminds.com/blog/jev-typesafe-ai-aws-guide-2026/

## 2. Cloudflare Clef and OpenAI Decisions

- FOUND: Clef launched on 01/10/2026 in two sizes: `@cf/cloudflare/clef` (27B) and `@cf/cloudflare/clef-flash` (9B). It uses the same API format as Jev, so switching means changing the endpoint and model name. Weights are on Hugging Face under Apache 2.0. Cloudflare's own medians are 209 ms for Clef, 38.8 ms for Clef-flash and 524 ms for Jev. https://developers.cloudflare.com/changelog/post/2026-10-01-clef-workers-ai/
- FOUND: Clef costs $0.24 per million input tokens and has a 65k context. Self-hosting was tested on one H200 GPU. https://www.developersdigest.tech/blog/cloudflare-clef-decision-models-2026
- FOUND: on 09/10 Clef-flash dropped to $0.038 per million (below Jev), but its hosted context shrank to 24k. Cloudflare also added Clef-omni, which takes audio, video, image and text. https://aiweekly.co/alerts/cloudflare-ships-multimodal-clef-omni-cuts-flash-to-0038m
- INFERRED: Clef is the only one of the three that can run inside a private AWS network, by self-hosting the weights on a GPU.
- FOUND: OpenAI Decisions went to public beta on 06/10/2026 as `POST /v1/decisions`, built on GPT-6 Luna. It uses Predicate, Choice and Score question types, accepts images as base64, and costs $0.10 per million input tokens with no output charge. https://www.techwyse.com/news/platform-updates/openai-decisions-api-public-beta-gpt-6-luna-api-tiers
- FOUND: it is eligible for zero data retention and HIPAA, with US and EU data residency. https://fourweekmba.com/ai-openai-prices-decisions-api-0-10-m-input-no-output-fees/
- FOUND: one blogger's small benchmark (10/10/2026) scored:

  | Model | Accuracy | Speed | Cost per 10k decisions |
  |---|---|---|---|
  | Jev | 97.6% | 255 ms | $0.19 |
  | Microsoft Decision-1 | 97.6% | 422 ms | $0.065 |
  | Clef | 95.8% | 302 ms | $0.63 |
  | OpenAI Decisions | 90.5% | 222 ms | $0.23 |
  | Clef-flash | 87.5% | 394 ms | $0.10 |

  Source: https://akitaonrails.com/en/2026/10/10/which-jev-like-ai-decision-classifier-model-is-best/

## 3. Other options for "about 10 buckets plus noise in under a second"

- **RouteLLM** (LMSYS): FOUND: only decides strong model versus weak model, so it cannot sort into topic buckets. Poor fit. https://lmsys.org/blog/2024-07-01-routellm/
- **Not Diamond**: FOUND: a hosted router that picks which LLM to call, not a labeller. Poor fit. https://docs.notdiamond.ai/docs/strong-and-cheap-routing
- **Arch-Router** (1.5B, Katanemo): FOUND: about 50 to 100 ms on a GPU. Its authors say it is "technically not a classifier model". Weak fit. https://hn.nuxt.dev/item/44436031
- **ModernBERT** (149M/395M, 8k context): FOUND for size and context, https://www.answer.ai/posts/2024-12-19-modernbert.html. INFERRED: fine-tuned on a few hundred labels it runs in milliseconds on CPU; best fit for a private network once labels exist.
- **SetFit**: FOUND: exportable to ONNX for CPU, https://huggingface.co/docs/setfit/tutorials/onnx. INFERRED: few-shot training needs roughly 8 to 16 examples per class; good fit for a quick self-hosted baseline.
- **Small open decision models**: FOUND: in the same benchmark, 4B models reached 87 to 90% at about 200 ms on a local machine, while sub-1B models without fine-tuning scored only 31 to 61%. https://akitaonrails.com/en/2026/10/10/which-jev-like-ai-decision-classifier-model-is-best/

## 4. Arize Phoenix

- FOUND: the current version is 21.0.0, released 30/10/2026. It needs Python 3.11 to 3.15, and the licence is Elastic License 2.0 (from the PyPI JSON API). https://pypi.org/project/arize-phoenix/
- FOUND: self-hosting "on your own infrastructure or in your cloud account is free and fully permitted", with no feature gates. https://www.arize.com/docs/phoenix/self-hosting/license.md
- FOUND: install with `pip install arize-phoenix`, then run `phoenix serve`. https://pypi.org/project/arize-phoenix/
- FOUND: the UI and trace intake are on port 6006 and gRPC traces on 4317. Data defaults to a temporary SQLite file unless `PHOENIX_SQL_DATABASE_URL` points to SQLite or Postgres. https://www.arize.com/docs/phoenix/self-hosting/configuration
- FOUND: some Windows users have hit "C++ Build Tools required" errors during install. https://community.arize.com/x/phoenix-support/6dia1qt3l63u/installation-error-for-arize-phoenix-c-build-tools
- FOUND: v21 turns login on by default without needing `PHOENIX_SECRET`. https://github.com/Arize-ai/phoenix/releases/tag/arize-phoenix-v21.0.0
- FOUND: login switches on automatically only when Phoenix listens beyond the local machine. The pip default listens only on 127.0.0.1, so it stays off locally. https://www.arize.com/docs/phoenix/self-hosting/configuration
- FOUND: the default admin is admin@localhost / admin. https://www.arize.com/docs/phoenix/self-hosting/features/authentication.md
- FOUND: tracing is `pip install arize-phoenix-otel openinference-instrumentation-openai`, then `register(project_name=..., auto_instrument=True)`. It traces chat completions, Responses and OpenAI Decisions calls. https://www.arize.com/docs/phoenix/integrations/llm-providers/openai/openai-tracing.md
- FOUND: the endpoint is set by `endpoint=` or `PHOENIX_COLLECTOR_ENDPOINT`. https://www.arize.com/docs/phoenix/tracing/how-to-tracing/setup-tracing/setup-using-phoenix-otel.md
- INFERRED: other services that use the OpenAI client with a changed `base_url` are traced too, because the tracing hooks into the OpenAI SDK itself. Jev calls are not covered and need one manual span.
- FOUND: LLM-as-judge is in `arize-phoenix-evals`: `create_classifier(name, prompt_template, llm=LLM(provider="openai", model=...), choices={...})` plus `evaluate_dataframe`. https://arize-phoenix.readthedocs.io/projects/evals/
- FOUND: human labels on traces use `client.spans.add_span_annotation` or `log_span_annotations` with annotator kind HUMAN or LLM. Datasets use `client.datasets.create_dataset`. https://www.arize.com/docs/phoenix/sdk-api-reference/python/arize-phoenix-client.md
- FOUND: experiments use `client.experiments.run_experiment(dataset, task, evaluators)`. https://arize.com/docs/phoenix/datasets-and-experiments/how-to-experiments/running-experiments.md
- FOUND: on AWS there is an official CloudFormation template: Fargate in private subnets, secrets in Secrets Manager. Its load balancer faces the internet on port 80 by default and must be locked down. https://www.arize.com/docs/phoenix/self-hosting/deployment-options/aws-with-cloudformation.md
- FOUND: Arize AX is the commercial product. It is managed SaaS (self-hosting needs a commercial licence) and adds monitoring, dashboards, audit, SOC 2/HIPAA and SLA support; Phoenix has community support only. https://www.arize.com/docs/phoenix/resources/frequently-asked-questions/what-is-the-difference-between-phoenix-and-arize.md

## 5. Recommendation for a one-day demo (all INFERRED)

- **One function, several backends.** Write a single `decide(text) -> (bucket, confidence)`. Primary backend: Jev, sending one Choice question (10 buckets plus "noise") and one Noul ("is this actionable product feedback?") in the same call, so the text is paid for once. Hard timeout about 1.5 s.
- **Fallback chain.**
  1. Clef-flash on Workers AI. Same request format, so only the endpoint and model change.
  2. OpenAI Decisions.
  3. A cheap LLM call with a strict JSON schema.
  4. If everything fails, fail open: send the item to the expensive LLM tagged "untriaged" so nothing is silently dropped. Retry 429/529 with backoff, and stop calling a backend for a while after repeated failures.
- **Gating.**
  - Noise with confidence ≥ 0.9: drop it, but log it.
  - Any bucket with confidence ≥ 0.7: send to the expensive LLM with that bucket's prompt.
  - Everything else: send to the LLM for triage, or to a human-review queue.
  - Store bucket, confidence, backend and response time on every record.
- **Observability.** Run Phoenix locally with `phoenix serve` and send traces to it. Wrap the decision call in its own span, labelling the backend used and the bucket and confidence returned. Hand-annotate about 100 traces to get ground truth, turn them into a dataset, then run an experiment comparing Jev, Clef-flash and OpenAI Decisions on accuracy against those labels.
- **Cost.** Spend is negligible. For example, 5,000 items a week at about 3,000 tokens each is 15M tokens, roughly $0.63 a week on Jev.
- **Data and next step.** Sending customer transcripts to Jev (hosted in the US, no zero retention by default) needs legal sign-off. For production inside a private AWS network, swap the backend to self-hosted Clef-flash, or to ModernBERT or SetFit trained on the labels collected in Phoenix. The demo code does not change.

## Gaps

TypeSafe's own docs, pricing and legal pages could not be reached; the Jev facts come from aggregators, partner docs and press. The figures that disagree between sources (rate limits, signup status, context size) need confirming at console.typesafe.ai before anything depends on them. Phoenix was not installed or run on Windows.
