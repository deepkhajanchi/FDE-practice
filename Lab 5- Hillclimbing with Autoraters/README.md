# Lab 5 — Hillclimbing with Autoraters

Evaluating, statistically auditing, and hill-climbing a **Google ADK 2.4 Real Estate Investment Opportunity Analysis Agent (`re_analyst`)** using custom **Pointwise LLM-as-a-Judge Autoraters** on the **Vertex AI GenAI Evaluation Service (`GEAP`)** and **Krippendorff's Alpha (`α`)** inter-rater agreement analysis.

See **[`RUNBOOK.md`](./RUNBOOK.md)** for the full system architecture diagram, end-to-end outer/inner workflows, 19-criterion statistical audit table, and step-by-step operational runbook.

---

## Architecture & Evaluation Stack Summary

| Layer | Technology / Module | Primary Entry Point | Role in Hill-Climbing Pipeline |
|---|---|---|---|
| **Agent Under Test** | **Google ADK 2.4 (`SkillToolset` + `FunctionTool`)** | `re_analyst/agent.py` | Generates 5-section Markdown investment memoranda (`gemini-3.5-flash` on Vertex AI `global`) using `analyze-opportunity`, `analyze-flood-risk`, and `analyze-tax-implications` skills |
| **County Data Layer** | **In-Memory JSON Stores** | `re_analyst/tools/lot_tool.py`, `tax_tool.py` | Serves 63 land parcels (`lots_database.json` with `adjacent_parcels` graph) and 60 official APN assessments (`tax_database.json`) |
| **Trace & Dataset Builder** | **ADK Evaluation Generator (`EvalSet`)** | `eval_harness/create_re_agent_evalset.py` | Runs `re_analyst` concurrently (`max_concurrency=10`) over target Lot IDs and exports ADK 2.0 `.evalset.json` traces |
| **Cloud Autorater Runner** | **Vertex AI GenAI Evaluation Service (`GEAP`)** | `eval_harness/run_geap_eval.py` | Compiles `rubrics.json` into `PointwiseMetricPromptTemplate` + `PointwiseMetric` and runs `k` stochastic passes (`gemini-2.5-flash`, `sampling_count=4`) in `us-central1` |
| **Statistical Reliability Engine** | **Pandas + `krippendorff-aleph-alpha`** | `eval_harness/all_criteria_analysis.py`, `single_criterion_analysis.py`, `explain_criteria_results.py` | Pivots $N \times k$ grades matrices to compute Mean, `sd_report_means`, Pairwise `%_agree`, and interval **Krippendorff's Alpha (`α`)**, separating reliable BARS rubrics from ceiling-saturated or vague rubrics |
| **Hill-Climbing Harness** | **Auto-Versioned Iteration Runner** | `eval_harness/run_hillclimb.py` | Executes `re_analyst` across 10 edge-case lots (`hillclimb_lots.txt`) and tracks versioned score progression (`runs/hillclimb_1/`, `runs/hillclimb_2/`, ...) on `cost-per-acre` and `neighboring-flood-risk` |

---

## Directory Layout

```text
Lab 5- Hillclimbing with Autoraters/
├── RUNBOOK.md                              # Step-by-step lab runbook, architecture & workflow diagrams
├── README.md                               # Stack summary, directory layout & quick verification commands
├── .gitignore                              # Excludes .env, .venv, .adk & transient hillclimb scratch outputs
├── requirements.txt                        # google-adk==2.4.0, vertexai[evaluation], krippendorff-aleph-alpha
├── best_criteria_submission.txt            # Selected reliable high-headroom criteria IDs
├── re_analyst/                             # ADK 2.4 Real Estate Investment Analyst Agent
│   ├── agent.py                            # Root agent, SYSTEM_INSTRUCTION & SkillToolset wiring
│   ├── skills/
│   │   ├── analyze-opportunity/SKILL.md    # Parcel investigation & cross-skill orchestration
│   │   ├── analyze-flood-risk/SKILL.md     # FEMA flood zone & neighboring parcel hydrology analysis
│   │   └── analyze-tax-implications/SKILL.md # Acquisition cost/acre & monthly APN tax carrying analysis
│   └── tools/
│       ├── lot_tool.py                     # get_lot_data(plot_id) -> lots_database.json
│       └── tax_tool.py                     # get_tax_assessment_data(parcel_apn) -> tax_database.json
├── eval_harness/                           # GEAP Autorater & Statistical Agreement Suite
│   ├── rubrics.json                        # 19 candidate 1-5 evaluation criteria (BARS + subjective foils)
│   ├── create_re_agent_evalset.py          # Concurrent ADK EvalSet trace generator
│   ├── run_geap_eval.py                    # Vertex AI EvalTask runner (--dry-run & k-pass cloud mode)
│   ├── metrics_calc.py                     # N x k matrix stats & interval Krippendorff's Alpha
│   ├── all_criteria_analysis.py            # 19-criterion summary & agreement table CLI
│   ├── single_criterion_analysis.py        # Per-criterion N x k grades matrix CLI
│   ├── explain_criteria_results.py         # Judge rationale inspector filtered by score threshold
│   ├── hillclimb_lots.txt                  # 10 target edge-case parcel IDs
│   └── run_hillclimb.py                    # Automated hill-climbing execution & scoring loop
├── tools_data/
│   ├── lots_database.json                  # 63 parcel records (zoning, flood_zone, adjacent_parcels, ESA)
│   └── tax_database.json                   # 60 official county APN tax assessment records
└── runs/
    └── geap_calls_and_responses_for_analysis.json # Pre-staged N=32 x 19 criteria x k=15 GEAP dataset
```

---

## Quick Verification

### 1. Run Offline Multi-Pass Autorater Reliability Analysis (`N = 32 × k = 15`)

```bash
# Global summary across all 19 criteria
python -m eval_harness.all_criteria_analysis \
  --run_geap_eval_out runs/geap_calls_and_responses_for_analysis.json

# Drill into a single criterion's N x k Grades Matrix
python -m eval_harness.single_criterion_analysis \
  --run_geap_eval_out runs/geap_calls_and_responses_for_analysis.json \
  --criterion monthly-tax-holding

# Inspect judge rationales for low-scoring / split-decision passes
python -m eval_harness.explain_criteria_results \
  --run_geap_eval_out runs/geap_calls_and_responses_for_analysis.json \
  --criterion cost-per-acre \
  --max_score_to_show 2.0
```

### 2. Run Live Agent Hill-Climbing Iteration (Requires Vertex AI ADC + `.env`)

```bash
python -m eval_harness.run_hillclimb
```

---

## Official References

- [Google Agent Development Kit (ADK) Documentation — Skills & Evaluation](https://google.github.io/adk-docs/)
- [Vertex AI GenAI Evaluation Service (`PointwiseMetric` & `EvalTask`)](https://cloud.google.com/vertex-ai/generative-ai/docs/models/evaluation-overview)
- [Define Your Evaluation Metrics & Custom Autorater Rubrics](https://cloud.google.com/vertex-ai/generative-ai/docs/models/determine-eval)
