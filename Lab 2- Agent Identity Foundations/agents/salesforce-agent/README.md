# salesforce-agent (Agent Identity Edition)

Salesforce specialist **A2A sub-agent** deployed to **Cloud Run** with **SPIFFE Agent Identity** (`--functional-type=agent`, `--identity-type=agent-identity`) and **Agent Identity Auth Manager** (`AuthenticatedFunctionTool` + `GcpAuthProvider` + `GcpAuthProviderScheme`).

It searches an organization's **Salesforce Files** document library (ADRs and engineering policies) via SOSL and downloads `VersionData` excerpts, while delegating 2-Legged OAuth (`client_credentials`) token exchange entirely to Google Cloud's `salesforce-auth-provider` — keeping `SALESFORCE_CLIENT_ID` and `SALESFORCE_CLIENT_SECRET` completely out of `.env` and Cloud Run revision specs.

## Configuration

Copy `.env.example` to `.env`:

| Variable | Purpose |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | GCP project for Vertex AI / Cloud Logging / Memory Bank. |
| `MODEL` | Gemini model ID (e.g., `gemini-3.5-flash`). |
| `GOOGLE_CLOUD_LOCATION` | Vertex location for model calls (`global`). |
| `SALESFORCE_DOMAIN` | Org My Domain host without scheme (e.g., `mycompany-dev-ed.develop.my.salesforce.com`). |
| `SALESFORCE_AUTH_PROVIDER_URI` | Full GCP 2LO AuthProvider resource name (`projects/.../locations/.../authProviders/salesforce-auth-provider`). |
| `SALESFORCE_API_VERSION` | *(Optional)* REST API version for `/services/data/vXX.X/` (default `v62.0`). |
| `MEMORY_BANK_ID` | *(Optional)* Vertex AI Memory Bank ID for cross-session per-user recall. |
| `MEMORY_BANK_LOCATION` | *(Optional)* Regional endpoint for Memory Bank (`us-central1`). |

## Deploy with Cloud Run SPIFFE Agent Identity

```bash
export SALESFORCE_APP_URL="https://salesforce-agent-${PROJECT_NUMBER}.${REGION}.run.app"
SF_ENV_VARS="$(grep -v '^#' .env | grep -v '^$' | paste -sd,),APP_URL=${SALESFORCE_APP_URL}"

gcloud beta run deploy salesforce-agent \
  --source=. \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --functional-type=agent \
  --identity-type=agent-identity \
  --no-allow-unauthenticated \
  --no-iap \
  --no-cpu-throttling \
  --memory=4Gi \
  --cpu=2 \
  --min-instances=0 \
  --max-instances=4 \
  --set-env-vars="${SF_ENV_VARS}"
```

## Offline Unit Tests

```bash
uv sync
uv run pytest tests/unit -v
```
