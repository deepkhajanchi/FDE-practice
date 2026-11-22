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

"""Salesforce Files search tool backed by Google Cloud Agent Identity Auth Manager.

Instead of holding Connected App consumer keys/secrets in environment variables
and performing a direct 2LO exchange inside the container, `AuthenticatedFunctionTool`
delegates token acquisition to Google Cloud Agent Identity (`GcpAuthProvider` +
`GcpAuthProviderScheme`) and injects a short-lived `AuthCredential` into
`search_salesforce` on every invocation.
"""

from __future__ import annotations

from google.adk.auth.auth_credential import AuthCredential
from google.adk.auth.auth_tool import AuthConfig
from google.adk.integrations.agent_identity import GcpAuthProviderScheme
from google.adk.tools.authenticated_function_tool import AuthenticatedFunctionTool

from app.salesforce_client import SalesforceClient


def _extract_access_token(credential: AuthCredential | None) -> str:
    """Extracts the bearer access token from an ADK AuthCredential."""
    if credential is None:
        raise ValueError("No AuthCredential returned by GcpAuthProvider.")
    if (
        credential.http
        and credential.http.credentials
        and credential.http.credentials.token
    ):
        return credential.http.credentials.token
    if credential.oauth2 and credential.oauth2.access_token:
        return credential.oauth2.access_token
    raise ValueError("AuthCredential did not contain a bearer access token.")


def build_search_salesforce(
    client: SalesforceClient,
    auth_provider_uri: str,
) -> AuthenticatedFunctionTool:
    """Builds an AuthenticatedFunctionTool bound to an Agent Identity AuthProvider.

    Args:
        client: A `SalesforceClient` configured with the org's My Domain host.
        auth_provider_uri: Full GCP resource name of the 2LO AuthProvider
            (`projects/{project}/locations/{location}/authProviders/{name}`).

    Returns:
        An `AuthenticatedFunctionTool` wrapping `search_salesforce`.
    """
    auth_config = AuthConfig(
        auth_scheme=GcpAuthProviderScheme(name=auth_provider_uri),
    )

    def search_salesforce(query: str, credential: AuthCredential) -> dict:
        """Searches the company's Salesforce document library (Files).

        Runs a SOSL full-text search across every file the application can read;
        the caller does not need to know a file name or folder.

        Args:
            query: The search term or issue description.

        Returns:
            A dict with a 'status' key; on success, 'data' holds matching
            documents (each a {'name', 'url', 'snippet'} dict). On failure,
            'error_message' explains why.
        """
        try:
            access_token = _extract_access_token(credential)
        except Exception as e:
            return {
                "status": "error",
                "error_message": f"Salesforce auth failed: {e}",
            }

        try:
            documents = client.search_files(
                access_token, client.instance_url, query
            )
        except Exception as e:
            return {
                "status": "error",
                "error_message": f"Salesforce search failed: {e}",
            }

        return {
            "status": "success",
            "query": query,
            "data": documents,
        }

    return AuthenticatedFunctionTool(
        func=search_salesforce,
        auth_config=auth_config,
    )
