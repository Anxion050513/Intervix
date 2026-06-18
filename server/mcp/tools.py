"""MCP tool definitions for code execution."""
from server.mcp.sandbox import sandbox, ExecutionResult


async def execute_code(
    code: str,
    language: str = "python",
    timeout: int = 30,
) -> dict:
    """Execute code in a secure Docker sandbox.

    Args:
        code: Source code to execute.
        language: Programming language (default: python).
        timeout: Max execution time in seconds (default: 30).

    Returns:
        dict with keys: success, stdout, stderr, exit_code, execution_time_ms
    """
    result: ExecutionResult = await sandbox.execute(code, language, timeout)
    return {
        "success": result.success,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "execution_time_ms": result.execution_time_ms,
    }


async def run_tests(code: str, test_code: str, timeout: int = 30) -> dict:
    """Run pytest against user code in the sandbox.

    Args:
        code: User's implementation code.
        test_code: Pytest test code.
        timeout: Max execution time in seconds.

    Returns:
        dict with test results.
    """
    combined = f"""
{code}

# --- Test Code Below ---
{test_code}

if __name__ == "__main__":
    import pytest
    import sys
    sys.exit(pytest.main(["-v", "--tb=short", __file__]))
"""
    result = await sandbox.execute(combined, "python", timeout)

    return {
        "success": result.exit_code == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "execution_time_ms": result.execution_time_ms,
    }


async def get_code_template(language: str = "python", topic: str = "") -> str:
    """Return a starter code template for a given topic.

    Args:
        language: Programming language.
        topic: Topic name (e.g., 'binary_search', 'linked_list').

    Returns:
        Starter code template string.
    """
    templates = {
        "binary_search": """def binary_search(arr: list[int], target: int) -> int:
    \"\"\"Return the index of target in arr, or -1 if not found.\"\"\"
    # Your code here
    pass

# Example usage
if __name__ == "__main__":
    test_arr = [1, 3, 5, 7, 9, 11]
    print(binary_search(test_arr, 7))  # Expected: 3
""",
        "two_sum": """def two_sum(nums: list[int], target: int) -> list[int]:
    \"\"\"Return indices of two numbers that add up to target.\"\"\"
    # Your code here
    pass

if __name__ == "__main__":
    print(two_sum([2, 7, 11, 15], 9))  # Expected: [0, 1]
""",
        "string_reverse": """def reverse_string(s: str) -> str:
    \"\"\"Reverse a string without using [::-1].\"\"\"
    # Your code here
    pass

if __name__ == "__main__":
    print(reverse_string("hello"))  # Expected: "olleh"
""",
    }

    return templates.get(topic, f"# Write your {language} code here\n# Topic: {topic or 'general'}\n")
