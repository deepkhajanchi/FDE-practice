# github-agent (Agent Identity Edition)

GitHub specialist **A2A sub-agent** secured with **Google Cloud Agent Identity** (`identityType=AGENT_IDENTITY`) and **Agent Identity Auth Manager** (`GcpAuthProvider` + `GcpAuthProviderScheme`).

Instead of storing a static `GITHUB_PERSONAL_ACCESS_TOKEN` in `.env` or container environment variables, `McpToolset` dynamically retrieves credentials from `projects/<PROJECT_ID>/locations/<LOCATION>/authProviders/github-mcp-auth-provider` using the Reasoning Engine's attested SPIFFE workload identity.

## Configuration

Copy `.env.example` to `.env`:

| Variable | Purpose |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | GCP project ID (filtered out at deploy time as Agent Runtime injects it automatically). |
| `GOOGLE_CLOUD_LOCATION` | Vertex AI model endpoint (`global`). |
| `GOOGLE_GENAI_USE_VERTEXAI` | `True` for Vertex AI Gemini calls. |
| `MODEL` | Gemini model ID (e.g., `gemini-3.5-flash`). |
| `GITHUB_MCP_URL` | Hosted GitHub MCP URL (`https://api.githubcopilot.com/mcp/`). |
| `GITHUB_AUTH_PROVIDER_URI` | Full GCP AuthProvider resource name (`projects/.../locations/.../authProviders/github-mcp-auth-provider`). |
| `GITHUB_OAUTH_SCOPES` | *(Optional)* Comma-separated OAuth scopes when using a 3LO Auth Provider. |
| `GITHUB_CONTINUE_URI` | *(Optional)* Callback/continue URI when using a 3LO Auth Provider. |

## Deploy with SPIFFE Agent Identity

```bash
AUTH_PROVIDER_NAME="github-mcp-auth-provider" \
AUTH_PROVIDER_LOCATION="us-central1" \
A2A_APP_NAME="agent" \
./deploy_with_identity.sh
```

## Offline Unit Tests

```bash
uv run --with pytest --with-requirements agent/requirements.txt pytest tests/unit -v
```
