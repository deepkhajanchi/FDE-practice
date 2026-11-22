#!/usr/bin/env python3
"""Read-only posture verifier & dry-run payload generator for Lab 8.

Checks (in live mode) or renders (in --dry-run mode):
  1. Required APIs (discoveryengine.googleapis.com, dlp.googleapis.com)
  2. Discovery Engine Service Agent IAM binding (roles/dlp.user)
  3. Sensitive Data Protection ContentPolicy existence & region alignment
  4. Federated Google Drive DataConnector state & attached dataProtectionPolicy
  5. Gemini Enterprise App (APP_TYPE_INTRANET) connected to the Google Drive DataStore
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any

from .builder import (
    GOOGLE_MANAGED_DRIVE_OAUTH_CLIENT_ID,
    build_content_policy_payload,
    build_gemini_enterprise_app_payload,
    build_google_drive_connector_payload,
    discovery_engine_endpoint,
    discovery_engine_service_agent,
    dlp_endpoint,
    validate_location,
)


def _fetch_json(url: str, headers: dict[str, str], method: str = "GET", body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req_headers = dict(headers)
    if data is not None:
        req_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def render_dry_run_bundle(
    *,
    project_id: str,
    project_number: str,
    location: str,
    policy_id: str,
    collection_id: str,
    app_id: str,
    folder_id: str | None = None,
) -> dict[str, Any]:
    """Generate a complete, schema-validated REST bundle without making network calls."""
    loc = validate_location(location)
    policy_resource = f"projects/{project_id}/locations/{loc}/contentPolicies/{policy_id}"
    service_agent = discovery_engine_service_agent(project_number)

    policy_payload = build_content_policy_payload(
        content_policy_id=policy_id,
        display_name="Gemini Enterprise Google Drive SDP Policy",
        info_types=[
            "US_SOCIAL_SECURITY_NUMBER",
            "CREDIT_CARD_NUMBER",
            "EMAIL_ADDRESS",
            "PHONE_NUMBER",
        ],
        min_likelihood="LIKELY",
        verdict_on_match="BLOCK",
        default_verdict="ALLOW",
        input_too_large_verdict="BLOCK",
        failed_to_scan_verdict="BLOCK",
    )

    connector_payload = build_google_drive_connector_payload(
        collection_id=collection_id,
        collection_display_name="Google Drive (SDP Governed)",
        connector_location=loc,
        content_policy_name=policy_resource,
        tag="gdrive-governed",
        included_folder_ids=[folder_id] if folder_id else None,
    )

    data_store_entity_id = f"{collection_id}_google_drive"
    app_payload = build_gemini_enterprise_app_payload(
        app_display_name=app_id,
        data_store_ids=[data_store_entity_id],
        company_name="Cymbal",
    )

    return {
        "metadata": {
            "project_id": project_id,
            "project_number": project_number,
            "location": loc,
            "discovery_engine_service_agent": service_agent,
            "required_service_agent_role": "roles/dlp.user",
            "google_managed_oauth_client_id": GOOGLE_MANAGED_DRIVE_OAUTH_CLIENT_ID,
        },
        "requests": [
            {
                "step": "1_create_sdp_content_policy",
                "method": "POST",
                "url": f"{dlp_endpoint(loc)}/v2/projects/{project_id}/locations/{loc}/contentPolicies",
                "body": policy_payload,
            },
            {
                "step": "2_setup_google_drive_connector",
                "method": "POST",
                "url": f"{discovery_engine_endpoint(loc)}/v1alpha/projects/{project_id}/locations/{loc}:setUpDataConnector",
                "body": connector_payload,
            },
            {
                "step": "3_create_gemini_enterprise_app",
                "method": "POST",
                "url": (
                    f"{discovery_engine_endpoint(loc)}/v1/projects/{project_id}/locations/{loc}"
                    f"/collections/default_collection/engines?engineId={app_id}"
                ),
                "body": app_payload,
            },
        ],
    }


def verify_live_posture(
    *,
    project_id: str,
    location: str,
    policy_id: str,
    collection_id: str,
    app_id: str | None = None,
) -> int:
    """Audit live GCP project posture for Lab 8 checkpoints (read-only)."""
    import google.auth
    import google.auth.transport.requests

    loc = validate_location(location)
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "X-Goog-User-Project": project_id,
    }

    failures = 0

    def record(ok: bool, label: str, detail: str) -> None:
        nonlocal failures
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"[{status}] {label}: {detail}")

    # 1. Project Number & IAM binding check
    try:
        proj_meta = _fetch_json(
            f"https://cloudresourcemanager.googleapis.com/v1/projects/{project_id}",
            headers,
        )
        project_number = proj_meta["projectNumber"]
        sa_email = discovery_engine_service_agent(project_number)
        iam = _fetch_json(
            f"https://cloudresourcemanager.googleapis.com/v1/projects/{project_id}:getIamPolicy",
            headers,
            method="POST",
            body={},
        )
        dlp_members = set()
        for binding in iam.get("bindings", []):
            if binding.get("role") in {"roles/dlp.user", "roles/dlp.admin"}:
                dlp_members.update(binding.get("members", []))
        has_dlp = f"serviceAccount:{sa_email}" in dlp_members
        record(has_dlp, "Discovery Engine SA DLP Role", f"{sa_email} -> roles/dlp.user={has_dlp}")
    except urllib.error.HTTPError as exc:
        record(False, "Project IAM Inspection", f"HTTP {exc.code}: {exc.reason}")

    # 2. SDP ContentPolicy check
    expected_policy = f"projects/{project_id}/locations/{loc}/contentPolicies/{policy_id}"
    try:
        pol = _fetch_json(f"{dlp_endpoint(loc)}/v2/{expected_policy}", headers)
        rules_cnt = len(pol.get("rules", []))
        record(True, "SDP ContentPolicy", f"{pol.get('name')} ({rules_cnt} rule(s))")
    except urllib.error.HTTPError as exc:
        record(False, "SDP ContentPolicy", f"{expected_policy} -> HTTP {exc.code}")

    # 3. Google Drive DataConnector check
    connector_url = (
        f"{discovery_engine_endpoint(loc)}/v1alpha/projects/{project_id}"
        f"/locations/{loc}/collections/{collection_id}/dataConnector"
    )
    try:
        conn = _fetch_json(connector_url, headers)
        state = conn.get("state", "UNKNOWN")
        src = conn.get("dataSource", "")
        attached = (
            conn.get("dataProtectionPolicy", {})
            .get("sensitiveDataProtectionPolicy", {})
            .get("policy", "")
        )
        record(
            src == "google_drive" and state == "ACTIVE",
            "Google Drive DataConnector State",
            f"dataSource={src}, state={state}",
        )
        record(
            attached == expected_policy,
            "Connector Attached SDP Policy",
            f"attached='{attached}' (expected '{expected_policy}')",
        )
    except urllib.error.HTTPError as exc:
        record(False, "Google Drive DataConnector", f"{connector_url} -> HTTP {exc.code}")

    # 4. Optional Gemini Enterprise App check
    if app_id:
        eng_url = (
            f"{discovery_engine_endpoint(loc)}/v1/projects/{project_id}/locations/{loc}"
            f"/collections/default_collection/engines/{app_id}"
        )
        try:
            eng = _fetch_json(eng_url, headers)
            ds_ids = eng.get("dataStoreIds", [])
            record(
                eng.get("appType") == "APP_TYPE_INTRANET" and bool(ds_ids),
                "Gemini Enterprise App",
                f"appType={eng.get('appType')}, dataStoreIds={ds_ids}",
            )
        except urllib.error.HTTPError as exc:
            record(False, "Gemini Enterprise App", f"{eng_url} -> HTTP {exc.code}")

    return 0 if failures == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True, help="Google Cloud Project ID")
    parser.add_argument("--project-number", default="123456789012", help="Project Number (used in --dry-run)")
    parser.add_argument("--location", default="global", choices=["global", "us", "eu"], help="Multi-region")
    parser.add_argument("--policy-id", default="gdrive-enterprise-sdp-policy", help="SDP ContentPolicy ID")
    parser.add_argument("--collection-id", default="gdrive-governed-connector", help="Drive Connector Collection ID")
    parser.add_argument("--app-id", default="gemini-enterprise-app", help="Gemini Enterprise App (Engine) ID")
    parser.add_argument("--folder-id", default=None, help="Optional Google Drive Folder ID to include")
    parser.add_argument("--dry-run", action="store_true", help="Emit validated REST bundle offline without API calls")
    args = parser.parse_args(argv)

    if args.dry_run:
        bundle = render_dry_run_bundle(
            project_id=args.project_id,
            project_number=args.project_number,
            location=args.location,
            policy_id=args.policy_id,
            collection_id=args.collection_id,
            app_id=args.app_id,
            folder_id=args.folder_id,
        )
        print(json.dumps(bundle, indent=2))
        return 0

    return verify_live_posture(
        project_id=args.project_id,
        location=args.location,
        policy_id=args.policy_id,
        collection_id=args.collection_id,
        app_id=args.app_id,
    )


if __name__ == "__main__":
    sys.exit(main())
