"""Start the MCP server on stdio: python -m src.mcp_server"""

from src.mcp_server.server import mcp

if __name__ == "__main__":
    mcp.run()
