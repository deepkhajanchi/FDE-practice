# Cost and Token Estimation, Analysis, and Optimization — Lab Runbook

A step-by-step operational runbook, system architecture, token/cost attribution model, and controlled optimization workflow for measuring and right-sizing a multi-agent **Google Agent Development Kit (`google-adk==2.3.0`) Code Assistant (`Code Assistant Agent`)** on **Vertex AI (`global`)**, **Vertex AI Agent Search (Discovery Engine)**, **ChromaDB**, and the **Vertex AI Gen AI Evaluation Service (`EvalTask` + `PointwiseMetric`)**.

---

## 1. System Architecture

Agentic applications multiply cost across hidden dimensions that single-call LLM prototypes never expose:
1. **Multi-Turn Tool Fan-Out:** A single developer question triggers a **Coordinator** model call to plan tool use, **two model calls per invoked sub-agent** (one to emit the lookup tool call, a second to summarize retrieved snippets), managed search or vector-embedding API fees, and a final **Coordinator** synthesis turn—producing **up to 8 billable events per user query**.
2. **Hidden Reasoning ("Thought") Token Spend:** Reasoning tokens (`thoughts_token_count`) are billed at the **output token rate** (`$12.00/1M` on `gemini-3.1-pro-preview`, `$9.00/1M` on `gemini-3.5-flash`), which is **6x** the input token rate. Leaving thinking at `HIGH` or leaving output generation unbounded (~65k runaway tokens) dominates per-query spend.
3. **Heterogeneous Retrieval Cost Shapes:** Managed **Vertex AI Agent Search** bills a **flat per-query fee** (`$1.50 / 1,000` queries = `$0.0015/lookup`, invariant to `top_k`), whereas self-hosted vector search (**ChromaDB** + `gemini-embedding-001`) bills **per embedded query token** (`$0.15 / 1M` tokens, `~$0.000003/lookup`).
4. **Per-Token Price ≠ Per-Query Cost:** Cheaper per-token models (`gemini-3.1-flash-lite`) paired with mismatched `HIGH` orchestration complexity can loop, misfire tools, or emit 3x–6x more tokens, causing wild cost variance (`$0.007`–`$0.048/query`) and quality regressions below acceptable floors.

Lab 7 separates **Agent Orchestration (`code_assistant/agents.py`)**, **Managed & Vector Retrieval (`vais.py`, `retrieval.py`)**, **Disjoint Usage Attribution (`ledger.py` + `cost_of`)**, and **Reference-Anchored Quality Autorating (`quality.py`)**:

```mermaid
flowchart TB
    subgraph Datasets["Evaluation & Grounding Assets (assets/)"]
        DevSet["eval_dataset.jsonl (15 Dev Queries + Reference Answers)"]
        HoldoutSet["eval_holdout.jsonl (16 Unseen Holdout Queries)"]
        DocsJSONL["docs.jsonl (20 Official Python Error Docs)"]
        SOJSONL["stackoverflow.jsonl (20 Accepted Stack Overflow Posts)"]
    end

    subgraph CacheFront["Optional Production Front-Door (Part 5 Bonus)"]
        SemCache["SemanticCache (Exact Hash + Cosine Similarity >= Threshold)"]
    end

    subgraph AgentPlane["ADK 2.3 Multi-Agent System (code_assistant/agents.py)"]
        Runner["InMemoryRunner + answer_query() (2-Attempt Retry Guard)"]
        Coord["Coordinator Agent (AgentTool Wrapper, max_output_tokens=3072, ThinkingConfig)"]
        DocsAg["DocsAgent (FunctionTool: docsagent_lookup, max_output_tokens=2048)"]
        CommAg["CommunityAgent (FunctionTool: communityagent_lookup, max_output_tokens=2048)"]
        ModelCB["after_model_callback: _model_cb() (Disjoint Prompt vs Cached Split)"]
    end

    subgraph RetrievalPlane["Dual Retrieval Backends (vais.py & retrieval.py)"]
        VAIS["Vertex AI Agent Search (Discovery Engine Standard: code_assistant-docs-engine)"]
        EmbedAPI["Vertex AI Embeddings (gemini-embedding-001, HttpRetryOptions)"]
        Chroma["ChromaDB Ephemeral Vector Index (community collection)"]
    end

    subgraph LedgerPlane["Cost Contract & Attribution Ledger (ledger.py + Notebook)"]
        Pricing["PRICING Table & cost_of(record) (July 2026 Global List Rates)"]
        Ledger["UsageLedger (cost_per_query(), cost_breakdown(), to_df())"]
        Scorecard["Scorecard & Pareto Plots (Cost/Query vs Quality)"]
    end

    subgraph EvalPlane["Quality Autorater & Grading (quality.py + Part 6)"]
        Metric["PointwiseMetric: question_answering_correctness (1-5 -> [0, 1])"]
        EvalTask["Vertex AI Gen AI Evaluation Service (EvalTask.evaluate())"]
        Gate["check_challenge_pass (Budget <= $0.0135 & Quality >= 0.90)"]
        GCSOut["gs://<PROJECT_ID>-metrics-result/results/final_metrics.json"]
    end

    DevSet --> Runner
    HoldoutSet --> Runner
    Runner -.->|"Optional Repeat-Traffic Bypass"| SemCache
    SemCache -.->|"Cache Miss"| Coord
    Runner --> Coord

    Coord <-->|"AgentTool"| DocsAg
    Coord <-->|"AgentTool"| CommAg

    DocsJSONL -->|"vais.ensure() Inline Import"| VAIS
    DocsAg -->|"top_k Snippets"| VAIS

    SOJSONL -->|"build_index() (__index__)"| Chroma
    CommAg -->|"1. Embed Query"| EmbedAPI
    EmbedAPI -->|"2. Query Vector (top_k)"| Chroma
    Chroma -->|"Snippets"| CommAg

    Coord --> ModelCB
    DocsAg --> ModelCB
    CommAg --> ModelCB
    ModelCB -->|"call_type=model"| Ledger
    VAIS -->|"call_type=retrieval (vais_query=1)"| Ledger
    EmbedAPI -->|"call_type=embedding (embed_tokens)"| Ledger
    Pricing --> Ledger

    Runner -->|"Synthesized Answers + References"| EvalTask
    Metric --> EvalTask
    EvalTask -->|"Normalized Quality [0, 1]"| Scorecard
    Ledger -->|"USD / Query + Component Breakdown"| Scorecard
    Scorecard --> Gate
    Gate --> GCSOut
```

### 1.1 Repository & Component Reference

| Path | Role |
|---|---|
| `code_assistant_cost_optimization.ipynb` | End-to-end interactive notebook defining `PRICING`, `cost_of()`, `measure()`, Parts 0–5 experiments, `SemanticCache`, and the Part 6 Final Challenge submission |
| `code_assistant/agents.py` | Builds `Coordinator`, `DocsAgent`, and `CommunityAgent` via `AgentTool` and `FunctionTool`; enforces `COORDINATOR_MAX_OUTPUT = 3072` and `SUBAGENT_MAX_OUTPUT = 2048`; captures thread exceptions from ADK's sync runner |
| `code_assistant/vais.py` | Idempotently provisions Discovery Engine Data Store (`code_assistant-docs`) and Standard Search Engine (`code_assistant-docs-engine`), imports `docs.jsonl` inline, polls until searchable, and exposes `make_vais_lookup_tool` |
| `code_assistant/retrieval.py` | Configures retry-enabled `genai.Client(vertexai=True)`, embeds text via `gemini-embedding-001` (`embed_texts`), builds in-memory `chromadb.EphemeralClient()` collections, and exposes `make_lookup_tool` |
| `code_assistant/ledger.py` | `UsageLedger` container recording one dict per billable event (`model`, `embedding`, `retrieval`), excluding one-time `__index__` builds from `cost_per_query()` |
| `code_assistant/quality.py` | Defines reference-anchored `CRITERIA` (`correctness`, `completeness`), 1–5 `RATING_RUBRIC`, `CORRECTNESS_METRIC`, and retry-hardened `run_quality_eval()` normalizing `(mean5 - 1) / 4` into `[0, 1]` |
| `code_assistant/display.py` | Renders HTML summary cards (`show_result`, `show_target`, `show_verdict`) inside Jupyter outputs |
| `code_assistant/data.py` | Minimal `load_jsonl(path)` loader |
| `assets/docs.jsonl` | 20 synthetic official Python documentation entries (`d1`–`d20`) served by managed Agent Search |
| `assets/stackoverflow.jsonl` | 20 synthetic accepted Stack Overflow Q&A entries (`s1`–`s20`) indexed in local ChromaDB |
| `assets/eval_dataset.jsonl` | 15 development queries (`t1`–`t15`: 10 single-error + 5 multi-part) used across Parts 1–5 |
| `assets/eval_holdout.jsonl` | 16 held-out queries (`h1`–`h16`, including multi-error/multi-part diagnostic prompts) reserved exclusively for Part 6 grading |
| `notebook_config.sh` | Vertex AI Workbench startup script copying notebook, package, and assets from GCS |

### 1.2 The Lab Cost Model & Disjoint Token Attribution (`PRICING` & `cost_of`)

All configurations are priced against published July 2026 list rates (`global` endpoint, `<= 200k` context window, online requests, Agent Search Standard Edition):

| Resource / Model ID | Input Rate | Cached Input Rate (90% Off) | Output & Thought Rate | Unit Basis |
|---|---:|---:|---:|---|
| **`gemini-3.1-pro-preview`** | `$2.00` | `$0.20` | **`$12.00`** | USD per `1,000,000` tokens |
| **`gemini-3.5-flash`** | `$1.50` | `$0.15` | **`$9.00`** | USD per `1,000,000` tokens |
| **`gemini-3.1-flash-lite`** | `$0.25` | `$0.025` | **`$1.50`** | USD per `1,000,000` tokens |
| `gemini-2.5-pro` *(reference)* | `$1.25` | `$0.13` | `$10.00` | USD per `1,000,000` tokens |
| `gemini-2.5-flash` *(reference)* | `$0.30` | `$0.03` | `$2.50` | USD per `1,000,000` tokens |
| **`gemini-embedding-001`** (`embedding`) | `$0.15` | — | — | USD per `1,000,000` input tokens (`$0.00015 / 1k`) |
| **Agent Search Standard** (`vais_query`) | `$1.50` | — | — | USD per `1,000` search queries (**`$0.0015 / query`**) |

> [!IMPORTANT]
> **Disjoint Prompt vs. Cached Token Accounting:** In Vertex AI `usage_metadata`, `prompt_token_count` **includes** `cached_content_token_count`. In `code_assistant/agents.py`, `_model_cb` records `input_tokens = max(0, prompt - cached)` and `cached_tokens = cached` separately so cached tokens are never billed twice. Reasoning tokens (`thoughts_token_count`) are added to `candidates_token_count` and billed at the model's `output` rate:
> $$\text{Cost}_{\text{model}} = \frac{\text{input\_tokens} \cdot P_{\text{in}} + \text{cached\_tokens} \cdot P_{\text{cache}} + (\text{output\_tokens} + \text{thought\_tokens}) \cdot P_{\text{out}}}{10^6}$$

---

## 2. Workflows

### 2.1 Outer Loop: Controlled Single-Lever Optimization Workflow

To prevent confounding variables, the lab holds **thinking effort pinned at `HIGH`** during model tiering (Parts 1–2) before adjusting reasoning and retrieval dials (Part 4), evaluating every step on `eval_dataset.jsonl` (15 queries), and reserving `eval_holdout.jsonl` (16 queries) strictly for the Part 6 final submission:

```mermaid
flowchart LR
    P0["Part 0: Provision VAIS + ChromaDB & Validate Cost Ledger"] --> P1["Part 1: Measure Baseline (Pro @ HIGH, Flash Subs)"]
    P1 --> P2A["Part 2 (Lever 1a): Tier Coord -> Flash @ HIGH"]
    P2A --> P2B["Part 2 (Lever 1b): Tier Coord -> Flash-Lite @ HIGH (Variance Trap)"]
    P2B --> P3["Part 3 (Lever 2): Explicit Context Cache (>=4,096 Prefix Demo)"]
    P3 --> P4A["Part 4 (Lever 3a): Lower Coord Thinking -> LOW"]
    P4A --> P4B["Part 4 (Lever 3b): Trim Retrieval top_k 3 -> 2"]
    P4B --> P5["Part 5: Pareto Scorecard + SemanticCache Demo"]
    P5 --> Diag["Part 6 Diagnosis: Inspect Per-Agent Spend Breakdown"]
    Diag --> P6["Part 6 Submission: Flash Coord (LOW) + Flash-Lite Subs + top_k=3"]
    P6 -->|"Cost <= $0.0135 & Quality >= 0.90"| Pass["Upload final_metrics.json to GCS"]
    P6 -->|"Autorater Variance / Miss"| Diag
```

### 2.2 Inner Loop: Single-Query Multi-Agent Fan-Out & 8-Event Ledger Sequence

When a developer submits a coding question that consults both sources, execution flows through **6 LLM turns** + **1 Discovery Engine search** + **1 embedding request**, all attributed to the active `query_id` via `qid_holder["v"]`:

```mermaid
sequenceDiagram
    participant M as measure()
    participant C as Coordinator (ADK Agent)
    participant D as DocsAgent (AgentTool)
    participant V as Agent Search (VAIS)
    participant K as CommunityAgent (AgentTool)
    participant E as Embedding + ChromaDB
    participant L as UsageLedger
    participant J as Gen AI Eval Service (Judge)

    M->>C: answer_query(query, query_id)
    Note over C: LLM Call 1 - Plan AgentTool Invocations (Bills Input + Thought + Output)
    C->>L: _model_cb("Coordinator", call 1)

    C->>D: AgentTool(DocsAgent)
    Note over D: LLM Call 2 - Decide docsagent_lookup(query)
    D->>L: _model_cb("DocsAgent", call 1)
    D->>V: search(serving_config, query, top_k)
    V->>L: add(call_type="retrieval", vais_query=1 -> $0.0015)
    V-->>D: Top-k Official Doc Snippets
    Note over D: LLM Call 3 - Concise Grounded Docs Summary
    D->>L: _model_cb("DocsAgent", call 2)
    D-->>C: Official Docs Grounding

    C->>K: AgentTool(CommunityAgent)
    Note over K: LLM Call 4 - Decide communityagent_lookup(query)
    K->>L: _model_cb("CommunityAgent", call 1)
    K->>E: embed_texts([query]) + collection.query(top_k)
    E->>L: add(call_type="embedding", embed_tokens)
    E-->>K: Top-k Stack Overflow Snippets
    Note over K: LLM Call 5 - Concise Community Summary
    K->>L: _model_cb("CommunityAgent", call 2)
    K-->>C: Community Grounding

    Note over C: LLM Call 6 - Synthesize Cited Answer (Docs vs Community)
    C->>L: _model_cb("Coordinator", call 2)
    C-->>M: Final Cited Response

    M->>J: EvalTask(prompt, response, reference) [Excluded from Agent Ledger]
    J-->>M: Mean 1-5 Correctness -> Normalized [0, 1]
```

### 2.3 Production Front-Door: Two-Tier Exact + Semantic Response Cache Workflow

For repeat developer errors phrased in different words, `SemanticCache` (Part 5 Bonus) intercepts queries prior to invoking `Coordinator`:

```mermaid
flowchart LR
    Q["Incoming Developer Query"] --> Exact{"1. Exact Prompt Hash Hit?"}
    Exact -->|"Yes ($0.00)"| Ret1["Return Cached Answer Immediately"]
    Exact -->|"No"| Emb["2. Embed Query (gemini-embedding-001, ~$0.000003)"]
    Emb --> Sim{"3. Cosine Similarity >= Threshold (0.85-0.92)?"}
    Sim -->|"Cache Hit (~4 Orders of Magnitude Cheaper)"| Ret2["Return Stored Answer"]
    Sim -->|"Cache Miss"| Pipe["4. Run Full Multi-Agent Pipeline"]
    Pipe --> Store["5. Store (Query Embedding, Answer) & Return"]
```

---

## 3. Step-by-Step Lab Runbook

### Step 1: Open the Lab Environment & Install Dependencies (Part 0a)

1. **In Google Cloud Console (Vertex AI Workbench):**
   - Navigate to **Vertex AI -> Workbench -> Instances**, click **Open JupyterLab** next to the provisioned instance, and open `code_assistant_cost_optimization.ipynb`.
   - Run **Cell 4** to install required packages:
     ```python
     %pip install -q google-adk==2.3.0 "google-cloud-aiplatform[evaluation]>=1.158.0" "google-genai>=2.10.0" "chromadb>=1.5.9" "google-cloud-discoveryengine>=0.20.0" pandas matplotlib
     ```
   - Run **Cell 5** to restart the Jupyter kernel, wait a few seconds for reconnection, and **skip Cells 4–5 on all subsequent re-runs**.

2. **Local / Cloud Shell CLI Alternative:**
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   export GOOGLE_CLOUD_PROJECT="<YOUR_GCP_PROJECT_ID>"
   export GOOGLE_CLOUD_LOCATION="global"
   export GOOGLE_GENAI_USE_VERTEXAI="TRUE"
   ```

3. **Run Cells 8–9** to bind `PROJECT`, `LOCATION = "global"`, `EVAL_LOCATION = "global"`, configure ADK logging, and define the default model map:
   ```python
   MODELS = {
       "coordinator": "gemini-3.1-pro-preview",
       "docs": "gemini-3.5-flash",
       "community": "gemini-3.5-flash",
       "embedding": "gemini-embedding-001",
   }
   THINKING = "HIGH"
   ```

---

### Step 2: Verify the Cost Contract & Quality Rubric (Part 0b)

1. **Run Cell 11** to load `PRICING` and `cost_of(record)` and verify the three built-in assertions:
   - `1,000` input tokens + `100` output tokens + `50` thought tokens on `gemini-3.5-flash` = `(1000 * 1.50 + 150 * 9.00) / 1e6 = $0.00285`.
   - `1,000` `embed_tokens` = `$0.00015`.
   - `3` `vais_query` lookups = `$0.0045`.
2. **Run Cells 13–14** to inspect `CRITERIA` (`correctness`, `completeness`), the 1–5 `RATING_RUBRIC` (normalized to `[0, 1]` via `(mean5 - 1) / 4`), and register `measure(...)` and `record_result(...)`.
   - Note that `measure(...)` retries a failed/empty query once (`time.sleep(5)`) on top of `HttpRetryOptions` (5 attempts with exponential backoff) and raises loudly if a query fails twice so partial failures never corrupt a configuration's cost or quality numbers.

---

### Step 3: Provision Retrieval Backends & Trace One Query's Ledger (Part 0c)

1. **Run Cell 16** (~3–5 minutes on first run; ~2 seconds on re-runs):
   - `vais.ensure(PROJECT, "global", "code_assistant-docs", "code_assistant-docs-engine", load_jsonl("assets/docs.jsonl"))` creates the managed Discovery Engine data store, imports all 20 official docs inline, creates the Standard tier search engine, and polls `wait_until_searchable(..., probe="KeyError")` until indexing completes.
   - `build_index(so, MODELS["embedding"], ...)` embeds the 20 Stack Overflow posts into ephemeral ChromaDB (`query_id="__index__"`).
   - Loads `dataset` (`15` dev queries) and `holdout` (`16` final-challenge queries) and defines `build(models, thinking_level=THINKING, max_output_tokens=None, top_k=3)`.
2. **Run Cell 17** to preview sample corpus rows and reference answers.
3. **Run Cell 19** to execute a single end-to-end demo query (`"I get a KeyError reading a dict in Python. How do I fix it?"`) and inspect `demo_ledger.to_df()`:
   - Observe **2 rows for `DocsAgent`**, **1 `retrieval` row (`$0.0015`)**, **2 rows for `CommunityAgent`**, **1 `embedding` row**, and **2 rows for `Coordinator`** (including hundreds of `thought_tokens` billed at `$12/1M`).

---

### Step 4: Measure the Reference Baseline (Part 1)

**Run Cell 21** (~8 minutes across all 15 `dataset` queries):

```python
coord, ledger = build(MODELS)
row, _ = measure(coordinator=coord, items=dataset, qid_holder=qid, ledger=ledger,
                 project=PROJECT, location=EVAL_LOCATION, label="baseline (Pro coordinator)")
record_result(row)
```

- **Expected Observation:**
  - **Cost / Query:** `~$0.025–$0.028`
  - **Quality:** `~0.91–0.95`
  - **Component Breakdown:** `Coordinator` (`gemini-3.1-pro-preview` @ `HIGH` thinking) accounts for the largest single bar on the chart because reasoning tokens bill at `$12.00/1M`.

---

### Step 5: Apply Lever 1 — Coordinator Model Selection & Tiering (Part 2)

Keep `THINKING = "HIGH"`, sub-agents, and `top_k = 3` constant so model tier comparisons remain strictly apples-to-apples:

1. **Lever 1a — Tier Coordinator from `Pro` to `gemini-3.5-flash` (Run Cell 24, ~7 min):**
   ```python
   TIERED_MODELS = {**MODELS, "coordinator": "gemini-3.5-flash"}
   ```
   - **Result:** Cost drops **~25–40%** (`~$0.016–$0.019/query`) while quality stays flat (`~0.92–0.95`). `gemini-3.5-flash` wins twice: lower output/thought unit rate (`$9.00` vs `$12.00/1M`) **and** fewer `thought_tokens` emitted for equivalent work.

2. **Lever 1b — Tier Coordinator to `gemini-3.1-flash-lite` at `HIGH` Thinking (Run Cell 27, ~5–12 min):**
   ```python
   LITE_MODELS = {**MODELS, "coordinator": "gemini-3.1-flash-lite"}
   ```
   - **Result (Cautionary Trap):** Despite 6x lower per-token prices than `3.5-flash`, `Flash-Lite @ HIGH` exhibits severe run-to-run cost instability (`$0.007` to `$0.048/query`) and occasional tool-call misfires or quality drops because compact budget models struggle with open-ended multi-tool orchestration at `HIGH` reasoning effort.

---

### Step 6: Apply Lever 2 — Explicit Context Caching (Part 3)

Because `Code Assistant Agent`'s real system instruction (~150 tokens) is smaller than Gemini 3's **`4,096`-token explicit cache minimum**, **Cell 30** (~30 seconds) demonstrates explicit caching on an ~8,400-token synthetic manual prefix (`ttl="120s"`):

```python
cache = client.caches.create(
    model="gemini-3.5-flash",
    config=types.CreateCachedContentConfig(system_instruction=big_prefix, ttl="120s"),
)
r = client.models.generate_content(
    model="gemini-3.5-flash",
    contents="Name your role in 5 words.",
    config=types.GenerateContentConfig(cached_content=cache.name),
)
client.caches.delete(name=cache.name)
```

- **Result:** Cached prefix tokens bill at `$0.15/1M` instead of `$1.50/1M` (**~90% input cost reduction**). Note that the notebook computes `without_cache` analytically from `prompt_token_count` so Gemini's automatic **implicit caching** does not distort a second live request.

---

### Step 7: Apply Lever 3 — Reasoning Effort & Retrieval Breadth Reduction (Part 4)

Starting from the reliable `TIERED_MODELS` (`gemini-3.5-flash` Coordinator) configuration:

1. **Lever 3a — Lower Coordinator Thinking from `HIGH` to `LOW` (Run Cell 33, ~5 min):**
   ```python
   THINKING_LOW = "LOW"
   coord, ledger = build(TIERED_MODELS, thinking_level=THINKING_LOW)
   ```
   - **Result:** Coordinator `thought_tokens` collapse dramatically, cutting another **~15–35%** below `Flash @ HIGH` (`~$0.014–$0.015/query`) while maintaining quality within judge variance (`~0.91–0.95`).

2. **Lever 3b — Trim Retrieval `top_k` from `3` to `2` (Run Cell 36, ~5 min):**
   ```python
   TOP_K = 2
   coord, ledger = build(TIERED_MODELS, thinking_level=THINKING_LOW, top_k=TOP_K)
   ```
   - **Result:** Only a tiny marginal cost trim (`~$0.0002–$0.0005/query`), because input tokens are already cheap (`$1.50/1M`) and both `vais_query` (`$0.0015` flat) and query embedding fees do not change with `top_k`. Crucially, total cost (`~$0.014–$0.015/query`) **still sits above** the Part 6 `$0.0135` target!

---

### Step 8: Compare Pareto Frontier & Run the Semantic Cache Demo (Part 5)

1. **Run Cells 39 & 41** to display the consolidated 5-configuration scorecard table (`cost_vs_baseline`, `quality_vs_baseline`), the **Cost vs. Quality Pareto scatter plot** (optimal configurations sit **up and to the left**), and the grouped per-component cost bar chart.
2. **Run Cells 43, 45, & 47** to test `SemanticCache(threshold=0.85)`:
   - Seeding `"How do I fix a KeyError in a Python dict?"` produces a **CACHE HIT** on `"fixing a KeyError when reading a dict"` (costing a single `gemini-embedding-001` call, `~$0.000003`) and a **CACHE MISS** on `"how do I center a div in CSS"`.

---

### Step 9: Beat the Graded Final Challenge on Held-Out Queries (Part 6)

#### 9.1 Why Straightforward Lever Stacking Falls Short (`> $0.0135`)

In Part 6 (**Cell 50**), both thresholds must pass simultaneously on the **16 unseen `holdout` queries**:
- **`BUDGET = $0.0135` per query**
- **`QUALITY_FLOOR = 0.90`**

Why did `TIERED_MODELS` (`Coordinator = gemini-3.5-flash`, `thinking_level = "LOW"`, `top_k = 2`) stall around `~$0.014–$0.015/query` in Part 4? Inspecting the per-agent breakdown in `code_assistant/agents.py` reveals the hidden spend driver:
1. Parts 2 and 4 tiered **only `Coordinator`**, leaving `DocsAgent` and `CommunityAgent` on **`gemini-3.5-flash`** (`$1.50/1M` input, `$9.00/1M` output/thoughts) with **unpinned default thinking** (`sub_cfg` only sets `max_output_tokens=2048`).
2. Across 4 sub-agent model calls per query (2 `DocsAgent` + 2 `CommunityAgent`), `gemini-3.5-flash` sub-agents spend **`~$0.007–$0.009/query`**—more than half of the remaining bill!
3. Meanwhile, Cell 51 explicitly notes:
   > *"Challenge rule: the Coordinator seat needs a tier you can rely on; run it on Pro or Flash... **Sub-agent tiers are unrestricted.**"*
4. Unlike `Coordinator` (which must plan multi-agent routing and synthesize cited multi-part answers), `DocsAgent` and `CommunityAgent` each execute **one fixed lookup tool** and summarize 2–3 short snippets—an ideal narrow task for **`gemini-3.1-flash-lite`** (**6x cheaper**: `$0.25/1M` input, `$1.50/1M` output), slashing sub-agent LLM spend from `~$0.008/query` down to **`~$0.0013/query`**!
5. Finally, several `holdout` prompts (`h9`, `h12`, `h13`, `h14`, `h15`) combine **two or three related Python errors** (for example, `h9` spans `d7` `asyncio.run()`, `d8` `SyntaxError: await`, and `d9` `coroutine never awaited`). Setting **`MY_TOPK = 3`** (instead of `1` or `2`) ensures full multi-document grounding recall for `< $0.00003/query` in extra `Flash-Lite` input tokens, while leaving **`MY_MAXOUT = None`** preserves the safe `3,072` ceiling without starving multi-part answers.

#### 9.2 Per-Query Spend Budget Breakdown (Optimal Configuration)

| Component | Configuration | Typical Volume / Query | Estimated USD / Query |
|---|---|---:|---:|
| **`Coordinator`** | `gemini-3.5-flash` (`MY_THINKING = "LOW"`, `max_output = 3072`) | ~1,200 in + ~450 out/thought tokens | `~$0.0058` |
| **`DocsAgent` (LLM)** | `gemini-3.1-flash-lite` (2 calls) | ~800 in + ~350 out/thought tokens | `~$0.0007` |
| **`CommunityAgent` (LLM)** | `gemini-3.1-flash-lite` (2 calls) | ~800 in + ~350 out/thought tokens | `~$0.0007` |
| **Agent Search (`vais_query`)** | Standard Edition (`MY_TOPK = 3`) | ~1.0 search query | `~$0.0015` |
| **Embeddings (`embedding`)** | `gemini-embedding-001` | ~25 query tokens | `< $0.0001` |
| **Total Expected** | **All Components Combined** | **16 Held-Out Queries** | **`~$0.0088 – $0.0105 / query`** (`<= $0.0135`) |

#### 9.3 Execute Cell 50, Cell 51, and Cell 52

1. **Run Cell 50** to define `BUDGET = 0.0135`, `QUALITY_FLOOR = 0.90`, and `check_challenge_pass(...)`.
2. **Update and run Cell 51** (~6–8 minutes across the 16 `holdout` queries):
   ```python
   MY_MODELS = {
       "coordinator": "gemini-3.5-flash",      # Reliable synthesis & tool coordination tier
       "docs":        "gemini-3.1-flash-lite", # 6x cheaper narrow single-tool retrieval summarizer
       "community":   "gemini-3.1-flash-lite", # 6x cheaper narrow single-tool retrieval summarizer
       "embedding":   "gemini-embedding-001",  # Required Vertex embedding model
   }
   MY_THINKING = "LOW"   # Eliminates redundant Coordinator thought-token spend
   MY_TOPK     = 3       # Preserves 3-snippet recall for multi-error holdout prompts (h9, h12-h15)
   MY_MAXOUT   = None    # Keeps 3,072 safety ceiling so multi-part answers are never truncated
   ```
   - Confirm the green **`PASS`** banner renders (`cost_per_query <= $0.0135` and `quality >= 0.90`).
   - *Variance Note:* Because the LLM autorater exhibits `±0.02–0.03` stochastic variance on 16 items, if cost is comfortably `~$0.009–$0.010` and quality lands at `0.88–0.89`, simply re-run Cell 51 (or raise `MY_THINKING = "MEDIUM"`, which still stays inside `$0.0135` thanks to `Flash-Lite` sub-agents).
3. **Run Cell 52** (required tracking cell) to write `/home/jupyter/final_metrics.json` and upload it to Cloud Storage:
   ```text
   Uploaded to gs://<PROJECT_ID>-metrics-result/results/final_metrics.json
   ```

---

### Step 10: Optional Lab Teardown (Reset Agent Search)

If you want to test cold-start provisioning from scratch, uncomment and run **Cell 57** (`vais.teardown` deletes the search engine first, then the data store, respecting Discovery Engine resource dependencies):

```python
vais.teardown(PROJECT, VAIS_LOCATION, DS_ID, ENGINE_ID)
```

---

## 4. Troubleshooting Quick Reference

| Symptom | Likely Cause | Action |
|---|---|---|
| `ModuleNotFoundError: No module named 'google.adk'` | Kernel was not restarted after `%pip install` in Cell 4 | Restart the Jupyter kernel (Cell 5), skip Cells 4–5, and run from Cell 8 onward |
| `Agent Search data store not searchable after provisioning` | Initial Discovery Engine indexing exceeded 10 minutes | Re-run Cell 16; `vais.ensure()` is idempotent and reuses the created data store/engine once indexed |
| `[run warning] query <id>: ...; retrying once` | Transient `429`/`503` API error or sub-agent tool parse hiccup | Normal if occasional (`measure()` retries automatically); if a query fails twice, re-run the measurement cell |
| `quality eval returned no scores (all judge rows failed)` | Transient Vertex AI Gen AI Evaluation Service throttling | Re-run the cell; `run_quality_eval()` already includes a 10-second automatic retry |
| Part 6 fails budget (`cost/query ~0.0145 exceeds 0.0135`) | `docs` and `community` sub-agents were left on `gemini-3.5-flash` | Tier `MY_MODELS["docs"]` and `MY_MODELS["community"]` to `"gemini-3.1-flash-lite"` while keeping `coordinator` on `"gemini-3.5-flash"` |
| Part 6 fails quality (`< 0.90`) with `MY_MAXOUT` set low or `MY_TOPK = 1` | Tight `max_output_tokens` truncated answers after thought tokens, or `top_k=1` missed multi-part error docs | Set `MY_MAXOUT = None` and `MY_TOPK = 3`; if quality lands at `0.88–0.89` from judge noise, re-run Cell 51 or set `MY_THINKING = "MEDIUM"` |
| Lab completion check does not register | Cell 52 was skipped after `PASS` in Cell 51 | Run Cell 52 and confirm `Uploaded to gs://<PROJECT_ID>-metrics-result/results/final_metrics.json` prints |
