"""
Agent System
============

The agent is the brain of the bot. It:
1. Receives user requests
2. Assembles context (memory, RAG, conversation)
3. Decides what actions to take
4. Executes tools as needed
5. Generates responses

This module provides:
- Agent: Main agent class for processing requests
- ContextAssembler: Builds context for the LLM
- ToolExecutor: Handles tool execution loop
"""

from src.agent.core import Agent
from src.agent.context import ContextAssembler
from src.agent.tools_executor import ToolExecutor

__all__ = ["Agent", "ContextAssembler", "ToolExecutor"]
