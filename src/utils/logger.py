"""
Logger Utility
==============

A simple but effective logging system for the bot. This module demonstrates:

1. Log levels (DEBUG, INFO, WARNING, ERROR)
2. Structured output with timestamps
3. Context-aware logging with child loggers
4. Color-coded terminal output

Why a custom logger instead of Python's logging module?
- Simpler API for educational purposes
- Demonstrates logging concepts clearly
- Easy to extend with custom formatters
- In production, you'd typically use Python's logging or structlog

Usage:
    from src.utils.logger import Logger, logger

    # Use the default logger
    logger.info("Application started")

    # Create a context-specific logger
    agent_logger = Logger("Agent")
    agent_logger.debug("Processing request", {"user": "U123"})
"""

import os
import sys
from datetime import datetime
from enum import IntEnum
from typing import Any


class LogLevel(IntEnum):
    """
    Log levels with numeric values for comparison.
    Higher values = more severe = always shown.
    """
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40


# ANSI color codes for terminal output
# These make logs easier to scan visually
class Colors:
    """ANSI escape codes for colored terminal output."""
    RESET = "\033[0m"
    DEBUG = "\033[36m"    # Cyan
    INFO = "\033[32m"     # Green
    WARNING = "\033[33m"  # Yellow
    ERROR = "\033[31m"    # Red
    DIM = "\033[2m"       # Dimmed text


def _get_log_level_from_env() -> LogLevel:
    """
    Parse the LOG_LEVEL environment variable.

    Returns:
        LogLevel: The configured log level, defaults to INFO
    """
    level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    level_map = {
        "DEBUG": LogLevel.DEBUG,
        "INFO": LogLevel.INFO,
        "WARNING": LogLevel.WARNING,
        "WARN": LogLevel.WARNING,
        "ERROR": LogLevel.ERROR,
    }
    return level_map.get(level_str, LogLevel.INFO)


class Logger:
    """
    A context-aware logger with colored output.

    The logger supports:
    - Multiple log levels (debug, info, warning, error)
    - Context prefixes for tracing through code
    - Optional structured data as JSON
    - Child loggers for nested contexts

    Example:
        logger = Logger("MyComponent")
        logger.info("Starting up")

        # Create a child logger for a sub-operation
        child = logger.child("SubOperation")
        child.debug("Processing item", {"item_id": 123})
    """

    def __init__(self, context: str = ""):
        """
        Initialize a logger with an optional context.

        Args:
            context: A string prefix for all log messages (e.g., "Agent", "Memory")
        """
        self.context = context
        self._min_level = _get_log_level_from_env()

    def child(self, child_context: str) -> "Logger":
        """
        Create a child logger with additional context.

        Useful for tracing through nested operations.

        Args:
            child_context: Additional context to append

        Returns:
            A new Logger with combined context

        Example:
            agent_logger = Logger("Agent")
            tool_logger = agent_logger.child("ToolExec")
            # Logs will show [Agent:ToolExec]
        """
        new_context = f"{self.context}:{child_context}" if self.context else child_context
        return Logger(new_context)

    def _format_message(
        self,
        level: str,
        message: str,
        color: str
    ) -> str:
        """
        Format a log message with timestamp, level, and context.

        Output format: [TIMESTAMP] [LEVEL] [context] message
        Example: [2024-01-31T10:30:00] [INFO] [Agent] Processing request...
        """
        timestamp = datetime.now().isoformat(timespec="seconds")
        context_str = f"[{self.context}] " if self.context else ""

        return (
            f"{Colors.DIM}[{timestamp}]{Colors.RESET} "
            f"{color}[{level}]{Colors.RESET} "
            f"{context_str}{message}"
        )

    def _log(
        self,
        level: LogLevel,
        level_name: str,
        color: str,
        message: str,
        data: dict[str, Any] | None = None
    ) -> None:
        """
        Internal logging method.

        Args:
            level: The log level for filtering
            level_name: Display name of the level
            color: ANSI color code for the level
            message: The log message
            data: Optional structured data to include
        """
        if level < self._min_level:
            return

        formatted = self._format_message(level_name, message, color)

        # Choose output stream based on level
        stream = sys.stderr if level >= LogLevel.ERROR else sys.stdout
        print(formatted, file=stream)

        # Print structured data if provided
        if data:
            import json
            data_str = json.dumps(data, indent=2, default=str)
            print(f"{Colors.DIM}{data_str}{Colors.RESET}", file=stream)

    def debug(self, message: str, data: dict[str, Any] | None = None) -> None:
        """
        Log a debug message.

        Debug messages are for detailed information useful during development.
        Only shown when LOG_LEVEL=DEBUG.

        Args:
            message: The debug message
            data: Optional structured data to log
        """
        self._log(LogLevel.DEBUG, "DEBUG", Colors.DEBUG, message, data)

    def info(self, message: str, data: dict[str, Any] | None = None) -> None:
        """
        Log an info message.

        Info messages are for general operational information.
        This is the default log level.

        Args:
            message: The info message
            data: Optional structured data to log
        """
        self._log(LogLevel.INFO, "INFO", Colors.INFO, message, data)

    def warning(self, message: str, data: dict[str, Any] | None = None) -> None:
        """
        Log a warning message.

        Warnings are for potentially problematic situations that don't
        prevent operation but should be noted.

        Args:
            message: The warning message
            data: Optional structured data to log
        """
        self._log(LogLevel.WARNING, "WARN", Colors.WARNING, message, data)

    def error(self, message: str, error: Exception | None = None) -> None:
        """
        Log an error message.

        Errors indicate something went wrong. Always shown regardless
        of log level.

        Args:
            message: The error message
            error: Optional exception to include details from
        """
        data = None
        if error:
            data = {
                "error_type": type(error).__name__,
                "error_message": str(error),
            }
        self._log(LogLevel.ERROR, "ERROR", Colors.ERROR, message, data)


# Default logger instance for general use
# Import this when you need quick logging without creating a new Logger
logger = Logger("Bot")
