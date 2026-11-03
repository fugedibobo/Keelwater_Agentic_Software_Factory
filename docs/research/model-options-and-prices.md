# Research: model options, prices and private-network hosting

Researched 02/11/2026. FOUND = checked at the source URL; INFERRED = reasoned. Prices change weekly: re-check before relying on them.

Findings below are labelled FOUND (with URL) or INFERRED, prices in USD per million tokens (in/out) as listed on 02/11/2026.

Four limits on the data:
- All web content came through WebFetch, whose summaries are model-generated.
- curl to openrouter.ai was blocked by the egress policy, so I did not use the raw JSON API.
- OpenRouter "headline" prices are the cheapest endpoint, often a thin provider, so I give typical provider prices where they differ.
- ZDR (zero data retention) per model could not be verified. The per-model ZDR listing returned no ZDR flags, so every ZDR statement below is INFERRED or unknown.

## Q1 OpenRouter (id | context | in/out | tools/JSON | weights)

(a) Cheap extraction and classification:
- `openai/gpt-oss-20b` | 131K | 0.018/0.09 (most others 0.03/0.14) | tools and structured outputs | Apache 2.0. FOUND openrouter.ai/openai/gpt-oss-20b
- `openai/gpt-oss-120b` | 131K | 0.03/0.15 | native tools and structured output | open-weight. Bedrock is a listed provider. FOUND openrouter.ai/openai/gpt-oss-120b
- `deepseek/deepseek-v4.1-flash-1017` | 1.05M | 0.035/0.50 (DeepSeek direct 0.15/0.60) | tools and json_schema | MIT, 763B total. FOUND openrouter.ai/deepseek/deepseek-v4.1-flash-1017 and huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017. One fetch of the API list showed 0.15/0.60 with weekday overrides, so verify.
- `qwen/qwen3.6-35b-a3b` | 262K | headline 0.012/0.115, typical 0.10/0.90-1.00 | tools and structured output | Apache 2.0. FOUND openrouter.ai/models/qwen/qwen3.6-35b-a3b
- `qwen/qwen3.8-27b` | 1.05M | headline 0.004/0.229, typical 0.04/1.3-2.3 | tools/JSON not stated | Apache 2.0. FOUND huggingface.co/Qwen/Qwen3.8-27B
- `minimax/minimax-m3.1-flash` | 1.05M | headline 0.05/0.20 (one provider), typical 0.15/0.60 | tools and structured (API list) | open-weight, licence not stated.
- `mistralai/mistral-small-2603` (Small 4) | 262K | 0.15/0.60 | tools/JSON not stated | weights on Hugging Face.

(b) Long-context synthesis and reasoning:
- `moonshotai/kimi-k3.1-pro` | 1.05M | 2/10 | tools and structured (API list) | OpenRouter calls it open-weight, but the Hugging Face org page showed only Kimi-K3 (2.8T, 104B active, "Kimi K3 License"). Moonshot is the only provider, so K3.1 weights are UNVERIFIED.
- `moonshotai/kimi-k3` | 1M | providers mostly 3/15 (cheap tail 0.15/7.15) | tools/JSON not stated | open-weight. FOUND openrouter.ai/moonshotai/kimi-k3
- `deepseek/deepseek-v4-pro-0813` | 1.05M | DeepSeek 0.66/1.98, typical 1.3/2.6-3.96 | tools/JSON not stated | open weights (1.7T). No V4.1 Pro found on OpenRouter or Hugging Face, only V4.1 Flash.
- `z-ai/glm-5.3` | 1.05M | typical 1.40/4.40 | tools and json_schema | weights link, licence not stated. FOUND openrouter.ai/z-ai/glm-5.3
- `qwen/qwen3.8-2.4t-a95b` | 1M | 2/6 | not stated | open-weight, 95B active.
- `mistralai/mistral-large-4-0` | 1.05M | 0.70/2.10 | tools and structured | weights link, licence not stated.

(c) Coding:
- `meta/muse-spark-open` | 1.05M | 1.25/4.25 | not stated | open-weight, Meta's newest. FOUND openrouter.ai/meta/muse-spark-open. No current Llama appears on OpenRouter.
- Also strong candidates: kimi-k3.1-pro, glm-5.3, deepseek-v4.1-flash, `qwen/qwen3.6-27b` (262K, 0.20/3.00, Apache 2.0) and `mistralai/devstral-2512` (262K, 0.40/2, modified MIT).
- Qwen3.7 and Qwen3.8 Flash, Plus and Max (`qwen3.8-max-0902` 2/6, `qwen3.8-max-prime` 4/12) are not stated as open-weight. INFERRED: treat them as API-only.

OpenRouter controls (FOUND openrouter.ai/docs/features/provider-routing, /docs/guides/features/zdr, /docs/guides/features/guardrails):
- **Request-level provider settings:** `provider.data_collection:"deny"`, `provider.zdr:true`, `require_parameters:true`, `only`/`ignore`/`order`, `allow_fallbacks`, `sort`, and `max_price`.
- **JSON reliability:** tools and response_format are only soft preferences unless `require_parameters` is true.
- **Account ZDR:** toggles per model group. OpenRouter assumes an endpoint retains and trains if it cannot confirm otherwise.
- **ZDR endpoint list:** call `GET /api/v1/endpoints/zdr` with a key for the real per-endpoint list.
- **Key spend limit:** `POST /keys` takes `limit` (USD), `limit_reset` (daily/weekly/monthly, midnight UTC), `include_byok_in_limit` and `expires_at`. Guardrails add per-key and per-member budgets, and requests are rejected with HTTP 403 when a limit is hit.
- **EU routing:** `eu.openrouter.ai` needs a Business or Enterprise plan. The DeepSeek, Kimi and GLM pages say "not currently available through EU in-region routing".

## Q2 Embeddings (FOUND openrouter.ai/collections/embedding-models and Hugging Face cards)

- **On OpenRouter:**
  - `perplexity/pplx-embed-v1-0.6b` 0.004
  - `qwen/qwen3-embedding-8b` 0.01 (41K context)
  - `baai/bge-m3` 0.01 (1024 dims)
  - `qwen/qwen3-embedding-4b` 0.02
  - `openai/text-embedding-3-small` 0.02
  - `amazon/titan-embed-text-v2` 0.02 (1024 dims, 512/256 selectable, 8192 tokens)
  - `voyageai/voyage-4` 0.06
  - `mistralai/mistral-embed-2312` 0.10
- **Local on laptop CPU:**
  - Qwen3-Embedding-0.6B: Apache 2.0, 1024 dims (MRL 32-1024), 32K context, MTEB multilingual 64.33.
  - EmbeddingGemma-300m: Gemma licence (click-through), 768 dims (MRL 512/256/128), 2K context, MTEB multilingual 61.15.
  - nomic-embed-text-v1.5: Apache 2.0, about 137M parameters, 768 dims (MRL down to 64), 8192 context.
  - bge-small-en-v1.5: MIT, 33M parameters, 384 dims, 512 tokens.
- INFERRED: use one embedding model for both demo and production so vectors stay compatible. Qwen3-Embedding-0.6B served locally or on vLLM covers both. Titan V2 is the in-region managed alternative, with in-region London and Ireland availability FOUND on the Bedrock regional table.

## Q3 AWS Bedrock

- **Models listed** (FOUND docs.aws.amazon.com/bedrock/latest/userguide/model-cards.html): DeepSeek V3.2/V3.1/R1; Qwen3 (235B-2507, Next 80B, Coder, VL); gpt-oss-120b/20b; Llama 3.x and 4; Mistral Large 3 and Devstral 2; Kimi K3, K2.5 and K2 Thinking; MiniMax M2.5; GLM 5.3 and 5. No DeepSeek V4.x, Qwen3.6/3.8, MiniMax M3 or Kimi K3.1 are listed, so INFERRED: Bedrock lags OpenRouter by months.
- **London (eu-west-2) and Ireland (eu-west-1)**, from each model-card-*.html page:
  - `openai.gpt-oss-120b-1:0`: both, in-region, 128K.
  - `minimax.minimax-m2.5`: both, in-region, 196K.
  - `qwen.qwen3-next-80b-a3b`: both, in-region, 256K.
  - `qwen.qwen3-235b-a22b-2507-v1:0`: London on runtime; Ireland only on bedrock-mantle.
  - `deepseek.v3.2`, `moonshotai.kimi-k2.5`, `mistral.mistral-large-3-675b-instruct`: London in-region; Ireland not listed.
  - `moonshotai.kimi-k3` and `zai.glm-5.3`: only via `global.` profiles, with no EU geo profile, so data may leave the EU.
  - Llama 4 Maverick: US geo profile only.
- **London pricing is higher:** Qwen3 Next 0.23/1.86 (Ireland 0.18/1.41), MiniMax M2.5 0.47/1.86 (Ireland 0.36/1.44), GLM 5 1.55/4.96. Kimi K3 (global profile) is 3/15 and GLM 5.3 (global profile) is 1.68/5.28. FOUND aws.amazon.com/bedrock/pricing. London prices for gpt-oss and DeepSeek were not shown.
- **PrivateLink** (FOUND docs.aws.amazon.com/bedrock/latest/userguide/vpc-interface-endpoints.html): `com.amazonaws.<region>.bedrock`, `bedrock-runtime`, `bedrock-mantle`, `bedrock-agent` and `bedrock-agent-runtime`, with private DNS and endpoint policies.
- **Audit** (FOUND docs.aws.amazon.com/bedrock/latest/userguide/logging-using-cloudtrail.html and .../model-invocation-logging.html):
  - CloudTrail logs InvokeModel and Converse as management events by default.
  - Model invocation logging is off by default. It writes full prompts and responses to S3 or CloudWatch with caller ARN and requestMetadata.
  - It covers bedrock-runtime only, not bedrock-mantle.
- **Bedrock Access Gateway is DEPRECATED** and archived 4 Sep 2026 (FOUND github.com/aws-samples/bedrock-access-gateway). The replacement is the native OpenAI-compatible endpoint, `https://bedrock-mantle.{region}.api.aws/v1`, plus `bedrock-runtime.{region}.amazonaws.com/openai/v1`.
- **Self-host** (FOUND aws.github.io/deep-learning-containers/vllm/ and aws.amazon.com/blogs/machine-learning/announcing-openai-compatible-api-support-for-amazon-sagemaker-ai-endpoints/): the AWS vLLM container (`public.ecr.aws/deep-learning-containers/vllm:server-cuda`) runs on EC2/EKS (port 8000) and SageMaker (port 8080). It serves `/v1/chat/completions`, `/v1/embeddings` and `/v1/responses`. SageMaker endpoints have been OpenAI-compatible since 20 May 2026, at `runtime.sagemaker.<region>.amazonaws.com/endpoints/<name>/openai/v1`.

## Q4 Anthropic (FOUND platform.claude.com/docs/en/models/overview and /about-claude/pricing)

All models have 1M context and 128K output.

| Model id | In/out |
|---|---|
| `claude-haiku-5-5` | 0.10/0.50 up to 100K prompt (0.50/2.50 above) |
| `claude-sonnet-5-5` | 2/10 |
| `claude-opus-5-5` | 4/20 |
| `claude-fable-5-1` | 10/50 |

- Mythos 5.1 is also 10/50. Batch is 50% off, and Haiku cache hits are 0.01.
- **Claude on Bedrock in London: yes** (FOUND model-card-anthropic-claude-*-5-5.html). Opus 5.5 is in-region in eu-west-2. Sonnet 5.5 and Haiku 5.5 work via `eu.anthropic.claude-sonnet-5-5` and `eu.anthropic.claude-haiku-5-5`. London can route to eu-central-1, eu-north-1, eu-south-1/2 and eu-west-1/2/3, while Ireland does not route to London.

## Q5 Recommendation (INFERRED from the above)

| Stage | Demo (OpenRouter) | Production (AWS private) |
|---|---|---|
| Triage | `openai/gpt-oss-20b` | `openai.gpt-oss-120b-1:0` in London, or self-host gpt-oss-20b on vLLM |
| Extraction (JSON) | `openai/gpt-oss-120b` or `deepseek-v4.1-flash-1017`, with `require_parameters` | Bedrock gpt-oss-120b in London, with structured outputs |
| Clustering and labelling | Qwen3-Embedding-0.6B, plus `qwen/qwen3.6-35b-a3b` for labels | the same embedding model, plus `qwen.qwen3-next-80b-a3b` in London |
| Synthesis | `moonshotai/kimi-k3.1-pro` or `deepseek-v4-pro-0813`, with `anthropic/claude-sonnet-5.5` as the quality reference | `eu.anthropic.claude-sonnet-5-5` from London |
| Judge | `anthropic/claude-haiku-5.5` (different model family from the generator) | `eu.anthropic.claude-haiku-5-5` |

- **Demo setup:** set a key `limit` and `limit_reset`, and put `provider.zdr:true` in every request.
- **Production setup:** use a bedrock-runtime VPC endpoint, switch on invocation logging, and avoid bedrock-mantle for audited traffic until it is logged.
- **Open-model fallback in London:** DeepSeek V3.2, Qwen3-235B or Mistral Large 3 for synthesis.
- **Switching demo to production:** change the OpenAI-compatible base URL and keep a small eval set.

Not checked: Bedrock London prices for gpt-oss, DeepSeek V3.2 and Claude; per-model ZDR; Kimi K3.1 Pro licence and weights; OpenRouter tool and JSON support on pages that did not state it. Risk: this is a fast-moving market, and several OpenRouter prices were inconsistent between page views, so re-pull live prices before committing a budget.
