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

"""Offline config tests for the Salesforce sub-agent with Agent Identity."""

import os

from google.adk.auth.credential_manager import CredentialManager
from google.adk.integrations.agent_identity import (
    GcpAuthProvider,
    GcpAuthProviderScheme,
)
from google.adk.tools.authenticated_function_tool import AuthenticatedFunctionTool
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from app.agent import app, generate_memories_callback, root_agent


def test_agent_identity() -> None:
    """The agent and app are named as the runner expects."""
    assert root_agent.name == "salesforce_agent"
    assert app.name == "app"


def test_tools_and_auth_provider_are_wired() -> None:
    """The agent exposes AuthenticatedFunctionTool + PreloadMemoryTool with zero client secrets."""
    assert len(root_agent.tools) == 2
    sf_tool = root_agent.tools[0]
    assert isinstance(sf_tool, AuthenticatedFunctionTool)
    assert sf_tool.name == "search_salesforce"
    assert isinstance(root_agent.tools[1], PreloadMemoryTool)

    scheme = GcpAuthProviderScheme(
        name="projects/test-project/locations/us-central1/authProviders/salesforce-auth-provider"
    )
    provider = CredentialManager._auth_provider_registry.get_provider(scheme)
    assert isinstance(provider, GcpAuthProvider)

    assert "SALESFORCE_CLIENT_ID" not in os.environ
    assert "SALESFORCE_CLIENT_SECRET" not in os.environ


def test_llm_declaration_hides_credential_argument() -> None:
    """The LLM function declaration exposes `query` only, hiding `credential`."""
    sf_tool = root_agent.tools[0]
    decl = sf_tool._get_declaration()
    props = (
        decl.parameters_json_schema["properties"]
        if decl.parameters_json_schema
        else decl.parameters.properties
    )
    assert "query" in props
    assert "credential" not in props


def test_memory_generation_callback_wired() -> None:
    """The after-agent callback that persists memories is attached."""
    assert root_agent.after_agent_callback is generate_memories_callback
