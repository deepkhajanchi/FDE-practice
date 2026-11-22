# Lab 8 — Add Google Drive with Sensitive Data Protection to Gemini Enterprise

Connecting a federated **Google Drive (`google_drive`, `FEDERATED` mode)** data store to **Gemini Enterprise (`APP_TYPE_INTRANET`)** with inline **Cloud Sensitive Data Protection (SDP) Content Policies (`contentPolicies`)** enforcing synchronous **`ALLOW` / `BLOCK`** verdicts across **inbound Drive retrieval**, **Google Workspace classification labels (`googleDriveLabel`)**, **Assistant chat uploads**, and **Gemini Notebook Enterprise**, complemented by **Model Armor** serving-path guardrails and **BigQuery (`ContentPolicyActionLog`)** audit logging.

👉 **Full step-by-step operational runbook, system architecture diagram, runtime sequence workflows, Console + REST API commands, and troubleshooting playbook:** see **[`RUNBOOK.md`](./RUNBOOK.md)**.

---

## Governance & Data-Protection Stack Summary

| Layer | Google Cloud / Workspace Surface | Primary Resource / Module | Security & Governance Guarantee |
|---|---|---|---|
| **Workspace Identity & Federated Access** | **Google Identity** + **Google-Managed Drive OAuth App** | `502998392228-...googleusercontent.com` | Queries Google Drive live (`FEDERATED`) with zero index duplication and zero privilege escalation beyond per-user Drive ACLs |
| **Service Agent Authorization** | **Cloud IAM** (`discoveryengine` $\rightarrow$ `dlp`) | `service-<PROJECT_NUMBER>@gcp-sa-discoveryengine.iam.gserviceaccount.com` | Least-privilege **`roles/dlp.user`** grant enables Gemini Enterprise to evaluate SDP content policies synchronously |
| **Inbound & Upload Policy Engine** | **Sensitive Data Protection (`contentPolicies`)** | `configs/content_policy_pii_labels.json`, `gdrive_sdp_governance/builder.py` | Evaluates built-in PII/credential `infoTypes`, hotword rules, and `googleDriveLabel` metadata; enforces fail-closed `BLOCK` on `inputTooLarge` and `failedToScanSupportedFileType` |
| **Federated Google Drive Connector** | **Discovery Engine `v1alpha` (`setUpDataConnector`)** | `configs/gdrive_connector_payload.json`, `gdrive_sdp_governance/builder.py` | Scopes `Search files` via recursive `FolderIds` / `SharedDriveIds` (`admin_filter`) and attaches `dataProtectionPolicy` inline |
| **Multi-Surface App Protection** | **Gemini Enterprise App (`APP_TYPE_INTRANET`)** | **App $\rightarrow$ Security** (`Assistant` + `NotebookLM` + **Model Armor**) | Blocks side-channel sensitive file uploads in chat and notebooks while Model Armor screens prompts and responses |
| **Posture & Schema Verifier** | **Zero-Dependency Python Package & CLI** | `gdrive_sdp_governance/verify_posture.py`, `tests/test_governance.py` | Offline RFC-1034 ID, multi-region parity, and filter mutual-exclusion validation (`--dry-run`) + read-only live GCP posture auditing |

---

## Directory Layout

```text
Lab 8- Add Google Drive with Sensitive Data Protection to Gemini Enterprise/
├── RUNBOOK.md                              # Step-by-step runbook, Mermaid architecture & workflow diagrams
├── README.md                               # Governance stack overview, directory layout & quick verification
├── .gitignore                              # Excludes .env secrets, .venv, __pycache__ & credentials
├── configs/
│   ├── content_policy_pii_labels.json      # Reference SDP ContentPolicy (PII + hotword rule + Drive label + BigQuery log)
│   └── gdrive_connector_payload.json       # Reference Discovery Engine setUpDataConnector (FEDERATED + SDP policy)
├── gdrive_sdp_governance/
│   ├── __init__.py                         # Package exports
│   ├── builder.py                          # Schema-validated builders for ContentPolicy, Drive Connector & App Engine
│   └── verify_posture.py                   # Offline --dry-run bundle generator & live read-only GCP posture auditor
└── tests/
    └── test_governance.py                  # Zero-dependency offline unit test suite (16 tests, unittest & pytest compatible)
```

---

## Enforcement Surfaces & Guardrails at a Glance

| Surface | Policy Attachment Field / Path | Verdict Effect on Violation (`BLOCK`) | Propagation Latency |
|---|---|---|---|
| **Google Drive Connector Retrieval** | `DataConnector.dataProtectionPolicy.sensitiveDataProtectionPolicy.policy` | Violating Drive files/entities are dropped before grounding; clean files still ground answers | **Immediate** |
| **Gemini Enterprise Assistant Uploads** | **App $\rightarrow$ Security $\rightarrow$ SDP $\rightarrow$ Assistant setting** | Local, Google Drive, and OneDrive file uploads into chat fail immediately | **Immediate** |
| **Gemini Notebook Enterprise Uploads** | **App $\rightarrow$ Security $\rightarrow$ SDP $\rightarrow$ NotebookLM setting** | Uploaded notebook sources are rejected (*"Unable to import this source. It violates policies"*) across all regional notebooks in the project | **~10 minutes** |
| **Oversized / Corrupted Files** | `ContentPolicy.inputTooLarge` & `failedToScanSupportedFileType` | Setting `BLOCK` overrides the permissive `ALLOW` default for files exceeding SDP limits (`50 MB` PDF, `30 MB` Office, `10 MB` text/image) | **Immediate** |

---

## Quick Verification

### 1. Run Offline Schema & Governance Unit Tests (16 Passing Tests)

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

### 2. Generate a Validated REST Provisioning Bundle Offline (`--dry-run`)

```bash
PYTHONPATH=. python3 -m gdrive_sdp_governance.verify_posture \
  --project-id "<PROJECT_ID>" \
  --project-number "<PROJECT_NUMBER>" \
  --location global \
  --folder-id "<FOLDER_ID>" \
  --dry-run
```

### 3. Audit Live GCP Lab Posture (Read-Only)

```bash
PYTHONPATH=. python3 -m gdrive_sdp_governance.verify_posture \
  --project-id "<PROJECT_ID>" \
  --location global \
  --policy-id gdrive-enterprise-sdp-policy \
  --collection-id gdrive-governed-connector \
  --app-id enterprise-workspace-assistant
```

---

## Official References

- [Protect Sensitive Data in Gemini Enterprise Sources & Uploads](https://docs.cloud.google.com/gemini/enterprise/docs/protect-sensitive-data)
- [Set Up a Google Drive Data Store in Gemini Enterprise](https://docs.cloud.google.com/gemini/enterprise/docs/connectors/gdrive/set-up-data-store)
- [Google Drive Connector Overview, Supported Actions & Limits](https://docs.cloud.google.com/gemini/enterprise/docs/connectors/gdrive)
- [Add Folder & Shared Drive Filters to a Google Drive Data Store](https://docs.cloud.google.com/gemini/enterprise/docs/connectors/gdrive/add-filters-to-gdrive-data-store)
- [Sensitive Data Protection Content Policies Overview & Management](https://docs.cloud.google.com/sensitive-data-protection/docs/manage-content-policies)
- [Create Custom Metadata Label Detectors (`googleDriveLabel` & `sensitivityLabel`)](https://docs.cloud.google.com/sensitive-data-protection/docs/create-custom-infotypes-metadata-labels)
- [Enable Model Armor for Gemini Enterprise](https://docs.cloud.google.com/gemini/enterprise/docs/enable-model-armor)
