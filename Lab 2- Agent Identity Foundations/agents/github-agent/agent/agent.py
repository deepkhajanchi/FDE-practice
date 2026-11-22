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

"""GitHub sub-agent secured with Google Cloud Agent Identity Auth Manager.

Talks to the hosted **GitHub MCP server** through ADK `McpToolset` using
`GcpAuthProvider` and `GcpAuthProviderScheme` instead of a static plaintext PAT
in `.env`. Deployed to Vertex AI Agent Runtime with SPIFFE Agent Identity
(`identityType=AGENT_IDENTITY`) and reached over A2A.
"""

import os

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.auth.credential_manager import CredentialManager
from google.adk.integrations.agent_identity import (
    GcpAuthProvider,
    GcpAuthProviderScheme,
)
from google.adk.models import Gemini
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams
from google.genai import types

load_dotenv()

MODEL = os.environ["MODEL"]
GITHUB_AUTH_PROVIDER_URI = os.environ["GITHUB_AUTH_PROVIDER_URI"]
GITHUB_MCP_URL = os.getenv("GITHUB_MCP_URL", "https://api.githubcopilot.com/mcp/")
GITHUB_TOOL_FILTER = ["search_repositories", "search_issues", "list_issues"]

# Optional 3-Legged OAuth parameters (unused for API-key auth providers,
# populated when upgrading the AuthProvider to per-user 3LO consent).
_raw_scopes = os.getenv("GITHUB_OAUTH_SCOPES", "").strip()
GITHUB_OAUTH_SCOPES = [s.strip() for s in _raw_scopes.split(",") if s.strip()] or None
GITHUB_CONTINUE_URI = os.getenv("GITHUB_CONTINUE_URI", "").strip() or None

# Register Google Cloud Agent Identity Auth Manager with ADK's CredentialManager.
CredentialManager.register_auth_provider(GcpAuthProvider())

github_auth_scheme = GcpAuthProviderScheme(
    name=GITHUB_AUTH_PROVIDER_URI,
    scopes=GITHUB_OAUTH_SCOPES,
    continue_uri=GITHUB_CONTINUE_URI,
)

github_mcp_toolset = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url=GITHUB_MCP_URL,
        headers={
            "Accept": "application/vnd.github.v3+json",
        },
    ),
    auth_scheme=github_auth_scheme,
    tool_filter=GITHUB_TOOL_FILTER,
)

root_agent = Agent(
    name="github_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    description=(
        "Specialized assistant for GitHub: searches repositories, issues, and "
        "pull requests via the GitHub MCP server."
    ),
    instruction=(
        "You are a specialized assistant for interacting with GitHub. "
        "Use the provided tools to search for repositories, find issues, and "
        "retrieve pull-request information, then answer with what you find. "
        "Be concise and cite the repository names / issue numbers you used."
    ),
    tools=[github_mcp_toolset],
)

app = App(
    root_agent=root_agent,
    name="app",
)
