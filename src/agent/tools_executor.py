"""
Tool Executor
=============

Handles the execution of tools called by the LLM.

The executor:
1. Parses tool calls from LLM responses
2. Executes tools with validated parameters
3. Formats results for the LLM
4. Handles errors gracefully

Tool Execution Loop:
    1. LLM generates response with tool calls
    2. Executor runs each tool
    3. Results are formatted and sent back to LLM
    4. LLM continues with results (may call more tools)
    5. Repeat until LLM generates final response

This loop allows the agent to gather information from multiple sources
and take multiple actions before responding to the user.
"""

import json
from dataclasses import dataclass
from typing import Any

from src.tools import tool_registry, ToolResult
from src.utils.logger import Logger

logger = Logger("ToolExecutor")


@dataclass
class ToolCall:
    """
    A parsed tool call from the LLM.

    Attributes:
        id: The tool call ID (for matching results)
        name: The tool name
        arguments: Parsed arguments dict
    """
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolCallResult:
    """
    Result of executing a tool call.

    Attributes:
        tool_call_id: The original tool call ID
        name: The tool name
        result: The tool result
    """
    tool_call_id: str
    name: str
    result: ToolResult

    def to_openai_message(self) -> dict:
        """
        Format as a tool result message for OpenAI.

        Returns:
            Message dict in OpenAI's expected format
        """
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "content": self.result.to_message()
        }


class ToolExecutor:
    """
    Executes tools called by the LLM.

    The executor handles:
    - Parsing tool calls from OpenAI responses
    - Validating tool names and parameters
    - Running tools and capturing results
    - Formatting results for the next LLM call

    Example:
        executor = ToolExecutor()

        # Parse and execute tool calls from response
        tool_calls = executor.parse_tool_calls(response)
        results = await executor.execute_all(tool_calls)

        # Add results to messages
        for result in results:
            messages.append(result.to_openai_message())
    """

    def __init__(self):
        """Initialize the tool executor."""
        self.registry = tool_registry

    def parse_tool_calls(self, response: Any) -> list[ToolCall]:
        """
        Parse tool calls from an OpenAI response.

        Args:
            response: The OpenAI chat completion response

        Returns:
            List of parsed ToolCall objects
        """
        tool_calls = []

        # Get tool calls from the response
        message = response.choices[0].message
        if not message.tool_calls:
            return []

        for tc in message.tool_calls:
            try:
                # Parse the JSON arguments
                arguments = json.loads(tc.function.arguments)

                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=arguments
                ))

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse tool arguments: {e}")
                # Add a failed tool call with empty arguments
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments={}
                ))

        logger.debug(f"Parsed {len(tool_calls)} tool calls")
        return tool_calls

    async def execute_one(self, tool_call: ToolCall) -> ToolCallResult:
        """
        Execute a single tool call.

        Args:
            tool_call: The tool call to execute

        Returns:
            ToolCallResult with the execution result
        """
        logger.info(f"Executing tool: {tool_call.name}")

        # Execute through the registry
        result = await self.registry.execute(tool_call.name, tool_call.arguments)

        if result.success:
            logger.debug(f"Tool {tool_call.name} succeeded")
        else:
            logger.warning(f"Tool {tool_call.name} failed: {result.error}")

        return ToolCallResult(
            tool_call_id=tool_call.id,
            name=tool_call.name,
            result=result
        )

    async def execute_all(self, tool_calls: list[ToolCall]) -> list[ToolCallResult]:
        """
        Execute multiple tool calls.

        Tools are executed sequentially to maintain consistency.
        For parallel execution, use execute_parallel().

        Args:
            tool_calls: List of tool calls to execute

        Returns:
            List of ToolCallResults in the same order
        """
        results = []

        for tool_call in tool_calls:
            result = await self.execute_one(tool_call)
            results.append(result)

        return results

    async def execute_parallel(self, tool_calls: list[ToolCall]) -> list[ToolCallResult]:
        """
        Execute multiple tool calls in parallel.

        Use this when tools are independent and can run concurrently.
        Results are returned in the same order as inputs.

        Args:
            tool_calls: List of tool calls to execute

        Returns:
            List of ToolCallResults in input order
        """
        import asyncio

        tasks = [self.execute_one(tc) for tc in tool_calls]
        results = await asyncio.gather(*tasks)

        return list(results)

    def format_results_for_messages(
        self,
        results: list[ToolCallResult]
    ) -> list[dict]:
        """
        Format tool results as messages for the next LLM call.

        Args:
            results: List of tool call results

        Returns:
            List of message dicts to add to the conversation
        """
        return [result.to_openai_message() for result in results]

    def get_available_tools(self) -> list[str]:
        """Get list of available tool names."""
        return self.registry.list_names()

    def has_tool(self, name: str) -> bool:
        """Check if a tool is available."""
        return self.registry.get(name) is not None
