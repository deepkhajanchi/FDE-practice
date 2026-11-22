"""Zero-dependency offline unit tests (compatible with both unittest and pytest) for Lab 8."""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from gdrive_sdp_governance import (
    GOOGLE_MANAGED_DRIVE_OAUTH_CLIENT_ID,
    build_connector_filter_patch,
    build_connector_sdp_patch,
    build_content_policy_payload,
    build_gemini_enterprise_app_payload,
    build_google_drive_connector_payload,
    discovery_engine_endpoint,
    discovery_engine_service_agent,
    dlp_endpoint,
    parse_content_policy_name,
    validate_collection_id,
    validate_location,
)
from gdrive_sdp_governance.verify_posture import main as cli_main

LAB_ROOT = Path(__file__).resolve().parent.parent


class TestValidatorsAndEndpoints(unittest.TestCase):
    def test_valid_locations(self) -> None:
        for loc in ("global", "us", "eu", "GLOBAL", " us "):
            self.assertIn(validate_location(loc), {"global", "us", "eu"})

    def test_invalid_locations_rejected(self) -> None:
        for bad_loc in ("us-central1", "asia-east1", "", "europe"):
            with self.assertRaisesRegex(ValueError, "Unsupported location"):
                validate_location(bad_loc)

    def test_valid_collection_ids(self) -> None:
        for valid_id in ("a", "gdrive-connector-1", "cymbal_drive_prod_01", "a" * 63):
            self.assertEqual(validate_collection_id(valid_id), valid_id)

    def test_invalid_collection_ids_rejected(self) -> None:
        for bad_id in (
            "",
            "123-cymbal-collection",
            "Uppercase-Collection",
            "trailing-hyphen-",
            "trailing_underscore_",
            "a" * 64,
            "has spaces",
        ):
            with self.assertRaisesRegex(ValueError, "Invalid collectionId"):
                validate_collection_id(bad_id)

    def test_service_agent_and_oauth_constants(self) -> None:
        self.assertEqual(
            discovery_engine_service_agent(612130106124),
            "service-612130106124@gcp-sa-discoveryengine.iam.gserviceaccount.com",
        )
        self.assertTrue(GOOGLE_MANAGED_DRIVE_OAUTH_CLIENT_ID.endswith(".apps.googleusercontent.com"))
        with self.assertRaisesRegex(ValueError, "numeric"):
            discovery_engine_service_agent("not-a-number")

    def test_endpoint_routing(self) -> None:
        self.assertEqual(discovery_engine_endpoint("global"), "https://discoveryengine.googleapis.com")
        self.assertEqual(discovery_engine_endpoint("us"), "https://us-discoveryengine.googleapis.com")
        self.assertEqual(discovery_engine_endpoint("eu"), "https://eu-discoveryengine.googleapis.com")
        self.assertEqual(dlp_endpoint("global"), "https://dlp.googleapis.com")
        self.assertEqual(dlp_endpoint("us-west2"), "https://dlp.us-west2.rep.googleapis.com")


class TestContentPolicyBuilder(unittest.TestCase):
    def test_builds_standard_pii_and_drive_label_policy(self) -> None:
        payload = build_content_policy_payload(
            content_policy_id="gdrive-sdp-01",
            display_name="Drive Inbound SDP",
            info_types=["US_SOCIAL_SECURITY_NUMBER", "CREDIT_CARD_NUMBER"],
            google_drive_label={
                "custom_info_type_name": "CUSTOM_GOOGLE_DRIVE_LABEL_CONFIDENTIAL",
                "label_id": "lbl-123",
                "field_id": "sensitivity",
                "field_value": "confidential",
            },
            bigquery_log_target={
                "projectId": "my-sec-proj",
                "datasetId": "sdp_logs",
                "tableId": "verdicts",
            },
        )
        cp = payload["contentPolicy"]
        self.assertEqual(payload["contentPolicyId"], "gdrive-sdp-01")
        self.assertEqual(
            [i["name"] for i in cp["inspectConfig"]["infoTypes"]],
            ["US_SOCIAL_SECURITY_NUMBER", "CREDIT_CARD_NUMBER"],
        )
        custom = cp["inspectConfig"]["customInfoTypes"][0]
        self.assertEqual(custom["fileLabelInfoType"]["googleDriveLabel"]["labelId"], "lbl-123")
        self.assertEqual(cp["rules"][0]["action"]["returnVerdict"], "BLOCK")
        self.assertEqual(cp["defaultAction"]["returnVerdict"], "ALLOW")
        self.assertEqual(cp["inputTooLarge"]["returnVerdict"], "BLOCK")
        self.assertEqual(cp["loggingConfigs"][0]["logToBigQuery"]["datasetId"], "sdp_logs")

    def test_rejects_metadata_label_detector_in_ruleset(self) -> None:
        with self.assertRaisesRegex(ValueError, "Custom metadata label detectors cannot be used"):
            build_content_policy_payload(
                content_policy_id="bad-ruleset",
                display_name="Invalid Ruleset",
                info_types=["CREDIT_CARD_NUMBER"],
                google_drive_label={
                    "custom_info_type_name": "CUSTOM_DRIVE_LABEL",
                    "label_id": "lbl-123",
                },
                rule_set=[
                    {
                        "infoTypes": [{"name": "CUSTOM_DRIVE_LABEL"}],
                        "rules": [],
                    }
                ],
            )


class TestGoogleDriveConnectorAndAppBuilders(unittest.TestCase):
    def test_builds_federated_connector_with_inline_sdp_and_filters(self) -> None:
        policy_name = "projects/demo-proj-01/locations/global/contentPolicies/gdrive-sdp"
        payload = build_google_drive_connector_payload(
            collection_id="gdrive-governed",
            collection_display_name="Governed Drive",
            connector_location="global",
            content_policy_name=policy_name,
            included_folder_ids=["1AbCdEfGhIjKlMnOpQrStUv"],
            enable_actions=True,
            tag="gdrive-v1",
        )
        dc = payload["dataConnector"]
        self.assertEqual(dc["dataSource"], "google_drive")
        self.assertEqual(dc["connectorModes"], ["FEDERATED", "ACTION"])
        self.assertEqual(dc["params"]["admin_filter"]["FolderIds"], ["1AbCdEfGhIjKlMnOpQrStUv"])
        self.assertEqual(dc["dataProtectionPolicy"]["sensitiveDataProtectionPolicy"]["policy"], policy_name)

    def test_rejects_region_mismatch_between_policy_and_connector(self) -> None:
        with self.assertRaisesRegex(ValueError, "Region mismatch"):
            build_google_drive_connector_payload(
                collection_id="gdrive-us",
                collection_display_name="US Drive",
                connector_location="us",
                content_policy_name="projects/demo-proj-01/locations/global/contentPolicies/pol1",
            )

    def test_rejects_simultaneous_include_and_exclude_filters(self) -> None:
        with self.assertRaisesRegex(ValueError, "Cannot configure both included and excluded FolderIds"):
            build_google_drive_connector_payload(
                collection_id="gdrive-conflict",
                collection_display_name="Conflict",
                included_folder_ids=["folder-a"],
                excluded_folder_ids=["folder-b"],
            )

    def test_rejects_cmek_on_global_connector(self) -> None:
        with self.assertRaisesRegex(ValueError, "only supported in 'us' or 'eu'"):
            build_google_drive_connector_payload(
                collection_id="gdrive-cmek",
                collection_display_name="CMEK Global",
                connector_location="global",
                kms_key_name="projects/p/locations/global/keyRings/kr/cryptoKeys/k",
            )

    def test_patch_helpers_attach_detach_and_reset_filters(self) -> None:
        mask, attach = build_connector_sdp_patch(
            connector_location="eu",
            content_policy_name="projects/demo-proj-01/locations/eu/contentPolicies/eu-pol",
        )
        self.assertEqual(mask, "dataProtectionPolicy")
        self.assertTrue(attach["dataProtectionPolicy"]["sensitiveDataProtectionPolicy"]["policy"].endswith("/eu-pol"))

        _, detach = build_connector_sdp_patch(connector_location="eu", content_policy_name=None)
        self.assertEqual(detach["dataProtectionPolicy"]["sensitiveDataProtectionPolicy"]["policy"], "")

        fmask, clear_filters = build_connector_filter_patch()
        self.assertEqual(fmask, "params")
        self.assertEqual(clear_filters["params"]["admin_filter"], {"SharedDriveIds": [], "FolderIds": []})
        self.assertEqual(clear_filters["params"]["admin_exclusion_filter"], {"SharedDriveIds": [], "FolderIds": []})

    def test_gemini_enterprise_app_payload(self) -> None:
        app = build_gemini_enterprise_app_payload(
            app_display_name="Enterprise Search & Assistant",
            data_store_ids=["gdrive-governed_google_drive"],
            company_name="Cymbal",
            include_cross_domain_documents=False,
        )
        self.assertEqual(app["appType"], "APP_TYPE_INTRANET")
        self.assertEqual(app["solutionType"], "SOLUTION_TYPE_SEARCH")
        self.assertEqual(app["dataStoreIds"], ["gdrive-governed_google_drive"])
        self.assertNotIn("includeCrossDomainDocuments", app)


class TestReferenceConfigsAndDryRunCLI(unittest.TestCase):
    def test_reference_json_configs_parse_cleanly(self) -> None:
        cp_cfg = json.loads((LAB_ROOT / "configs" / "content_policy_pii_labels.json").read_text())
        self.assertEqual(cp_cfg["contentPolicyId"], "gdrive-enterprise-sdp-policy")
        self.assertEqual(cp_cfg["contentPolicy"]["rules"][0]["action"]["returnVerdict"], "BLOCK")

        dc_cfg = json.loads((LAB_ROOT / "configs" / "gdrive_connector_payload.json").read_text())
        validate_collection_id(dc_cfg["collectionId"])
        self.assertEqual(dc_cfg["dataConnector"]["dataSource"], "google_drive")
        self.assertEqual(dc_cfg["dataConnector"]["connectorModes"], ["FEDERATED"])

    def test_dry_run_cli_and_bundle(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_main(
                [
                    "--project-id",
                    "cymbal-prod-123",
                    "--project-number",
                    "987654321098",
                    "--location",
                    "global",
                    "--folder-id",
                    "1FolderIdExample",
                    "--dry-run",
                ]
            )
        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(
            out["metadata"]["discovery_engine_service_agent"],
            "service-987654321098@gcp-sa-discoveryengine.iam.gserviceaccount.com",
        )
        self.assertEqual(len(out["requests"]), 3)
        parsed = parse_content_policy_name(
            out["requests"][1]["body"]["dataConnector"]["dataProtectionPolicy"][
                "sensitiveDataProtectionPolicy"
            ]["policy"]
        )
        self.assertEqual(parsed["project"], "cymbal-prod-123")
        self.assertEqual(parsed["location"], "global")


if __name__ == "__main__":
    unittest.main()
