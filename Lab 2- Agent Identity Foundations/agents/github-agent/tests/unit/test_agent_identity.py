"""Offline unit tests verifying Agent Identity Auth Manager wiring for github-agent."""

import os

from google.adk.auth.credential_manager import CredentialManager
from google.adk.integrations.agent_identity import (
    GcpAuthProvider,
    GcpAuthProviderScheme,
)
from google.adk.tools.mcp_tool import McpToolset

import agent as github_agent_module


def test_agent_and_app_names() -> None:
    """Agent and ADK App names match expected contract."""
    assert github_agent_module.root_agent.name == "github_agent"
    assert github_agent_module.app.name == "app"


def test_gcp_auth_provider_registered_in_credential_manager() -> None:
    """CredentialManager resolves GcpAuthProviderScheme to GcpAuthProvider."""
    scheme = GcpAuthProviderScheme(
        name="projects/test-project/locations/us-central1/authProviders/github-mcp-auth-provider"
    )
    provider = CredentialManager._auth_provider_registry.get_provider(scheme)
    assert isinstance(provider, GcpAuthProvider)


def test_mcp_toolset_uses_agent_identity_auth_scheme() -> None:
    """McpToolset delegates authentication to GcpAuthProviderScheme with zero static bearer secrets."""
    toolset = github_agent_module.github_mcp_toolset
    assert isinstance(toolset, McpToolset)
    assert isinstance(toolset.auth_scheme, GcpAuthProviderScheme)
    assert (
        toolset.auth_scheme.name
        == "projects/test-project/locations/us-central1/authProviders/github-mcp-auth-provider"
    )

    headers = toolset.connection_params.headers or {}
    assert "Authorization" not in headers
    assert headers.get("Accept") == "application/vnd.github.v3+json"
    assert "GITHUB_PERSONAL_ACCESS_TOKEN" not in os.environ


def test_readonly_tool_filter_preserved() -> None:
    """Least-privilege read-only MCP tool filter remains enforced."""
    assert github_agent_module.GITHUB_TOOL_FILTER == [
        "search_repositories",
        "search_issues",
        "list_issues",
    ]
