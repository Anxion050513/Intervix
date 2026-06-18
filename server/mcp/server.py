"""MCP server for the interview code sandbox.

Uses fastmcp to expose code execution tools via the Model Context Protocol.
Run as: python -m server.mcp.server
"""
import asyncio
from fastmcp import FastMCP

from server.mcp.tools import execute_code, run_tests, get_code_template

# Create MCP server
mcp = FastMCP("interview-code-sandbox")


@mcp.tool()
async def tool_execute_code(
    code: str,
    language: str = "python",
    timeout: int = 30,
) -> dict:
    """Execute code in a secure Docker sandbox.

    Use this to run candidate's code and see the output.
    Returns stdout, stderr, exit_code, and execution time.
    """
    return await execute_code(code, language, timeout)


@mcp.tool()
async def tool_run_tests(
    code: str,
    test_code: str,
    timeout: int = 30,
) -> dict:
    """Run pytest test cases against candidate's code.

    Provide the candidate's implementation and test cases.
    Returns test results summary.
    """
    return await run_tests(code, test_code, timeout)


@mcp.tool()
async def tool_get_code_template(
    language: str = "python",
    topic: str = "",
) -> str:
    """Get a starter code template for a coding interview question.

    Supports topics: binary_search, two_sum, string_reverse.
    """
    return await get_code_template(language, topic)


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
