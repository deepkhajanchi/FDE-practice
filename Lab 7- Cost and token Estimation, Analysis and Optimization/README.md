# Lab 7 — Cost and Token Estimation, Analysis, and Optimization

Measuring, attributing, and optimizing per-query cost and answer quality for a multi-agent **Google ADK (`google-adk==2.3.0`) Code Assistant (`Code Assistant Agent`)** backed by **Vertex AI Gemini 3 models (`global`)**, **Vertex AI Agent Search (Discovery Engine)**, **ChromaDB + `gemini-embedding-001`**, and a **Vertex AI Gen AI Evaluation Service (`PointwiseMetric`)** autorater.

See **[`RUNBOOK.md`](./RUNBOOK.md)** for the full system architecture diagram, multi-agent & ledger attribution workflows, July 2026 cost-model math, lever-by-lever analysis, Part 6 Final Challenge solution (`<= $0.0135/query` at `>= 0.90` quality), and troubleshooting reference.

---

## Architecture & Optimization Stack Summary

| Layer | Technology / Module | Primary Entry Point | Role in Cost-Quality Pipeline |
|---|---|---|---|
| **Coordinator Agent** | **Google ADK 2.3 (`Agent` + `AgentTool`)** | `code_assistant/agents.py` | Orchestrates sub-agents as tools so control returns for cited synthesis; caps output (`3,072` ceiling) and pins `ThinkingConfig(thinking_level=...)` |
| **Docs Sub-Agent & Managed Search** | **ADK `FunctionTool` + Discovery Engine (`vais_query`)** | `code_assistant/vais.py` | Queries managed **Agent Search** (`code_assistant-docs-engine` over `assets/docs.jsonl`), billing a flat **`$1.50 / 1,000` queries (`$0.0015/lookup`)** |
| **Community Sub-Agent & Vector Store** | **ADK `FunctionTool` + ChromaDB + `gemini-embedding-001`** | `code_assistant/retrieval.py` | Embeds lookup queries (`$0.15 / 1M` input tokens) and searches 20 Stack Overflow Q&A posts (`assets/stackoverflow.jsonl`) in ephemeral ChromaDB |
| **Usage & Cost Attribution Ledger** | **Disjoint Event Ledger (`UsageLedger` + `cost_of`)** | `code_assistant/ledger.py`, `code_assistant_cost_optimization.ipynb` | Captures every LLM turn (`after_model_callback`), query embedding, and Agent Search call, pricing disjoint `input`, `cached`, `output + thought`, `embed`, and `vais_query` units |
| **Reference-Anchored Quality Judge** | **Vertex AI Gen AI Evaluation Service (`EvalTask`)** | `code_assistant/quality.py` | Scores answers `1`–`5` (normalized to `[0, 1]`) on `correctness` and `completeness` against reference answers in `eval_dataset.jsonl` (15) and `eval_holdout.jsonl` (16) |
| **Caching & Optimization Notebook** | **Explicit Context Cache + `SemanticCache` + Pareto Scorecard** | `code_assistant_cost_optimization.ipynb` | Walks through Baseline, Model Tiering, Context Caching, Thinking/Retrieval Reduction, Semantic Response Caching, and the Held-Out Final Challenge |

---

## Directory Layout

```text
Lab 7- Cost and token Estimation, Analysis and Optimization/
├── RUNBOOK.md                              # Step-by-step runbook, Mermaid architecture & workflow diagrams
├── README.md                               # Stack summary, directory layout & quick verification commands
├── .gitignore                              # Excludes .venv, __pycache__, checkpoints & scratch metrics
├── requirements.txt                        # google-adk==2.3.0, vertexai[evaluation], discoveryengine, chromadb
├── code_assistant_cost_optimization.ipynb  # End-to-end Parts 0–6 lab notebook (with Final Challenge config)
├── notebook_config.sh                      # Sanitized Vertex AI Workbench startup staging script
├── code_assistant/                         # Tested multi-agent, retrieval, ledger & evaluation package
│   ├── __init__.py                         # Package docstring
│   ├── agents.py                           # build_code_assistant(), _model_cb(), answer_query() & retry hooks
│   ├── vais.py                             # Managed Agent Search ensure(), provision(), search(), teardown()
│   ├── retrieval.py                        # genai_client(), embed_texts(), ChromaDB build_index() & lookup tool
│   ├── ledger.py                           # UsageLedger (per-event cost_fn, cost_per_query, cost_breakdown)
│   ├── quality.py                          # CRITERIA, RATING_RUBRIC, CORRECTNESS_METRIC & run_quality_eval()
│   ├── display.py                          # HTML scorecard banners (show_result, show_target, show_verdict)
│   └── data.py                             # load_jsonl() helper
└── assets/                                 # Grounding corpora & reference-anchored evaluation sets
    ├── docs.jsonl                          # 20 official Python error documentation notes (d1–d20)
    ├── stackoverflow.jsonl                 # 20 accepted community Stack Overflow Q&A posts (s1–s20)
    ├── eval_dataset.jsonl                  # 15 development queries (t1–t15) for Parts 1–5
    └── eval_holdout.jsonl                  # 16 unseen multi-part holdout queries (h1–h16) for Part 6 grading
```

---

## Optimization Levers at a Glance

| Lever | Notebook Section | Primary Mechanism | Cost Impact | Quality Trade-Off |
|---|---|---|---|---|
| **Baseline** | Part 1 | `gemini-3.1-pro-preview` Coordinator (`HIGH`), `gemini-3.5-flash` Sub-Agents, `top_k=3` | `~$0.026 / query` | Reference quality (`~0.92–0.95`) |
| **Lever 1a: Coordinator Tiering (Flash)** | Part 2 | Tier Coordinator `Pro` -> `gemini-3.5-flash` (keep `HIGH` thinking) | **~25–40% lower** | **Free win** (holds baseline quality) |
| **Lever 1b: Coordinator Tiering (Flash-Lite)** | Part 2 | Tier Coordinator -> `gemini-3.1-flash-lite` at `HIGH` thinking | Unstable (`$0.007–$0.048`) | **Trap:** erratic reasoning & tool loops |
| **Lever 2: Explicit Context Caching** | Part 3 | `client.caches.create` on stable prefix (`>= 4,096` tokens) | **~90% off cached input** | Zero quality loss (requires large prefix) |
| **Lever 3a: Reasoning Effort (`LOW`)** | Part 4 | Pin `thinking_level="LOW"` on `gemini-3.5-flash` Coordinator | **~15–35% lower** vs 1a | Within autorater noise (`±0.02–0.03`) |
| **Lever 3b: Retrieval Trim (`top_k=2`)** | Part 4 | Reduce snippets from `3` -> `2` | Marginal (`vais_query` is flat) | Slight context loss on multi-part queries |
| **Bonus: Semantic Response Cache** | Part 5 | Embed incoming query + cosine match (`threshold=0.85–0.92`) | **~99.9% off cache hits** | Threshold controls false-hit risk |
| **Part 6: Multi-Tier Architecture** | Part 6 | `gemini-3.5-flash` Coordinator (`LOW`) + **`gemini-3.1-flash-lite` Sub-Agents** + `top_k=3` | **`~$0.009–$0.010 / query`** (`<= $0.0135`) | **`>= 0.90`** on 16 unseen holdout queries |

---

## Quick Setup & Verification

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Sanity-check package imports & cost ledger math offline
.venv/bin/python -c "
from code_assistant.ledger import UsageLedger
from code_assistant.quality import CRITERIA, RATING_RUBRIC
L = UsageLedger(lambda r: (r['input_tokens']*1.5 + (r['output_tokens']+r['thought_tokens'])*9.0)/1e6)
L.add(query_id='q1', agent='Coordinator', call_type='model', input_tokens=1000, output_tokens=100, thought_tokens=50)
assert L.cost_per_query() == 0.00285
print('Ledger & rubric imports OK:', list(CRITERIA.keys()), len(RATING_RUBRIC), 'levels')
"
```

---

## Official References

- [Vertex AI Gemini Model Pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing)
- [Vertex AI Context Caching Overview](https://cloud.google.com/vertex-ai/generative-ai/docs/context-cache/context-cache-overview)
- [Google Agent Development Kit (ADK) Documentation](https://google.github.io/adk-docs/)
- [Vertex AI Gen AI Evaluation Service Overview](https://cloud.google.com/vertex-ai/generative-ai/docs/models/evaluation-overview)
- [Vertex AI Agent Builder / Agent Search Pricing](https://cloud.google.com/generative-ai-app-builder/pricing)
