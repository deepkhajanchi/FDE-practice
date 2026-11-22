# Lab 1 — Build Enterprise Agents ("Code Assist")

An enterprise-grade, heterogeneous multi-agent incident-resolution platform built on **Google ADK 2.0 (`Workflow`)**, **LangGraph**, the **Agent2Agent (A2A) protocol** (`0.3.x` + `1.x` backward compatibility), **Model Context Protocol (MCP)**, **GCP Skill Registry**, **Vertex AI Search**, **BigQuery Vector Search**, and **Vertex AI Memory Bank**, deployed across **Agent Runtime**, **Cloud Run**, and **GKE Autopilot**, and published to **Gemini Enterprise**.

👉 **Full operational guide, system architecture, sequence workflows, code implementations, and troubleshooting:** see [`RUNBOOK.md`](./RUNBOOK.md).

---

## Multi-Agent Fleet Overview

| Agent | Framework | Hosting Target | Protocol / Surface | Knowledge Source & Auth |
|---|---|---|---|---|
| **`code-assistant`** *(Root Orchestrator)* | ADK 2.0 `Workflow` (`google-adk 2.3.0`) | **Agent Runtime** (Vertex AI Agent Engine) | ADK `:streamQuery` (Gemini Enterprise) + A2A `0.3` | Orchestrates intake (`load_artifacts`), 5-way parallel fan-out, `JoinNode` fan-in, and source-attributed synthesis |
| **`manual_search_agent`** *(In-Process Branch)* | ADK `Agent` | In-process inside `code-assistant` | Shared `Workflow` session state (`manual_findings`) | **Vertex AI Search** (`code_manuals/*.pdf`) + **Developer Knowledge MCP** + **GCP Skill Registry** (`using-developer-knowledge-mcp`) |
| **`bug-db-agent`** *(Remote Specialist)* | ADK `Agent` | **GKE Autopilot** (or Cloud Run) | A2A `0.3` (`RemoteA2aAgent`, `use_legacy=False`) | **BigQuery** `code_assist_bugs.known_bugs` (768-dim `text-embedding-004` semantic/SQL search) via Workload Identity / ADC |
| **`github-agent`** *(Remote Specialist)* | ADK `Agent` | **Agent Runtime** | Authenticated A2A `0.3` (`GoogleADCAuth` bearer token) | Hosted **GitHub MCP Server** (`https://api.githubcopilot.com/mcp/`) with PAT + read-only `tool_filter` |
| **`salesforce-agent`** *(Remote Specialist)* | ADK `Agent` | **Cloud Run** | A2A `0.3` + `user_id` metadata forwarding | **Salesforce Files** SOSL + `VersionData` excerpting via **2-Legged OAuth (`client_credentials`)** + **Vertex AI Memory Bank** |
| **`stackexchange-agent`** *(Remote Specialist)* | **LangGraph** (`StateGraph`, deterministic / no LLM) | **GKE Autopilot** (or Cloud Run) | Self-hosted **`a2a-sdk` 1.x** (`1.0` + `0.3` dual `AgentInterface`) | Public **Stack Exchange API** (`StackExchangeTool`), queried via `CleanQueryRemoteA2aAgent` |

---

## Directory Layout

```text
Lab 1- Build Enterprise Agents/
├── RUNBOOK.md                      # Step-by-step runbook, architecture & workflow diagrams
├── README.md                       # Fleet overview and repository index
├── .gitignore                      # Excludes .env secrets, .venv, and Terraform state
└── agents/
    ├── code-assistant/             # Root ADK 2.0 graph Workflow orchestrator + Skill Registry publisher
    ├── github-agent/               # ADK specialist wrapping the hosted GitHub MCP server
    ├── salesforce-agent/           # ADK specialist with Salesforce 2LO SOSL + Vertex AI Memory Bank
    └── stackexchange-agent/        # LangGraph specialist self-served on a2a-sdk 1.x (GKE / Cloud Run)
```

---

## Quick Verification (Offline Unit Suites)

Each agent includes an offline unit test suite under `tests/unit/` that validates graph topology, tool filtering, 2LO caching/retry, Memory Bank callbacks, and A2A `0.3`/`1.0` backward compatibility without live network calls:

```bash
cd "agents/github-agent"        && uv sync && uv run pytest tests/unit
cd "../stackexchange-agent"     && uv sync && uv run pytest tests/unit
cd "../salesforce-agent"        && uv sync && uv run pytest tests/unit
cd "../code-assistant"          && uv sync && uv run pytest tests/unit
```
