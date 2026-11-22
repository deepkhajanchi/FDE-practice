"""REST payload builders and schema validators for Lab 8 (Google Drive + SDP + Gemini Enterprise)."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

SUPPORTED_LOCATIONS: frozenset[str] = frozenset({"global", "us", "eu"})
SUPPORTED_VERDICTS: frozenset[str] = frozenset({"ALLOW", "BLOCK"})
GOOGLE_MANAGED_DRIVE_OAUTH_CLIENT_ID: str = (
    "502998392228-hpelhql0ouj9ckiu3l39lllsir24b02s.apps.googleusercontent.com"
)

_COLLECTION_ID_RE = re.compile(r"^[a-z](?:[a-z0-9_-]{0,61}[a-z0-9])?$")
_CONTENT_POLICY_RE = re.compile(
    r"^projects/(?P<project>[a-z0-9][a-z0-9-]{4,29})/locations/(?P<location>[a-z0-9-]+)/contentPolicies/(?P<policy_id>[A-Za-z0-9_-]+)$"
)


def validate_location(location: str) -> str:
    """Validate that a multi-region is supported by Gemini Enterprise Drive + SDP."""
    loc = (location or "").strip().lower()
    if loc not in SUPPORTED_LOCATIONS:
        raise ValueError(
            f"Unsupported location '{location}'. Gemini Enterprise Google Drive + SDP requires one of: "
            f"{sorted(SUPPORTED_LOCATIONS)}."
        )
    return loc


def validate_collection_id(collection_id: str) -> str:
    """Validate Discovery Engine DataConnector collectionId naming rules (1-63 chars)."""
    cid = (collection_id or "").strip()
    if not _COLLECTION_ID_RE.match(cid):
        raise ValueError(
            f"Invalid collectionId '{collection_id}'. Must be 1-63 chars, start with a lowercase letter, "
            "end with a lowercase letter or digit, and contain only [a-z0-9_-]."
        )
    return cid


def parse_content_policy_name(policy_resource_name: str) -> dict[str, str]:
    """Parse and validate a full SDP ContentPolicy resource name."""
    match = _CONTENT_POLICY_RE.match((policy_resource_name or "").strip())
    if not match:
        raise ValueError(
            f"Invalid ContentPolicy resource name '{policy_resource_name}'. Expected "
            "'projects/<PROJECT_ID>/locations/<LOCATION>/contentPolicies/<POLICY_ID>'."
        )
    return match.groupdict()


def discovery_engine_service_agent(project_number: str | int) -> str:
    """Return the canonical Discovery Engine service agent email requiring roles/dlp.user."""
    num = str(project_number).strip()
    if not num.isdigit():
        raise ValueError(f"project_number must be numeric, got '{project_number}'.")
    return f"service-{num}@gcp-sa-discoveryengine.iam.gserviceaccount.com"


def discovery_engine_endpoint(location: str) -> str:
    """Return the multi-regional Discovery Engine base URL."""
    loc = validate_location(location)
    if loc == "global":
        return "https://discoveryengine.googleapis.com"
    return f"https://{loc}-discoveryengine.googleapis.com"


def dlp_endpoint(location: str) -> str:
    """Return the Sensitive Data Protection base URL (global vs. regional REP)."""
    loc = (location or "").strip().lower()
    if not loc:
        raise ValueError("location must be non-empty.")
    if loc in {"global", "us", "eu"}:
        return "https://dlp.googleapis.com"
    return f"https://dlp.{loc}.rep.googleapis.com"


def _validate_verdict(name: str, verdict: str) -> str:
    v = (verdict or "").strip().upper()
    if v not in SUPPORTED_VERDICTS:
        raise ValueError(f"{name} must be one of {sorted(SUPPORTED_VERDICTS)}, got '{verdict}'.")
    return v


def build_content_policy_payload(
    *,
    content_policy_id: str,
    display_name: str,
    info_types: Sequence[str],
    min_likelihood: str = "LIKELY",
    verdict_on_match: str = "BLOCK",
    default_verdict: str = "ALLOW",
    unsupported_file_verdict: str = "ALLOW",
    input_too_large_verdict: str = "BLOCK",
    failed_to_scan_verdict: str = "BLOCK",
    google_drive_label: Mapping[str, Any] | None = None,
    rule_set: Sequence[Mapping[str, Any]] | None = None,
    bigquery_log_target: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build a validated Sensitive Data Protection contentPolicies.create request payload."""
    policy_id = (content_policy_id or "").strip()
    if not policy_id:
        raise ValueError("content_policy_id must be non-empty.")
    if not info_types and not google_drive_label:
        raise ValueError("At least one built-in info_type or google_drive_label detector must be configured.")

    match_verdict = _validate_verdict("verdict_on_match", verdict_on_match)
    def_verdict = _validate_verdict("default_verdict", default_verdict)
    unsup_verdict = _validate_verdict("unsupported_file_verdict", unsupported_file_verdict)
    large_verdict = _validate_verdict("input_too_large_verdict", input_too_large_verdict)
    fail_verdict = _validate_verdict("failed_to_scan_verdict", failed_to_scan_verdict)

    inspect_config: dict[str, Any] = {
        "infoTypes": [{"name": it.strip()} for it in info_types if it.strip()],
        "minLikelihood": min_likelihood,
    }

    label_detector_names: set[str] = set()
    if google_drive_label:
        custom_name = str(
            google_drive_label.get("custom_info_type_name", "CUSTOM_GOOGLE_DRIVE_LABEL_CONFIDENTIAL")
        ).strip()
        label_id = str(google_drive_label.get("label_id", "")).strip()
        if not label_id:
            raise ValueError("google_drive_label requires a non-empty 'label_id'.")
        drive_label_spec: dict[str, Any] = {"labelId": label_id}
        field_id = google_drive_label.get("field_id")
        field_value = google_drive_label.get("field_value")
        if field_id or field_value:
            if not (field_id and field_value):
                raise ValueError("Both 'field_id' and 'field_value' are required when matching label fields.")
            drive_label_spec["labelFieldsToMatch"] = [{"id": str(field_id), "value": str(field_value)}]

        inspect_config["customInfoTypes"] = [
            {
                "infoType": {"name": custom_name},
                "likelihood": str(google_drive_label.get("likelihood", "VERY_LIKELY")),
                "fileLabelInfoType": {"googleDriveLabel": drive_label_spec},
            }
        ]
        label_detector_names.add(custom_name)

    if rule_set:
        for rs in rule_set:
            targets = {t.get("name", "") for t in rs.get("infoTypes", [])}
            overlap = targets & label_detector_names
            if overlap:
                raise ValueError(
                    f"Custom metadata label detectors cannot be used inside inspectConfig.ruleSet: {sorted(overlap)}."
                )
        inspect_config["ruleSet"] = list(rule_set)

    content_policy: dict[str, Any] = {
        "displayName": display_name,
        "inspectConfig": inspect_config,
        "rules": [
            {
                "conditions": [{"infoTypeCondition": {"anyInfoType": {}}}],
                "action": {"returnVerdict": match_verdict},
            }
        ],
        "unsupportedFileType": {"returnVerdict": unsup_verdict},
        "inputTooLarge": {"returnVerdict": large_verdict},
        "failedToScanSupportedFileType": {"returnVerdict": fail_verdict},
        "defaultAction": {"returnVerdict": def_verdict},
    }

    if bigquery_log_target:
        for required_key in ("projectId", "datasetId", "tableId"):
            if not bigquery_log_target.get(required_key):
                raise ValueError(f"bigquery_log_target missing required key '{required_key}'.")
        content_policy["loggingConfigs"] = [
            {
                "logToBigQuery": {
                    "projectId": bigquery_log_target["projectId"],
                    "datasetId": bigquery_log_target["datasetId"],
                    "tableId": bigquery_log_target["tableId"],
                }
            }
        ]

    return {
        "contentPolicyId": policy_id,
        "contentPolicy": content_policy,
    }


def _build_drive_filter_params(
    *,
    included_shared_drive_ids: Sequence[str] | None = None,
    excluded_shared_drive_ids: Sequence[str] | None = None,
    included_folder_ids: Sequence[str] | None = None,
    excluded_folder_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    if included_shared_drive_ids and excluded_shared_drive_ids:
        raise ValueError("Cannot configure both included and excluded SharedDriveIds simultaneously.")
    if included_folder_ids and excluded_folder_ids:
        raise ValueError("Cannot configure both included and excluded FolderIds simultaneously.")

    params: dict[str, Any] = {}
    admin_filter: dict[str, list[str]] = {}
    admin_exclusion_filter: dict[str, list[str]] = {}

    if included_shared_drive_ids is not None:
        admin_filter["SharedDriveIds"] = list(included_shared_drive_ids)
    if included_folder_ids is not None:
        admin_filter["FolderIds"] = list(included_folder_ids)
    if excluded_shared_drive_ids is not None:
        admin_exclusion_filter["SharedDriveIds"] = list(excluded_shared_drive_ids)
    if excluded_folder_ids is not None:
        admin_exclusion_filter["FolderIds"] = list(excluded_folder_ids)

    if admin_filter:
        params["admin_filter"] = admin_filter
    if admin_exclusion_filter:
        params["admin_exclusion_filter"] = admin_exclusion_filter
    return params


def build_google_drive_connector_payload(
    *,
    collection_id: str,
    collection_display_name: str,
    connector_location: str = "global",
    content_policy_name: str | None = None,
    tag: str | None = None,
    included_shared_drive_ids: Sequence[str] | None = None,
    excluded_shared_drive_ids: Sequence[str] | None = None,
    included_folder_ids: Sequence[str] | None = None,
    excluded_folder_ids: Sequence[str] | None = None,
    enable_actions: bool = False,
    kms_key_name: str | None = None,
) -> dict[str, Any]:
    """Build a validated projects.locations:setUpDataConnector payload for Google Drive."""
    loc = validate_location(connector_location)
    cid = validate_collection_id(collection_id)
    if not (collection_display_name or "").strip():
        raise ValueError("collection_display_name must be non-empty.")

    modes = ["FEDERATED"]
    if enable_actions:
        modes.append("ACTION")

    connector: dict[str, Any] = {
        "dataSource": "google_drive",
        "entities": [{"entityName": "google_drive"}],
        "connectorModes": modes,
    }

    if tag:
        connector["tag"] = tag.strip()

    if kms_key_name:
        if loc == "global":
            raise ValueError("Cloud KMS CMEK keys on Google Drive connectors are only supported in 'us' or 'eu'.")
        connector["kmsKeyName"] = kms_key_name

    params = _build_drive_filter_params(
        included_shared_drive_ids=included_shared_drive_ids,
        excluded_shared_drive_ids=excluded_shared_drive_ids,
        included_folder_ids=included_folder_ids,
        excluded_folder_ids=excluded_folder_ids,
    )
    if params:
        connector["params"] = params

    if content_policy_name:
        parsed = parse_content_policy_name(content_policy_name)
        if parsed["location"] != loc:
            raise ValueError(
                f"Region mismatch: ContentPolicy is in '{parsed['location']}' but Drive connector is in '{loc}'. "
                "Both resources must reside in the same multi-region."
            )
        connector["dataProtectionPolicy"] = {
            "sensitiveDataProtectionPolicy": {
                "policy": content_policy_name.strip(),
            }
        }

    return {
        "collectionId": cid,
        "collectionDisplayName": collection_display_name.strip(),
        "dataConnector": connector,
    }


def build_connector_sdp_patch(
    *,
    connector_location: str,
    content_policy_name: str | None,
) -> tuple[str, dict[str, Any]]:
    """Build (updateMask, payload) to attach or remove an SDP ContentPolicy on an existing DataConnector."""
    loc = validate_location(connector_location)
    update_mask = "dataProtectionPolicy"
    if not content_policy_name:
        return update_mask, {"dataProtectionPolicy": {"sensitiveDataProtectionPolicy": {"policy": ""}}}

    parsed = parse_content_policy_name(content_policy_name)
    if parsed["location"] != loc:
        raise ValueError(
            f"Region mismatch: ContentPolicy is in '{parsed['location']}' but DataConnector is in '{loc}'."
        )
    return update_mask, {
        "dataProtectionPolicy": {
            "sensitiveDataProtectionPolicy": {
                "policy": content_policy_name.strip(),
            }
        }
    }


def build_connector_filter_patch(
    *,
    included_shared_drive_ids: Sequence[str] | None = None,
    excluded_shared_drive_ids: Sequence[str] | None = None,
    included_folder_ids: Sequence[str] | None = None,
    excluded_folder_ids: Sequence[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build (updateMask, payload) to update or clear Drive scoping filters on an existing DataConnector."""
    params = _build_drive_filter_params(
        included_shared_drive_ids=included_shared_drive_ids,
        excluded_shared_drive_ids=excluded_shared_drive_ids,
        included_folder_ids=included_folder_ids,
        excluded_folder_ids=excluded_folder_ids,
    )
    if not params:
        params = {
            "admin_filter": {"SharedDriveIds": [], "FolderIds": []},
            "admin_exclusion_filter": {"SharedDriveIds": [], "FolderIds": []},
        }
    return "params", {"params": params}


def build_gemini_enterprise_app_payload(
    *,
    app_display_name: str,
    data_store_ids: Sequence[str],
    company_name: str | None = None,
    include_cross_domain_documents: bool = False,
) -> dict[str, Any]:
    """Build a Discovery Engine v1 engines.create payload for a Gemini Enterprise intranet app."""
    if not (app_display_name or "").strip():
        raise ValueError("app_display_name must be non-empty.")
    ds_ids = [d.strip() for d in data_store_ids if d.strip()]
    if not ds_ids:
        raise ValueError("At least one data_store_id (e.g. '<collection_id>_google_drive') is required.")

    payload: dict[str, Any] = {
        "displayName": app_display_name.strip(),
        "dataStoreIds": ds_ids,
        "solutionType": "SOLUTION_TYPE_SEARCH",
        "industryVertical": "GENERIC",
        "appType": "APP_TYPE_INTRANET",
    }
    if company_name:
        payload["commonConfig"] = {"companyName": company_name.strip()}
    if include_cross_domain_documents:
        payload["includeCrossDomainDocuments"] = True
    return payload
