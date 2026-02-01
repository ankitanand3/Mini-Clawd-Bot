"""
MCP Tools System
================

This module implements tools following the Model Context Protocol (MCP) pattern.
Tools are functions that the AI agent can call to perform actions.

MCP (Model Context Protocol) is a standard for exposing capabilities to AI models:
- Each tool has a name, description, and parameter schema
- The AI decides which tools to use based on the user's request
- Tools are executed and results are returned to the AI

Tool Categories:
1. Slack Tools: Channel operations, messaging, scheduling
2. GitHub Tools: Issue creation, code search
3. Notion Tools: Page creation, content management
4. Scheduler Tools: Reminders, recurring tasks

How Tools Work:
1. Agent receives user request
2. Agent decides which tool(s) to use
3. Tool is executed with provided parameters
4. Result is returned to agent
5. Agent formulates response (may call more tools)

This module provides:
- MCPTool dataclass for defining tools
- ToolResult for standardized responses
- ToolRegistry for managing available tools
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
import json

from src.utils.logger import Logger

logger = Logger("Tools")


@dataclass
class ToolResult:
    """
    Standardized result from tool execution.

    Attributes:
        success: Whether the tool executed successfully
        data: The result data (varies by tool)
        error: Error message if success is False
    """
    success: bool
    data: Any = None
    error: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error
        }

    def to_message(self) -> str:
        """Format as a message for the LLM."""
        if self.success:
            return json.dumps(self.data, default=str)
        else:
            return f"Error: {self.error}"


@dataclass
class MCPTool:
    """
    Definition of a tool following MCP pattern.

    Attributes:
        name: Unique identifier for the tool
        description: What the tool does (shown to the AI)
        parameters: JSON Schema for the parameters
        execute: Async function that runs the tool

    Example:
        async def send_message(params: dict) -> ToolResult:
            channel = params["channel"]
            text = params["text"]
            # ... send message ...
            return ToolResult(success=True, data={"message_id": "123"})

        tool = MCPTool(
            name="send_message",
            description="Send a message to a Slack channel",
            parameters={
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "Channel ID or name"},
                    "text": {"type": "string", "description": "Message text"}
                },
                "required": ["channel", "text"]
            },
            execute=send_message
        )
    """
    name: str
    description: str
    parameters: dict
    execute: Callable[[dict], Awaitable[ToolResult]]

    def to_openai_function(self) -> dict:
        """
        Convert to OpenAI function calling format.

        Returns:
            Dict in the format expected by OpenAI's API
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }


class ToolRegistry:
    """
    Central registry for all available tools.

    The registry pattern allows tools to be registered from different modules
    and provides a single place to look up tools by name.

    Example:
        registry = ToolRegistry()

        # Register a tool
        registry.register(my_tool)

        # Get tool by name
        tool = registry.get("my_tool")

        # Get all tools for OpenAI
        functions = registry.get_openai_functions()
    """

    def __init__(self):
        """Initialize an empty registry."""
        self._tools: dict[str, MCPTool] = {}

    def register(self, tool: MCPTool) -> None:
        """
        Register a tool.

        Args:
            tool: The tool to register

        Raises:
            ValueError: If a tool with this name already exists
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")

        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def get(self, name: str) -> MCPTool | None:
        """
        Get a tool by name.

        Args:
            name: The tool name

        Returns:
            The tool, or None if not found
        """
        return self._tools.get(name)

    def get_all(self) -> list[MCPTool]:
        """Get all registered tools."""
        return list(self._tools.values())

    def get_openai_functions(self) -> list[dict]:
        """
        Get all tools in OpenAI function format.

        Returns:
            List of function definitions for OpenAI API
        """
        return [tool.to_openai_function() for tool in self._tools.values()]

    def list_names(self) -> list[str]:
        """Get list of all tool names."""
        return list(self._tools.keys())

    async def execute(self, name: str, params: dict) -> ToolResult:
        """
        Execute a tool by name.

        Args:
            name: The tool name
            params: Parameters to pass to the tool

        Returns:
            ToolResult from the tool execution
        """
        tool = self.get(name)
        if not tool:
            return ToolResult(success=False, error=f"Tool '{name}' not found")

        try:
            logger.info(f"Executing tool: {name}")
            result = await tool.execute(params)
            return result
        except Exception as e:
            logger.error(f"Tool execution failed: {name}", e)
            return ToolResult(success=False, error=str(e))


# Global tool registry instance
tool_registry = ToolRegistry()


# Import and register tools from submodules
# This happens when the module is imported
def _register_all_tools():
    """Register all tools from submodules."""
    # Import tool modules (they will register themselves)
    from src.tools import slack_tools
    from src.tools import github_tools
    from src.tools import notion_tools
    from src.tools import scheduler

    logger.info(f"Registered {len(tool_registry.list_names())} tools")


# Note: Don't call _register_all_tools() here to avoid circular imports
# It's called from main.py after all imports are ready


__all__ = [
    "MCPTool",
    "ToolResult",
    "ToolRegistry",
    "tool_registry",
]
