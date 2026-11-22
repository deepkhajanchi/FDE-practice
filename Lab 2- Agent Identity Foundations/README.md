# Lab 2 — Agent Identity Foundations (APEX009)

An enterprise-grade zero-standing-secret refactoring of the **Code Assist** specialist fleet (`github-agent` and `salesforce-agent`), replacing shared runtime service accounts and plaintext `.env` secrets with **cryptographically attested SPIFFE Workload Identities (`*.system.id.goog`)** and **Google Cloud Agent Identity Auth Manager (`authProviders`)** across **Vertex AI Agent Runtime** and **Cloud Run**.

👉 **Full operational guide, system architecture, credential-exchange sequence workflows, code implementations, and troubleshooting:** see [`RUNBOOK.md`](./RUNBOOK.md).

---

## Identity & Credential Architecture Overview

| Agent | Hosting Target | Workload Identity (SPIFFE Principal) | Auth Manager Resource (`authProviders`) | ADK Integration Surface | Secrets Removed from `.env` / Container |
|---|---|---|---|---|---|
| **`github-agent`** | **Vertex AI Agent Runtime** (`us-central1`, `identityType=AGENT_IDENTITY`) | `principal://agents.global.org-<ORG_ID>.system.id.goog/resources/aiplatform/projects/<PROJECT_NUMBER>/locations/us-central1/reasoningEngines/<ENGINE_ID>` | `github-mcp-auth-provider` (**API Key** — upgradable in-place to **3-Legged OAuth** w/ PKCE) | `CredentialManager` + `GcpAuthProvider` + `McpToolset(auth_scheme=GcpAuthProviderScheme)` | `GITHUB_PERSONAL_ACCESS_TOKEN` |
| **`salesforce-agent`** | **Cloud Run** (`us-central1`, `--functional-type=agent`, `--identity-type=agent-identity`) | `principal://agents.global.org-<ORG_ID>.system.id.goog/resources/run/projects/<PROJECT_NUMBER>/locations/us-central1/services/salesforce-agent` | `salesforce-auth-provider` (**2-Legged OAuth** `client_credentials` exchanged server-side) | `CredentialManager` + `GcpAuthProvider` + `AuthenticatedFunctionTool(auth_config=AuthConfig)` | `SALESFORCE_CLIENT_ID`, `SALESFORCE_CLIENT_SECRET` |

---

## Directory Layout

```text
Lab 2- Agent Identity Foundations/
├── RUNBOOK.md                      # Step-by-step runbook, architecture & sequence diagrams
├── README.md                       # Identity overview, transformation matrix & test index
├── .gitignore                      # Excludes .env secrets, .venv, and deployment metadata
├── apex_labs/
│   └── lab2_prereqs.sh             # Reproduces End-of-Lab-1 starter state in a fresh GCP project
└── agents/
    ├── github-agent/               # Agent Runtime ADK specialist + GcpAuthProviderScheme + two-phase deploy_with_identity.sh
    └── salesforce-agent/           # Cloud Run ADK specialist + AuthenticatedFunctionTool (2LO) + Vertex AI Memory Bank
```

---

## Quick Verification (Offline Unit Suites)

Both refactored agents include offline unit test suites under `tests/unit/` that validate `GcpAuthProvider` registration, `GcpAuthProviderScheme` binding, `McpToolset` and `AuthenticatedFunctionTool` token injection, LLM declaration parameter masking (`credential` hidden from tool schema), and zero-plaintext-secret enforcement without live network calls:

```bash
# Verify salesforce-agent (AuthenticatedFunctionTool + 2LO AuthProvider + Memory Bank)
cd "agents/salesforce-agent" && uv sync && uv run pytest tests/unit

# Verify github-agent (McpToolset + API-Key / 3LO AuthProvider)
cd "../github-agent" && uv run --with pytest --with-requirements agent/requirements.txt pytest tests/unit
```
