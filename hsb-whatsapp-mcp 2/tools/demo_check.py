"""Run the actual MCP client/server protocol with synthetic records only."""
import asyncio
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    root = Path(__file__).resolve().parents[1]
    params = StdioServerParameters(command=sys.executable,
        args=["-m", "hsb_mcp", "demo-stdio"], cwd=str(root))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert {t.name for t in tools.tools} == {"search", "fetch"}
            found = await session.call_tool("search", {"query": "pump quotation"})
            assert not found.isError
            rows = found.structuredContent["results"]
            assert rows
            fetched = await session.call_tool("fetch", {"id": rows[0]["id"]})
            assert not fetched.isError
            assert "DEMO DATA ONLY" in fetched.structuredContent["text"]
            print("PASS: MCP initialize, tool discovery, search and fetch.")
            print("Synthetic result:", fetched.structuredContent["text"])


if __name__ == "__main__":
    asyncio.run(main())
