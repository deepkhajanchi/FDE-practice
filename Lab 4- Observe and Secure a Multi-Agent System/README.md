# Lab 4 — Observe and Secure a Multi-Agent System (APEX014 Challenge Lab)

An enterprise-grade cross-runtime observability, platform discovery, topology mapping, and AI security-posture governance implementation for a multi-agent system spanning **Vertex AI Agent Runtime (`github-agent`)**, **Cloud Run (`salesforce-agent`)**, and an external **Model Context Protocol (MCP) server (`github-mcp`)** using **OpenTelemetry + Cloud Trace (`telemetry.googleapis.com`)**, **App Hub**, **Agent Registry**, **Agent Topology**, **Security Command Center (SCC) AI Protection**, **IAM Policy Analyzer**, and **Agent Platform Threat Detection**.

👉 **Full step-by-step challenge runbook, system architecture diagram, end-to-end sequence workflows, scored checkpoint matrix, and troubleshooting:** see [`RUNBOOK.md`](./RUNBOOK.md).

---

## Observability, Discovery & AI Security Stack Overview

| Layer / Capability | Google Cloud Service / API | Implementation Surface | Operational & Security Guarantee |
|---|---|---|---|
| **Distributed Agent Tracing** | **OpenTelemetry + Telemetry OTLP API + Cloud Trace** (`telemetry.googleapis.com`, `cloudtrace.googleapis.com`) | `google-adk[gcp,otel-gcp]` + `app/app_utils/telemetry.py` + `roles/telemetry.tracesWriter` | Exports hierarchical `agent_run`, `call_llm`, and `execute_tool` spans across Agent Runtime (managed telemetry) and Cloud Run (`get_gcp_exporters`) |
| **Workload Classification** | **App Hub** (`apphub.googleapis.com`) | `discoveredWorkloads` (`functionalType.type = "AGENT"`) | Automatically classifies Agent Runtime engines as `AGENT` and backs MCP/Agent inventory for Topology and SCC AI Protection |
| **Multi-Runtime Agent & MCP Catalog** | **Agent Registry** (`agentregistry.googleapis.com`) + **Discovery Engine SA** (`gcp-sa-discoveryengine`) | Auto-discovery (`github-agent`) + `services create salesforce-agent` (`a2a-agent-card`) + `services create github-mcp` (`no-spec`, `JSONRPC`) | Unifies Vertex AI Agent Runtime agents, private Cloud Run A2A agents (`roles/run.invoker`), and external MCP servers in one registry |
| **System Dependency Graph** | **Agent Topology** (`apptopology.googleapis.com`) | Agent Registry **Topology** tab | Synthesizes classified App Hub/Registry **nodes** with batch-aggregated Cloud Trace **edges** across heterogeneous runtimes |
| **AI Security Posture & Risk Inventory** | **SCC AI Protection** (`Agent Platform → Security`) | AI Inventory, *Agents with excessive permissions*, & ~6h Attack Path Simulation | Surfaces non-human identity privilege creep (`roles/editor`) and models toxic-combination exposure for high-value agent assets |
| **Blast-Radius Proof & Least Privilege** | **IAM Policy Analyzer + Cloud Asset Inventory** (`cloudasset.googleapis.com`) | Console Policy Analyzer + `gcloud asset analyze-iam-policy` + `remove-iam-policy-binding` | Proves exact resource reach of over-privileged agent SAs and right-sizes `salesforce-agent` to 4 narrow operational roles |
| **Near-Real-Time Runtime Defense** | **Agent Platform Threat Detection** (`Security Command Center → Findings`) | Container runtime & control-plane detectors (EICAR test workflow) | Detects foreign binary execution (`AGENT_ENGINE_ADDED_MALICIOUS_BINARY_EXECUTED`), reverse shells, container escapes, and credential theft |

---

## Directory Layout

```text
Lab 4- Observe and Secure a Multi-Agent System/
├── RUNBOOK.md                              # Step-by-step challenge runbook, architecture & sequence diagrams
├── README.md                               # Stack overview, directory layout & offline test verification
├── .gitignore                              # Excludes .env secrets, salesforce_card.json, .venv & state files
├── apex_labs/
│   └── lab2_prereqs.sh                     # Deploys baseline github-agent (Agent Runtime) & salesforce-agent (Cloud Run)
├── scripts/
│   └── verify_lab4_posture.sh              # Read-only verifier for all 6 scored Challenge Lab checkpoints
└── agents/
    ├── github-agent/                       # Agent Runtime ADK specialist + McpToolset + OTel Agent Engine telemetry (5 unit tests)
    │   ├── app/
    │   │   ├── agent.py                    # GitHub Copilot MCP toolset (search_repositories, search_issues, list_issues)
    │   │   ├── fast_api_app.py             # FastAPI + A2A + Reasoning Engine adapter + setup_agent_engine_telemetry()
    │   │   └── app_utils/telemetry.py      # OpenTelemetry GenAI logging + _default_instrumentor_builder()
    │   ├── deployment/terraform/           # Single-project & shared BigQuery/GCS GenAI telemetry sink templates
    │   └── tests/unit/                     # Offline pytest suite (5 tests)
    └── salesforce-agent/                   # Cloud Run ADK specialist + A2A Card + OTLP exporter + Memory Bank (28 unit tests)
        ├── app/
        │   ├── agent.py                    # Salesforce SOSL search tool + PreloadMemoryTool + Memory Bank callback
        │   ├── fast_api_app.py             # FastAPI + A2A (/a2a/app/.well-known/agent-card.json) + setup_telemetry()
        │   └── app_utils/telemetry.py      # get_gcp_exporters(enable_cloud_tracing=True) -> telemetry.googleapis.com
        ├── deployment/terraform/           # Cloud Run service + BigQuery/GCS GenAI telemetry sink templates
        └── tests/unit/                     # Offline pytest suite (28 tests)
```

---

## Quick Verification

### 1. Audit Live GCP Lab Checkpoints (Read-Only)

```bash
chmod +x scripts/verify_lab4_posture.sh
./scripts/verify_lab4_posture.sh
```

### 2. Run Offline Agent Unit Suites (33 Passing Tests)

```bash
# 1. Verify github-agent (5 unit tests: identity, MCP toolset wiring & read-only tool filter)
cd "agents/github-agent"
MODEL=gemini-3.5-flash GITHUB_PERSONAL_ACCESS_TOKEN=dummy uv run pytest tests/unit -v

# 2. Verify salesforce-agent (28 unit tests: user-scoped A2A metadata, Memory Bank, 2LO auth & SOSL excerpting)
cd "../salesforce-agent"
MODEL=gemini-3.5-flash SALESFORCE_DOMAIN=example.my.salesforce.com \
  SALESFORCE_CLIENT_ID=dummy SALESFORCE_CLIENT_SECRET=dummy \
  uv run pytest tests/unit -v
```

---

## Official References

- [Agent Registry Overview](https://docs.cloud.google.com/agent-registry/overview)
- [Cloud Trace & OpenTelemetry OTLP Ingestion (`telemetry.googleapis.com`)](https://cloud.google.com/trace/docs/overview)
- [App Hub Overview](https://cloud.google.com/app-hub/docs/overview)
- [Security Command Center AI Protection Overview](https://cloud.google.com/security-command-center/docs)
- [IAM Policy Analyzer (`gcloud asset analyze-iam-policy`)](https://cloud.google.com/policy-intelligence/docs/analyze-iam-policies)
