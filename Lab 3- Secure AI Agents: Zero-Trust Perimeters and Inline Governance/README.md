# Lab 3 — Secure AI Agents: Zero-Trust Perimeters and Inline Governance

An enterprise-grade zero-trust network perimeter and inline content-governance reference architecture for **Google ADK** agents on **Vertex AI Agent Runtime (`ReasoningEngine`)** invoking remote **Model Context Protocol (MCP)** servers on **Cloud Run**. Outbound agent traffic is mediated through a **Google-Managed Agent Gateway (`AGENT_TO_ANYWHERE`)** backed by **Private Service Connect (PSC) Interfaces**, **Agent Registry** dynamic discovery, **Identity-Aware Proxy (IAP) `REQUEST_AUTHZ`** (`roles/iap.egressor`), and **Model Armor + Cloud DLP `CONTENT_AUTHZ`** inline prompt-injection blocking and PII redaction.

👉 **Full step-by-step operational guide, zero-trust system architecture, runtime sequence workflows, Terraform module reference, and troubleshooting:** see [`RUNBOOK.md`](./RUNBOOK.md).

---

## Zero-Trust & Inline Governance Stack Overview

| Layer / Component | Resource / Service | Implementation Surface | Security & Governance Guarantee |
|---|---|---|---|
| **Governed Agent Workload** | **Vertex AI Agent Runtime** (`hello_agent`, `identityType=AGENT_IDENTITY`) | `agents/hello_agent/` (`FastAPI` + `AdkApp` + `RootAgent`) | Runs with attested SPIFFE identity (`*.system.id.goog`), zero hardcoded tool URLs, dual OIDC token routing, and fail-fast handling for `403`/`798`/`799` interventions |
| **Private Network Perimeter** | **VPC + Dual PSC-Interface Network Attachments** (`governed-agent-vpc`, `10.128.0.0/20`) | `terraform/networking/` & `terraform/gateway/` | Isolates Reasoning Engine NIC (`gateway-egress-na`) and Agent Gateway egress (`gateway-egress-services-na`) inside a private subnet |
| **Central Discovery & Catalog** | **Google Cloud Agent Registry** (`agentregistry.googleapis.com`) | `terraform/registry/` (`register_endpoints.sh.tpl`) + Cloud Run `--functional-type=mcp-server` | Dynamically resolves `agents-everywhere-sample-tool` and allowlists 50 regional/global/mTLS/REP Google Cloud API endpoints |
| **Egress Proxy Control Point** | **Google-Managed Agent Gateway** (`gateway-egress`, `AGENT_TO_ANYWHERE`) | `terraform/gateway/main.tf` (`google_network_services_agent_gateway`) | Intercepts all outbound agent traffic (`agentGatewayConfig.agentToAnywhereConfig`) and enforces attached `AuthzPolicy` extensions |
| **Layer 1: Zero-Trust AuthZ** | **IAP Service Extension (`REQUEST_AUTHZ`)** (`iap.googleapis.com`, `fail_open=false`) | `gateway-egress-iap-ext` + `gateway-egress-iap-policy` | Supports `DRY_RUN` audit mode (`enable_iap_enforcement=false`) and active default-deny enforcement (`roles/iap.egressor` per MCP server/endpoint) |
| **Layer 2: Inline Safety & DLP** | **Model Armor + Cloud DLP (`CONTENT_AUTHZ`)** (`modelarmor.<region>.rep.googleapis.com`) | `terraform/model-armor/` + `gateway-egress-ma-policy` | Blocks prompt injection, jailbreaks, RAI violations, and malicious URIs inline (`HTTP 799`/`798`), redacts SSNs/PII in transit via Cloud DLP, and enforces project-wide `AI_PLATFORM` floor settings |
| **Governed MCP Tool Target** | **Cloud Run FastMCP Server** (`agents-everywhere-sample-tool`) | `mcp-servers/sample-tool/` (`server.py`, JSON-RPC 2.0) | Deployed with `--no-allow-unauthenticated` and `--functional-type=mcp-server`; exposes `get_capital`, `get_hostname`, and `get_santized_record` |

---

## Directory Layout

```text
Lab 3- Secure AI Agents: Zero-Trust Perimeters and Inline Governance/
├── RUNBOOK.md                              # Step-by-step runbook, architecture & workflow diagrams
├── README.md                               # Zero-trust stack overview, layout & offline test commands
├── .gitignore                              # Excludes .env secrets, .venv, and Terraform/deploy state
├── agents/
│   └── hello_agent/                        # Containerized ADK Reasoning Engine agent + 42 unit tests
│       ├── app/
│       │   ├── agent.py                    # Agent Registry discovery, dual OIDC routing & 403/798/799 handling
│       │   ├── main.py                     # FastAPI Reasoning Engine HTTP/stream wrapper + _safe_project_id
│       │   ├── models.py                   # Pydantic JSON-RPC 2.0 & AgentState schemas
│       │   └── agent_runtime_app.py        # Agent Runtime entrypoint
│       ├── tests/                          # Offline pytest suite (test_agent.py, test_main.py, test_hello_models.py)
│       ├── Dockerfile                      # Non-root Python 3.13 container spec
│       └── pyproject.toml                  # Project metadata & dependencies
├── mcp-servers/
│   └── sample-tool/                        # Cloud Run FastMCP JSON-RPC 2.0 server + 18 unit tests
│       ├── server.py                       # get_capital, get_hostname, get_santized_record tools
│       ├── models.py                       # Strict MCP JSON-RPC 2.0 request/response validation
│       ├── tests/                          # Offline pytest suite (test_server.py, test_sample_models.py)
│       └── Dockerfile                      # Non-root Python 3.12 container spec
├── scripts/
│   └── lab-cleanup.sh                      # Dependency-ordered teardown (ReasoningEngine -> AuthzPolicy -> AgentGateway)
└── terraform/
    ├── main.tf                             # Root orchestrator, Artifact Registry & SPIFFE/Service Agent IAM
    ├── networking/                         # Private VPC, subnet (10.128.0.0/20) & gateway-egress-na PSC attachment
    ├── registry/                           # Agent Registry API, serialized roles/iap.egressor & 50 Google API endpoints
    ├── gateway/                            # Agent Gateway (AGENT_TO_ANYWHERE), IAP REQUEST_AUTHZ & Model Armor CONTENT_AUTHZ
    └── model-armor/                        # Cloud DLP inspect/deidentify templates, Model Armor 799/798 templates & Vertex AI floor settings
```

---

## Quick Verification (Offline Unit Suites — 60 Tests)

Both `hello_agent` (**42 tests**) and `sample-tool` (**18 tests**) include comprehensive offline unit test suites validating Agent Registry discovery, native vs. impersonated OIDC token routing, JSON-RPC 2.0 schema validation, and fail-fast Model Armor (`HTTP 799`) intervention handling without live network calls:

```bash
# 1. Verify hello_agent (42 unit tests: discovery, dual OIDC routing, 799 safety handling & FastAPI streaming)
cd "agents/hello_agent"
PROJECT_ID=test-project uv run --no-project \
  --with pytest --with pytest-mock --with httpx \
  --with-requirements requirements.txt \
  pytest tests -v

# 2. Verify sample-tool FastMCP server (18 unit tests: get_capital, get_hostname, get_santized_record & JSON-RPC errors)
cd "../../mcp-servers/sample-tool"
uv run --no-project \
  --with pytest --with pytest-mock --with anyio \
  --with-requirements requirements.txt \
  pytest tests -v
```
