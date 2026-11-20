
"""Coding agent with repository discovery, search, and execution tools."""

import os
import warnings
import subprocess

from google.adk.agents import Agent
from google.genai import types

DEFAULT_MODEL = "gemini-3.1-flash-lite"

warnings.filterwarnings(
    "ignore",
    message=r".*JSON_SCHEMA_FOR_FUNC_DECL.*",
    category=UserWarning
)


def _resolve(sandbox: str, path: str) -> str:
    """Resolve a sandbox-relative path safely."""
    sandbox = os.path.realpath(sandbox)
    full = os.path.realpath(os.path.join(sandbox, path))

    if full != sandbox and not full.startswith(sandbox + os.sep):
        raise ValueError(f"path escapes sandbox: {path!r}")

    return full


def _read(sandbox: str, path: str) -> str:
    try:
        with open(_resolve(sandbox, path), encoding="utf-8") as fh:
            return fh.read()
    except (FileNotFoundError, ValueError, OSError) as exc:
        return f"Error: {exc}"


def _write(sandbox: str, path: str, contents: str) -> str:
    try:
        full = _resolve(sandbox, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)

        with open(full, "w", encoding="utf-8") as fh:
            fh.write(contents)

        return f"Wrote {len(contents)} chars to {path}"

    except (ValueError, OSError) as exc:
        return f"Error: {exc}"


def _list_files(sandbox: str, path: str = ".") -> str:
    """List files and directories recursively within the sandbox."""
    try:
        root = _resolve(sandbox, path)
        results = []

        for current, dirs, files in os.walk(root):
            dirs[:] = [
                d for d in dirs
                if d not in {".git", ".venv", "__pycache__", "node_modules"}
            ]

            relative = os.path.relpath(current, sandbox)

            for filename in files:
                results.append(os.path.join(relative, filename))

        return "\n".join(results[:500]) or "No files found."

    except (ValueError, OSError) as exc:
        return f"Error: {exc}"


def _search_code(sandbox: str, query: str) -> str:
    """Search repository source files for a string or symbol."""
    try:
        result = subprocess.run(
            [
                "grep", "-Rn",
                "--exclude-dir=.git",
                "--exclude-dir=.venv",
                "--exclude-dir=__pycache__",
                "--exclude-dir=node_modules",
                "--include=*.py",
                "--include=*.sh",
                "--include=*.toml",
                "--include=*.yaml",
                "--include=*.yml",
                "--",
                query,
                "."
            ],
            cwd=sandbox,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 1:
            return "No matches found."

        if result.returncode != 0:
            return f"Search error: {result.stderr}"

        return result.stdout[:20000]

    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"Error: {exc}"


def _run_command(sandbox: str, command: str) -> str:
    """Execute a shell command in the sandbox and return output and exit code."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=sandbox,
            capture_output=True,
            text=True,
            timeout=120
        )

        return (
            f"Exit code: {result.returncode}\n"
            f"STDOUT:\n{result.stdout[-12000:]}\n"
            f"STDERR:\n{result.stderr[-12000:]}"
        )

    except subprocess.TimeoutExpired as exc:
        return f"Command timed out: {exc}"

    except OSError as exc:
        return f"Execution error: {exc}"



SYSTEM_INSTRUCTION = """
You are an autonomous software engineering agent working in a task sandbox.

Your goal is to identify the actual root cause, implement the smallest
correct fix, and verify the behavior before reporting completion.

Follow this workflow for every task.

PHASE 1: UNDERSTAND THE REPOSITORY
1. Read the complete task description.
2. Use list_files to inspect the repository structure.
3. Identify the entry point, relevant source files, and related modules.
4. Read relevant files before modifying anything.
5. Trace imports, callers, data flow, and transformations across modules.
6. Use search_code to find definitions and usages of relevant functions.

PHASE 2: IDENTIFY THE ROOT CAUSE
1. Determine where the incorrect behavior first occurs.
2. Do not assume the file named in the task contains the defect.
3. Trace input data from the CLI or public API to the final output.
4. Check parsing, conversion, normalization, calculation, and formatting.
5. Identify the exact reason expected and actual behavior differ.
6. Do not modify code until you have a specific root-cause hypothesis.

PHASE 3: REPRODUCE THE PROBLEM
1. Inspect the available CLI interface and task requirements.
2. Check whether a reproduction script or test suite already exists.
3. If one exists, execute it using run_command.
4. If none exists, create a small reproduction script or use a direct
   Python/CLI command to reproduce the reported behavior.
5. Execute the reproducer and inspect stdout, stderr, and exit code.
6. Record the expected and actual behavior.

Never assume that a script works merely because you wrote it.
Never claim that a test passed without executing it.

PHASE 4: IMPLEMENT THE FIX
1. Make the smallest change that fixes the root cause.
2. Preserve existing APIs, output formats, and return types.
3. Avoid unrelated refactoring or unnecessary dependencies.
4. Consider how the change affects other callers.
5. Re-read modified files after writing them.

PHASE 5: SYSTEMATICALLY VERIFY
Test the normal case and relevant boundary cases.

Consider these categories whenever applicable:

- Empty input and single-element input.
- Zero, negative, and positive values.
- Minimum and maximum boundaries.
- Ascending and descending ranges.
- Inclusive and exclusive endpoints.
- Duplicate values and repeated operations.
- Decimal precision and rounding behavior.
- Leading/trailing whitespace and trailing zeros.
- Missing, null, malformed, or unexpected input.
- Time zones, UTC offsets, and date boundaries.
- Output formatting, ordering, and newline behavior.
- CLI exit codes, stdout, and stderr.

Choose cases relevant to the actual task; do not blindly test
irrelevant categories.

For every fix:
1. Execute the original reproduction case.
2. Execute at least one relevant boundary or edge case.
3. Execute available project tests if they exist.
4. Exercise the public CLI or API when applicable.
5. Inspect the actual output and exit code.
6. Investigate and correct any remaining failures.

PHASE 6: FINAL REVIEW
1. Review the final modified code.
2. Confirm that the original failure is resolved.
3. Confirm that no unrelated files were changed.
4. Report the root cause and files modified.
5. List the exact commands executed and their results.
6. Clearly distinguish verified results from unverified assumptions.

Never report success based only on code inspection.
Never invent test results.
If verification cannot be completed, explicitly explain why.
"""


def build_agent(sandbox: str, model: str) -> Agent:

    def read_file(path: str) -> dict:
        """Read a text file relative to the project root."""
        return {"result": _read(sandbox, path)}

    def write_file(path: str, contents: str) -> dict:
        """Create or overwrite a text file relative to the project root."""
        return {"result": _write(sandbox, path, contents)}

    def list_files(path: str = ".") -> dict:
        """List repository files recursively, relative to the project root."""
        return {"result": _list_files(sandbox, path)}

    def search_code(query: str) -> dict:
        """Search Python and configuration files for a function, symbol, or text."""
        return {"result": _search_code(sandbox, query)}

    def run_command(command: str) -> dict:
        """Run a shell command in the project sandbox and return output and exit code."""
        return {"result": _run_command(sandbox, command)}

    return Agent(
        name="coding_agent",
        model=model,
        instruction=SYSTEM_INSTRUCTION,
        tools=[
            read_file,
            write_file,
            list_files,
            search_code,
            run_command
        ],
        generate_content_config=types.GenerateContentConfig(
            temperature=0.2,
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.LOW
            )
        )
    )


if __name__ == "__main__":
    import asyncio
    import sys
    from google.adk.runners import InMemoryRunner

    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    os.environ.setdefault(
        "GOOGLE_CLOUD_PROJECT",
        "qwiklabs-gcp-04-8701eab96d36"
    )
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")

    sandbox = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "out"
    )

    os.makedirs(sandbox, exist_ok=True)

    prompt = " ".join(sys.argv[1:]) or "Write a hello world Python script"

    async def _run_agent():
        runner = InMemoryRunner(
            agent=build_agent(sandbox, DEFAULT_MODEL)
        )

        session = await runner.session_service.create_session(
            app_name=runner.app_name,
            user_id="me"
        )

        message = types.Content(
            role="user",
            parts=[types.Part(text=prompt)]
        )

        async for event in runner.run_async(
            user_id="me",
            session_id=session.id,
            new_message=message
        ):
            for part in (event.content and event.content.parts) or []:
                if part.text:
                    print(part.text, flush=True)

    asyncio.run(_run_agent())
