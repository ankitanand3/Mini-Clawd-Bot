"""
Short-Term Memory
=================

In-memory storage for current conversation context. Short-term memory:

- Stores conversation history per user
- Lives only in RAM (cleared on restart)
- Provides quick access to recent messages
- Has a configurable message limit per user

This is analogous to human short-term/working memory - it holds the
current context of what we're actively thinking about.

Design Notes:
- Uses a dictionary with user_id as key
- Each user has a list of messages (role, content, metadata)
- Automatically trims old messages when limit is exceeded
- Thread-safe for concurrent access (using basic dict operations)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Message:
    """
    A single message in the conversation.

    Attributes:
        role: Who sent the message ("user", "assistant", "system")
        content: The message text
        timestamp: When the message was added
        metadata: Optional extra data (channel, thread_ts, etc.)
    """
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary format for LLM API calls."""
        return {
            "role": self.role,
            "content": self.content,
        }


class ShortTermMemory:
    """
    In-memory conversation storage.

    Stores recent conversation history for each user. Messages are kept
    in memory and lost when the application restarts.

    Attributes:
        max_messages: Maximum messages to keep per user (default 50)

    Example:
        stm = ShortTermMemory(max_messages=30)

        # Add messages
        stm.add_message("U123", "user", "Hello!")
        stm.add_message("U123", "assistant", "Hi there!")

        # Get recent history
        history = stm.get_recent("U123", limit=10)

        # Clear for a fresh start
        stm.clear("U123")
    """

    def __init__(self, max_messages: int = 50):
        """
        Initialize short-term memory.

        Args:
            max_messages: Maximum messages to keep per user
        """
        self.max_messages = max_messages
        # Dictionary mapping user_id -> list of Messages
        self._conversations: dict[str, list[Message]] = {}

    def add_message(
        self,
        user_id: str,
        role: str,
        content: str,
        metadata: dict | None = None
    ) -> None:
        """
        Add a message to a user's conversation history.

        If the conversation exceeds max_messages, older messages are removed.

        Args:
            user_id: The Slack user ID
            role: Message role ("user", "assistant", "system")
            content: The message content
            metadata: Optional metadata (channel, timestamp, etc.)
        """
        # Initialize conversation list if needed
        if user_id not in self._conversations:
            self._conversations[user_id] = []

        # Create and add the message
        message = Message(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        self._conversations[user_id].append(message)

        # Trim if over limit (remove oldest messages)
        if len(self._conversations[user_id]) > self.max_messages:
            # Keep the most recent messages
            self._conversations[user_id] = self._conversations[user_id][-self.max_messages:]

    def get_recent(self, user_id: str, limit: int = 20) -> list[dict]:
        """
        Get recent messages for a user.

        Returns messages in chronological order (oldest first), formatted
        for use with LLM APIs.

        Args:
            user_id: The Slack user ID
            limit: Maximum number of messages to return

        Returns:
            List of message dicts with 'role' and 'content' keys
        """
        if user_id not in self._conversations:
            return []

        # Get the most recent messages up to limit
        messages = self._conversations[user_id][-limit:]

        # Convert to dict format for LLM
        return [msg.to_dict() for msg in messages]

    def get_all_messages(self, user_id: str) -> list[Message]:
        """
        Get all messages for a user as Message objects.

        Useful when you need access to timestamps and metadata.

        Args:
            user_id: The Slack user ID

        Returns:
            List of Message objects
        """
        return self._conversations.get(user_id, []).copy()

    def clear(self, user_id: str) -> None:
        """
        Clear a user's conversation history.

        Args:
            user_id: The Slack user ID
        """
        if user_id in self._conversations:
            del self._conversations[user_id]

    def clear_all(self) -> None:
        """Clear all conversations (e.g., for shutdown)."""
        self._conversations.clear()

    def get_user_count(self) -> int:
        """Get the number of users with active conversations."""
        return len(self._conversations)

    def get_message_count(self, user_id: str) -> int:
        """Get the number of messages for a specific user."""
        return len(self._conversations.get(user_id, []))
