# Plan: MCP Spec 2025-11-25 Compliance

Bring k8s-mcp-server up to date with MCP specification revision 2025-11-25.

## Context

- **Repo:** k8s-mcp-server
- **Language:** Python 3.13
- **Framework:** FastMCP (from `mcp` package)
- **Default branch:** master
- **Lint:** `uvx ruff check src/ tests/`
- **Tests:** `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/unit/`
- **Key files:**
  - `src/k8s_mcp_server/server.py` — tool definitions, FastMCP instance
  - `src/k8s_mcp_server/__main__.py` — transport selection
  - `src/k8s_mcp_server/config.py` — env var configuration
  - `src/k8s_mcp_server/errors.py` — custom error classes
  - `src/k8s_mcp_server/prompts.py` — MCP prompts

## Validation Commands
- `uvx ruff check src/ tests/`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/unit/`

### Task 1: Add Implementation description field (Issue #13)
This is a trivial change. Add `description` parameter to the `FastMCP()` constructor in `server.py`.

- [x] Add `description` parameter to `FastMCP(...)` in `src/k8s_mcp_server/server.py` with a concise description of the server's purpose
- [x] Verify FastMCP constructor accepts `description` parameter (check the mcp package source if needed)
- [x] All tests pass

### Task 2: Add ToolAnnotations to all tools (Issue #11)
Add `annotations` parameter with `ToolAnnotations` to each `@mcp.tool()` decorator in `server.py`. There are 8 tools total — 4 describe/help tools (read-only) and 4 execute tools (potentially destructive).

- [x] Import `ToolAnnotations` from `mcp.types` in `server.py`
- [x] Add annotations to all 4 `describe_*` tools: `readOnlyHint=True, title="<Tool> Help"`
- [x] Add annotations to all 4 `execute_*` tools: `destructiveHint=True, openWorldHint=True, title="Execute <Tool>"`
- [x] Check that `mcp` package version in `pyproject.toml` supports `ToolAnnotations` (needs `mcp>=1.22.0`). Update minimum version if needed.
- [x] All tests pass

### Task 3: Return input validation errors as tool execution errors (Issue #12)
MCP spec says input validation errors should be returned as tool results with `isError: true`, NOT as JSON-RPC protocol errors. Audit current behavior and fix if needed.

- [x] Audit how `CommandValidationError` is currently handled in `_execute_tool_command()` — check if the returned result sets `isError=True` at the MCP protocol level
- [x] Check how FastMCP handles exceptions raised by tool functions — does it convert them to `isError: true` results or JSON-RPC errors?
- [x] If FastMCP does NOT auto-set `isError=True` for our error results, update the tool functions to use the correct FastMCP mechanism (e.g., returning error content with the right type)
- [x] Handle Pydantic ValidationError for invalid input types — catch and return as tool error, not protocol error
- [x] Add/update unit tests verifying that validation errors produce `isError: true` responses
- [x] All tests pass

### Task 4: Add Streamable HTTP transport support (Issue #10)
MCP spec 2025-11-25 replaces SSE with Streamable HTTP. Add it as the recommended HTTP transport and deprecate SSE.

- [ ] In `__main__.py`, add `streamable-http` as a valid transport option
- [ ] When `sse` transport is selected, log a deprecation warning suggesting migration to `streamable-http`
- [ ] Update `config.py` — add documentation for the new transport option
- [ ] Add Docker host detection logic: bind to `0.0.0.0` when running in Docker, `127.0.0.1` otherwise (check for `/.dockerenv` file or `DOCKER_CONTAINER` env var). Look at aws-mcp-server for reference implementation: `/tmp/aws-mcp-server/src/aws_mcp_server/__main__.py`
- [ ] Update README.md transport documentation section
- [ ] Verify FastMCP supports `streamable-http` transport — check mcp package
- [ ] All tests pass
