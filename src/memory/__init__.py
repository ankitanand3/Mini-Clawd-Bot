"""
Memory System
=============

A multi-layer memory system that mimics human memory:

1. SHORT-TERM: Current conversation context (in-memory)
2. WORKING: Session-scoped notes and temporary data
3. LONG-TERM: Persistent knowledge in MEMORY.md and daily logs
4. PROFILE: User preferences (USER.md) and bot personality (SOUL.md)
5. TASK STATE: Scheduled tasks and reminders

This module provides a Facade pattern - a single MemoryManager class
that coordinates all memory layers and provides a simple interface.

Usage:
    from src.memory import MemoryManager

    memory = MemoryManager()

    # Store a message in short-term memory
    memory.add_message(user_id="U123", role="user", content="Hello!")

    # Recall relevant context for a query
    context = await memory.recall("What did we discuss about the API?")

    # Write to long-term memory
    await memory.write_long_term("User prefers morning standups", category="preferences")
"""

from src.memory.short_term import ShortTermMemory
from src.memory.working import WorkingMemory
from src.memory.long_term import LongTermMemory
from src.memory.profile import ProfileManager
from src.memory.recall import MemoryRecall, MemoryContext

from src.utils.logger import Logger
from src.utils.config import get_config

logger = Logger("Memory")


class MemoryManager:
    """
    Facade for the multi-layer memory system.

    The MemoryManager coordinates all memory layers and provides a unified
    interface for the rest of the application. This follows the Facade pattern:
    a simple interface to a complex subsystem.

    Memory Layers:
    - short_term: In-memory conversation history per user
    - working: Session notes that don't persist
    - long_term: File-backed persistent memory
    - profile: USER.md, SOUL.md, TOOLS.md files

    Example:
        memory = MemoryManager()

        # Add a conversation message
        memory.add_message("U123", "user", "Hello!")
        memory.add_message("U123", "assistant", "Hi there!")

        # Get conversation history
        history = memory.get_conversation("U123")

        # Recall context for a query
        context = await memory.recall("U123", "What's my preferred meeting time?")

        # Write important information to long-term memory
        await memory.write_long_term("User prefers 10am meetings", "preferences")
    """

    def __init__(self):
        """Initialize all memory layers."""
        config = get_config()

        # Initialize each memory layer
        self.short_term = ShortTermMemory()
        self.working = WorkingMemory()
        self.long_term = LongTermMemory(config.memory.directory)
        self.profile = ProfileManager(config.memory.directory)

        # The recall system searches across layers
        self.recall_system = MemoryRecall(
            short_term=self.short_term,
            working=self.working,
            long_term=self.long_term,
            profile=self.profile
        )

        logger.info("Memory system initialized")

    # ==========================================================================
    # Short-Term Memory Operations
    # ==========================================================================

    def add_message(
        self,
        user_id: str,
        role: str,
        content: str,
        metadata: dict | None = None
    ) -> None:
        """
        Add a message to short-term memory.

        Short-term memory stores the current conversation context for each user.
        Messages are stored in-memory and cleared when the bot restarts.

        Args:
            user_id: The Slack user ID (e.g., "U123ABC")
            role: Message role ("user", "assistant", or "system")
            content: The message content
            metadata: Optional metadata (e.g., channel, timestamp)
        """
        self.short_term.add_message(user_id, role, content, metadata)
        logger.debug(f"Added message to short-term memory for {user_id}")

    def get_conversation(
        self,
        user_id: str,
        limit: int = 20
    ) -> list[dict]:
        """
        Get recent conversation history for a user.

        Args:
            user_id: The Slack user ID
            limit: Maximum number of messages to return

        Returns:
            List of message dicts with role and content
        """
        return self.short_term.get_recent(user_id, limit)

    def clear_conversation(self, user_id: str) -> None:
        """
        Clear a user's conversation history.

        Useful when starting a new topic or on explicit request.

        Args:
            user_id: The Slack user ID
        """
        self.short_term.clear(user_id)
        logger.info(f"Cleared conversation for {user_id}")

    # ==========================================================================
    # Working Memory Operations
    # ==========================================================================

    def note(self, user_id: str, key: str, value: str) -> None:
        """
        Store a temporary note in working memory.

        Working memory is for session-scoped data that shouldn't persist.
        Use this for temporary context, intermediate results, etc.

        Args:
            user_id: The Slack user ID
            key: A key to identify the note
            value: The note content
        """
        self.working.set(user_id, key, value)

    def get_note(self, user_id: str, key: str) -> str | None:
        """
        Retrieve a note from working memory.

        Args:
            user_id: The Slack user ID
            key: The note key

        Returns:
            The note value, or None if not found
        """
        return self.working.get(user_id, key)

    # ==========================================================================
    # Long-Term Memory Operations
    # ==========================================================================

    async def write_long_term(
        self,
        content: str,
        category: str = "general"
    ) -> None:
        """
        Write information to long-term memory.

        Long-term memory is persisted to MEMORY.md and is organized by category.
        Use this for important facts, decisions, and user preferences.

        Args:
            content: The information to store
            category: Category for organization (e.g., "preferences", "decisions")
        """
        await self.long_term.write(content, category)
        logger.info(f"Wrote to long-term memory: {category}")

    async def write_daily_log(self, content: str) -> None:
        """
        Write to today's daily log.

        Daily logs capture day-to-day activity and are stored in
        memory/daily/YYYY-MM-DD.md files.

        Args:
            content: The log entry content
        """
        await self.long_term.write_daily(content)

    # ==========================================================================
    # Profile Operations
    # ==========================================================================

    def get_soul(self) -> str:
        """
        Get the bot's personality/behavior guidelines.

        The SOUL.md file defines how the bot should behave, its tone,
        and any guidelines for responses.

        Returns:
            The contents of SOUL.md
        """
        return self.profile.get_soul()

    def get_user_profile(self) -> str:
        """
        Get user preferences and information.

        The USER.md file stores user-specific preferences, settings,
        and important information about the user.

        Returns:
            The contents of USER.md
        """
        return self.profile.get_user()

    def get_tools_context(self) -> str:
        """
        Get tool and environment context.

        The TOOLS.md file stores information about configured tools,
        API details, and environment-specific notes.

        Returns:
            The contents of TOOLS.md
        """
        return self.profile.get_tools()

    # ==========================================================================
    # Memory Recall
    # ==========================================================================

    async def recall(
        self,
        user_id: str,
        query: str,
        include_profile: bool = True
    ) -> MemoryContext:
        """
        Recall relevant memory context for a query.

        This is the main interface for retrieving context. It searches
        across all memory layers and returns the most relevant information.

        The recall process:
        1. Gets recent short-term conversation history
        2. Searches long-term memory for relevant entries
        3. Optionally includes profile information
        4. Combines and truncates to fit token limits

        Args:
            user_id: The Slack user ID
            query: The query to find relevant context for
            include_profile: Whether to include profile files

        Returns:
            MemoryContext with conversation history and relevant memories
        """
        return await self.recall_system.recall(
            user_id=user_id,
            query=query,
            include_profile=include_profile
        )


# Export key classes
__all__ = [
    "MemoryManager",
    "MemoryContext",
    "ShortTermMemory",
    "WorkingMemory",
    "LongTermMemory",
    "ProfileManager",
]
