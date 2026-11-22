#!/usr/bin/env bash
# =============================================================================
# verify_lab4_posture.sh
# Read-only verification script for APEX014:
# "Observe and Secure a Multi-Agent System — Challenge Lab"
#
# Validates all 6 scored checkpoints and key observability/discovery signals
# without mutating any Google Cloud resources or IAM policies.
# =============================================================================

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
LOCATION="${LOCATION:-us-central1}"
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"

BOLD="$(tput bold 2>/dev/null || true)"
GREEN="$(tput setaf 2 2>/dev/null || true)"
YELLOW="$(tput setaf 3 2>/dev/null || true)"
RED="$(tput setaf 1 2>/dev/null || true)"
RESET="$(tput sgr0 2>/dev/null || true)"

pass() { echo "${GREEN}  [PASS]${RESET} $*"; }
warn() { echo "${YELLOW}  [WARN]${RESET} $*"; }
fail() { echo "${RED}  [FAIL]${RESET} $*"; }
hdr()  { echo -e "\n${BOLD}=== $* ===${RESET}"; }

echo "${BOLD}Project:${RESET} ${PROJECT_ID} (${PROJECT_NUMBER}) | ${BOLD}Location:${RESET} ${LOCATION}"

# 1. Checkpoint 1 — Observability & Discovery APIs
hdr "1. Observability & Discovery APIs (Task 1.5)"
REQUIRED_APIS=(
  observability.googleapis.com
  cloudtrace.googleapis.com
  telemetry.googleapis.com
  apphub.googleapis.com
  apptopology.googleapis.com
  agentregistry.googleapis.com
  cloudasset.googleapis.com
  monitoring.googleapis.com
  logging.googleapis.com
)
ENABLED_APIS="$(gcloud services list --enabled --project="${PROJECT_ID}" --format='value(config.name)' --quiet)"
for api in "${REQUIRED_APIS[@]}"; do
  if echo "${ENABLED_APIS}" | grep -qx "${api}"; then
    pass "${api} enabled"
  else
    fail "${api} NOT enabled"
  fi
done

# 2. Checkpoint 2 — Trace-Writer IAM Role on Cloud Run SA
hdr "2. Cloud Run Agent Telemetry Role (Task 2.3)"
SF_SA="$(gcloud run services describe salesforce-agent \
  --region="${LOCATION}" \
  --project="${PROJECT_ID}" \
  --format='value(spec.template.spec.serviceAccountName)' \
  --quiet)"
echo "  salesforce-agent service account: ${SF_SA}"

SA_ROLES="$(gcloud projects get-iam-policy "${PROJECT_ID}" \
  --flatten='bindings[].members' \
  --filter="bindings.members:serviceAccount:${SF_SA}" \
  --format='value(bindings.role)' \
  --quiet)"

if echo "${SA_ROLES}" | grep -qx "roles/telemetry.tracesWriter"; then
  pass "${SF_SA} has roles/telemetry.tracesWriter"
else
  fail "${SF_SA} is missing roles/telemetry.tracesWriter"
fi

# 3. Task 3 — Agent Runtime Auto-Discovery & App Hub Classification
hdr "3. Agent Runtime Discovery & App Hub Classification (Task 3)"
gcloud alpha agent-registry agents list \
  --location="${LOCATION}" \
  --project="${PROJECT_ID}" \
  --format="table(displayName,name.basename(),protocols[0].protocolVersion)" \
  --quiet || warn "Could not list Agent Registry agents"

TOKEN="$(gcloud auth print-access-token)"
curl -s \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "x-goog-user-project: ${PROJECT_ID}" \
  "https://apphub.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION}/discoveredWorkloads" \
  | jq -r '(.discoveredWorkloads // [])[] | "  AppHub Workload: \(.workloadProperties.functionalType.type // "-") -> \(.workloadReference.uri)"'

# 4. Checkpoint 3 — Discovery Engine Invoker on salesforce-agent
hdr "4. Discovery Engine Service Agent Invoker Binding (Task 4.1)"
DE_SA="service-${PROJECT_NUMBER}@gcp-sa-discoveryengine.iam.gserviceaccount.com"
CR_POLICY="$(gcloud run services get-iam-policy salesforce-agent \
  --region="${LOCATION}" \
  --project="${PROJECT_ID}" \
  --flatten='bindings[].members' \
  --filter="bindings.members:serviceAccount:${DE_SA} AND bindings.role:roles/run.invoker" \
  --format='value(bindings.role)' \
  --quiet)"
if [ "${CR_POLICY}" = "roles/run.invoker" ]; then
  pass "${DE_SA} has roles/run.invoker on salesforce-agent"
else
  fail "${DE_SA} is missing roles/run.invoker on salesforce-agent"
fi

# 5. Checkpoints 4 & 5 — Registered Cloud Run Agent & GitHub MCP Server
hdr "5. Agent Registry Services & MCP Servers (Tasks 4.3 & 5.2)"
gcloud alpha agent-registry services list \
  --location="${LOCATION}" \
  --project="${PROJECT_ID}" \
  --format="table(name.basename(),displayName,agentSpec.type,mcpServerSpec.type)" \
  --quiet || warn "Could not list Agent Registry services"

gcloud alpha agent-registry mcp-servers list \
  --location="${LOCATION}" \
  --project="${PROJECT_ID}" \
  --format="table(name.basename(),displayName,interfaces[0].url,interfaces[0].protocolBinding)" \
  --quiet || warn "Could not list Agent Registry MCP servers"

# 6. Checkpoint 6 — Least-Privilege IAM Verification on salesforce-agent
hdr "6. Least-Privilege IAM Posture on salesforce-agent (Task 9)"
EXPECTED_NARROW_ROLES=(
  roles/aiplatform.user
  roles/telemetry.tracesWriter
  roles/logging.logWriter
  roles/cloudtrace.agent
)
for r in "${EXPECTED_NARROW_ROLES[@]}"; do
  if echo "${SA_ROLES}" | grep -qx "${r}"; then
    pass "Narrow role present: ${r}"
  else
    warn "Narrow role missing: ${r}"
  fi
done

if echo "${SA_ROLES}" | grep -qx "roles/editor"; then
  fail "Over-privileged roles/editor is STILL bound to ${SF_SA}"
else
  pass "roles/editor is NOT bound to ${SF_SA} (least privilege verified)"
fi
