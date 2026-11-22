# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Offline tests for the Agent Identity AuthenticatedFunctionTool and SalesforceClient."""

import io
from unittest.mock import AsyncMock, MagicMock

import pytest
import requests
from docx import Document
from google.adk.auth.auth_credential import (
    AuthCredential,
    AuthCredentialTypes,
    HttpAuth,
    HttpCredentials,
    OAuth2Auth,
)

from app.agent import search_salesforce
from app.salesforce_client import (
    SalesforceClient,
    _build_excerpt,
    _build_sosl,
    _escape_sosl,
    _extract_text,
    _file_name,
)


def _bearer_credential(token: str = "managed-2lo-token") -> AuthCredential:
    return AuthCredential(
        auth_type=AuthCredentialTypes.HTTP,
        http=HttpAuth(
            scheme="Bearer",
            credentials=HttpCredentials(token=token),
        ),
    )


def _http_error(status: int) -> requests.HTTPError:
    resp = MagicMock()
    resp.status_code = status
    return requests.HTTPError(f"{status} boom", response=resp)


# --- AuthenticatedFunctionTool behavior ---------------------------------------


@pytest.mark.asyncio
async def test_search_salesforce_via_agent_identity_credential(mocker) -> None:
    """Happy path: CredentialManager supplies an HTTP Bearer AuthCredential and search succeeds."""
    tool_context = MagicMock()
    tool_context.user_id = "engineer@example.com"

    mocker.patch.object(
        search_salesforce._credentials_manager,
        "get_auth_credential",
        new=AsyncMock(return_value=_bearer_credential("managed-2lo-token")),
    )
    mock_search = mocker.patch(
        "app.salesforce_client.SalesforceClient.search_files",
        return_value=[
            {
                "name": "adr-014-async-timeouts.docx",
                "url": "https://test.my.salesforce.com/lightning/r/ContentDocument/069x/view",
                "snippet": "Outbound calls must set a timeout.",
            }
        ],
    )

    result = await search_salesforce.run_async(
        args={"query": "timeout"},
        tool_context=tool_context,
    )

    assert result["status"] == "success"
    assert result["data"][0]["name"] == "adr-014-async-timeouts.docx"
    assert result["data"][0]["snippet"] == "Outbound calls must set a timeout."
    mock_search.assert_called_once_with(
        "managed-2lo-token", "https://test.my.salesforce.com", "timeout"
    )


@pytest.mark.asyncio
async def test_search_salesforce_accepts_oauth2_credential(mocker) -> None:
    """Supports OAuth2Auth access_token credentials as well as HTTP Bearer credentials."""
    tool_context = MagicMock()
    tool_context.user_id = "engineer@example.com"

    oauth_cred = AuthCredential(
        auth_type=AuthCredentialTypes.OAUTH2,
        oauth2=OAuth2Auth(access_token="oauth-access-token"),
    )
    mocker.patch.object(
        search_salesforce._credentials_manager,
        "get_auth_credential",
        new=AsyncMock(return_value=oauth_cred),
    )
    mock_search = mocker.patch(
        "app.salesforce_client.SalesforceClient.search_files",
        return_value=[],
    )

    result = await search_salesforce.run_async(
        args={"query": "policy"},
        tool_context=tool_context,
    )

    assert result["status"] == "success"
    mock_search.assert_called_once_with(
        "oauth-access-token", "https://test.my.salesforce.com", "policy"
    )


@pytest.mark.asyncio
async def test_empty_credential_token_returns_structured_auth_error(mocker) -> None:
    """An AuthCredential with no bearer token returns a structured error dict."""
    tool_context = MagicMock()
    tool_context.user_id = "engineer@example.com"

    empty_cred = AuthCredential(
        auth_type=AuthCredentialTypes.HTTP,
        http=HttpAuth(scheme="Bearer", credentials=HttpCredentials(token=None)),
    )
    mocker.patch.object(
        search_salesforce._credentials_manager,
        "get_auth_credential",
        new=AsyncMock(return_value=empty_cred),
    )

    result = await search_salesforce.run_async(
        args={"query": "q"},
        tool_context=tool_context,
    )

    assert result["status"] == "error"
    assert "auth failed" in result["error_message"].lower()


@pytest.mark.asyncio
async def test_http_error_returns_structured_error_dict(mocker) -> None:
    """Upstream Salesforce HTTP errors surface cleanly to the model."""
    tool_context = MagicMock()
    tool_context.user_id = "engineer@example.com"

    mocker.patch.object(
        search_salesforce._credentials_manager,
        "get_auth_credential",
        new=AsyncMock(return_value=_bearer_credential()),
    )
    mocker.patch(
        "app.salesforce_client.SalesforceClient.search_files",
        side_effect=_http_error(500),
    )

    result = await search_salesforce.run_async(
        args={"query": "q"},
        tool_context=tool_context,
    )

    assert result["status"] == "error"
    assert "search failed" in result["error_message"].lower()


# --- Client request layer ------------------------------------------------------


def test_client_normalizes_domain_without_secrets() -> None:
    """SalesforceClient initializes with domain alone (no client_id/client_secret needed)."""
    client = SalesforceClient("https://myorg.my.salesforce.com/")
    assert client.domain == "myorg.my.salesforce.com"
    assert client.instance_url == "https://myorg.my.salesforce.com"
    assert client.client_id is None
    assert client.client_secret is None


def test_search_files_maps_records_and_enriches_top_hits(mocker) -> None:
    """search_files issues a SOSL GET and enriches hits with a downloaded excerpt."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "searchRecords": [
            {
                "Id": "068A",
                "Title": "adr-014-async-timeouts",
                "FileExtension": "docx",
                "ContentDocumentId": "069A",
            }
        ]
    }
    get = mocker.patch("app.salesforce_client.requests.get", return_value=resp)
    mocker.patch(
        "app.salesforce_client.SalesforceClient.download_version_text",
        return_value=("filler " * 40) + " NEEDLE timeout rule " + ("tail " * 40),
    )

    client = SalesforceClient("org.my.salesforce.com")
    docs = client.search_files("tok", "https://inst.my.salesforce.com", "NEEDLE")

    assert len(docs) == 1
    assert docs[0]["name"] == "adr-014-async-timeouts.docx"
    assert docs[0]["url"] == (
        "https://inst.my.salesforce.com/lightning/r/ContentDocument/069A/view"
    )
    assert "NEEDLE" in docs[0]["snippet"]
    url = get.call_args[0][0]
    kwargs = get.call_args[1]
    assert url == "https://inst.my.salesforce.com/services/data/v62.0/search"
    assert kwargs["headers"]["Authorization"] == "Bearer tok"
    assert kwargs["params"]["q"].startswith("FIND {NEEDLE} IN ALL FIELDS")
    assert "RETURNING ContentVersion(" in kwargs["params"]["q"]


def test_download_version_text_extracts(mocker) -> None:
    """download_version_text fetches VersionData bytes and extracts text."""
    resp = MagicMock()
    resp.status_code = 200
    resp.content = b"plain body text"
    get = mocker.patch("app.salesforce_client.requests.get", return_value=resp)

    client = SalesforceClient("org.my.salesforce.com")
    text = client.download_version_text(
        "tok", "https://inst.my.salesforce.com", "068A", "notes.txt"
    )

    assert text == "plain body text"
    url = get.call_args[0][0]
    assert url.endswith("/services/data/v62.0/sobjects/ContentVersion/068A/VersionData")


# --- Helpers -------------------------------------------------------------------


def test_build_sosl_targets_latest_content_versions() -> None:
    sosl = _build_sosl("async timeout")
    assert sosl.startswith(
        "FIND {async timeout} IN ALL FIELDS RETURNING ContentVersion("
    )
    assert "IsLatest = true" in sosl
    assert "ContentDocumentId" in sosl


def test_escape_sosl_escapes_reserved_chars() -> None:
    assert _escape_sosl("a+b (c)") == r"a\+b \(c\)"


def test_file_name_appends_extension() -> None:
    assert _file_name("adr-014", "docx") == "adr-014.docx"
    assert _file_name("notes.txt", "txt") == "notes.txt"
    assert _file_name("", "") == "document"


def test_extract_text_docx_roundtrip() -> None:
    doc = Document()
    doc.add_paragraph("mTLS between services is mandatory")
    buf = io.BytesIO()
    doc.save(buf)
    text = _extract_text("adr.docx", buf.getvalue())
    assert "mTLS between services is mandatory" in text


def test_build_excerpt_windows_around_match() -> None:
    text = ("a " * 2000) + "NEEDLE marker here " + ("b " * 2000)
    excerpt = _build_excerpt(text, "NEEDLE", max_chars=200)
    assert "NEEDLE" in excerpt
    assert excerpt.startswith("…") and excerpt.endswith("…")
    assert len(excerpt) <= 202
