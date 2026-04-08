"""Dev entry point for `mcp dev` / MCP Inspector.

Usage:
    uv run mcp dev src/memv/mcp/dev.py

Reads config from environment variables:
    MEMV_DB_URL          — database path (default: /tmp/memv-dev.db)
    MEMV_USER_ID         — default user ID (default: dev)
    MEMV_EMBEDDING       — embedding provider (default: openai)
    MEMV_LLM_MODEL       — LLM model string (optional)
"""

import os

from memv.mcp.server import create_server

mcp = create_server(
    db_url=os.environ.get("MEMV_DB_URL", "/tmp/memv-dev.db"),
    default_user_id=os.environ.get("MEMV_USER_ID", "dev"),
    embedding_provider=os.environ.get("MEMV_EMBEDDING", "openai"),
    llm_model=os.environ.get("MEMV_LLM_MODEL"),
)
