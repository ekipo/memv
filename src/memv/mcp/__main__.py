"""CLI entry point for the memv MCP server."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="memv-mcp",
        description="memv MCP server — expose memory operations to AI agents",
    )
    parser.add_argument("--db-url", required=True, help="Database URL (SQLite file path or postgresql://...)")
    parser.add_argument("--user-id", default="default", help="Default user ID for all operations (default: 'default')")
    parser.add_argument(
        "--embedding-provider",
        default="openai",
        choices=["openai", "voyage", "cohere", "local"],
        help="Embedding provider (default: openai)",
    )
    parser.add_argument("--embedding-model", default=None, help="Override default embedding model for the chosen provider")
    parser.add_argument("--embedding-dimensions", type=int, default=None, help="Override embedding dimensions")
    parser.add_argument(
        "--llm-model",
        default=None,
        help="LLM model for knowledge extraction (PydanticAI model string, e.g. 'openai:gpt-4o-mini'). "
        "Without this, add_conversation stores messages but cannot extract knowledge.",
    )
    parser.add_argument("--transport", default="stdio", choices=["stdio", "streamable-http"], help="MCP transport (default: stdio)")

    args = parser.parse_args()

    from memv.mcp.server import create_server

    server = create_server(
        db_url=args.db_url,
        default_user_id=args.user_id,
        embedding_provider=args.embedding_provider,
        embedding_model=args.embedding_model,
        embedding_dimensions=args.embedding_dimensions,
        llm_model=args.llm_model,
    )
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
