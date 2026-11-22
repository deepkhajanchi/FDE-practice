"""Test bootstrap for github-agent offline unit tests."""

import os
import sys
from pathlib import Path

AGENT_SRC = Path(__file__).resolve().parent.parent / "agent"
if str(AGENT_SRC) not in sys.path:
    sys.path.insert(0, str(AGENT_SRC))

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
os.environ.setdefault("MODEL", "gemini-3.5-flash")
os.environ.setdefault(
    "GITHUB_AUTH_PROVIDER_URI",
    "projects/test-project/locations/us-central1/authProviders/github-mcp-auth-provider",
)
