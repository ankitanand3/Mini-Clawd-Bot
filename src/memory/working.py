"""
Working Memory
==============

Session-scoped temporary storage for notes and intermediate data.

Working memory is for information that:
- Is useful during the current session
- Shouldn't be persisted to disk
- Might be promoted to long-term memory explicitly

Examples of working memory use:
- Temporary notes about what the user is working on
- Intermediate results during multi-step tasks
- Context from earlier in a complex conversation
- Draft content before final save

This is separate from short-term memory (which stores conversation messages)
and long-term memory (which persists to files).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class WorkingNote:
    """
    A single note in working memory.

    Attributes:
        key: Identifier for the note
        value: The note content
        created_at: When the note was created
        updated_at: When the note was last updated
    """
    key: str
    value: str
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


class WorkingMemory:
    """
    Session-scoped temporary storage.

    Working memory provides a key-value store for temporary notes that
    live only during the current session. Unlike short-term memory
    (conversation messages), working memory is for arbitrary data.

    Use cases:
    - "Remember that I'm working on the API refactor"
    - Store intermediate results during a multi-tool operation
    - Keep track of user intent across conversation turns

    Example:
        wm = WorkingMemory()

        # Store a note
        wm.set("U123", "current_project", "API refactor")

        # Retrieve it later
        project = wm.get("U123", "current_project")

        # List all notes for a user
        notes = wm.get_all("U123")

        # Clear when done
        wm.clear("U123")
    """

    def __init__(self):
        """Initialize working memory."""
        # Dictionary mapping user_id -> dict of key -> WorkingNote
        self._storage: dict[str, dict[str, WorkingNote]] = {}

    def set(self, user_id: str, key: str, value: str) -> None:
        """
        Store or update a note.

        Args:
            user_id: The Slack user ID
            key: A key to identify the note
            value: The note content
        """
        # Initialize user's storage if needed
        if user_id not in self._storage:
            self._storage[user_id] = {}

        # Check if updating existing note
        if key in self._storage[user_id]:
            note = self._storage[user_id][key]
            note.value = value
            note.updated_at = datetime.now()
        else:
            # Create new note
            self._storage[user_id][key] = WorkingNote(key=key, value=value)

    def get(self, user_id: str, key: str) -> str | None:
        """
        Retrieve a note by key.

        Args:
            user_id: The Slack user ID
            key: The note key

        Returns:
            The note value, or None if not found
        """
        if user_id not in self._storage:
            return None
        note = self._storage[user_id].get(key)
        return note.value if note else None

    def get_all(self, user_id: str) -> dict[str, str]:
        """
        Get all notes for a user.

        Args:
            user_id: The Slack user ID

        Returns:
            Dictionary of key -> value for all notes
        """
        if user_id not in self._storage:
            return {}
        return {key: note.value for key, note in self._storage[user_id].items()}

    def delete(self, user_id: str, key: str) -> bool:
        """
        Delete a specific note.

        Args:
            user_id: The Slack user ID
            key: The note key

        Returns:
            True if the note existed and was deleted
        """
        if user_id not in self._storage:
            return False
        if key in self._storage[user_id]:
            del self._storage[user_id][key]
            return True
        return False

    def clear(self, user_id: str) -> None:
        """
        Clear all notes for a user.

        Args:
            user_id: The Slack user ID
        """
        if user_id in self._storage:
            del self._storage[user_id]

    def clear_all(self) -> None:
        """Clear all working memory."""
        self._storage.clear()

    def has_notes(self, user_id: str) -> bool:
        """Check if a user has any notes."""
        return user_id in self._storage and len(self._storage[user_id]) > 0

    def to_context_string(self, user_id: str) -> str:
        """
        Format all notes as a context string for the LLM.

        Useful for including working memory in the prompt.

        Args:
            user_id: The Slack user ID

        Returns:
            Formatted string of all notes, or empty string if none
        """
        notes = self.get_all(user_id)
        if not notes:
            return ""

        lines = ["## Working Notes"]
        for key, value in notes.items():
            lines.append(f"- **{key}**: {value}")

        return "\n".join(lines)
