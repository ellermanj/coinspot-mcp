"""CoinSpot Australia MCP server."""

from coinspot_mcp.server import mcp, run

__all__ = ["mcp", "main", "run"]


def main() -> None:
    """CLI entry point for the CoinSpot MCP server."""
    run()
