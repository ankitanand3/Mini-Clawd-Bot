"""
Memory Recall
=============

Intelligent memory retrieval that searches across all memory layers
and returns relevant context for a given query.

The recall process:
1. Always include recent short-term conversation
2. Include any working memory notes
3. Search long-term memory for relevant entries
4. Optionally include profile files
5. Combine and format for LLM context

This module is the "brain" of the memory system - it decides what
information is relevant and how to present it.

Token Budget Considerations:
- LLMs have context limits (e.g., 128k tokens for GPT-4 Turbo)
- We need to leave room for the user's query, tools, and response
- Memory context is typically budgeted at ~2000-4000 tokens
- We prioritize recent/relevant information
"""

from dataclasses import dataclass, field

from src.memory.short_term import ShortTermMemory
from src.memory.working import WorkingMemory
from src.memory.long_term import LongTermMemory
from src.memory.profile import ProfileManager
from src.utils.logger import Logger

logger = Logger("MemoryRecall")


@dataclass
class MemoryContext:
    """
    Container for recalled memory context.

    This is what gets passed to the agent for inclusion in the LLM prompt.

    Attributes:
        conversation: Recent conversation history (list of messages)
        working_notes: Current working memory notes
        long_term: Relevant long-term memory entries
        profile: Profile context (SOUL, USER, TOOLS)
        total_tokens_estimate: Rough estimate of token count
    """
    conversation: list[dict] = field(default_factory=list)
    working_notes: str = ""
    long_term: str = ""
    profile: str = ""
    total_tokens_estimate: int = 0

    def to_system_context(self) -> str:
        """
        Format all memory as a system context string.

        This is typically included in the system message for the LLM.

        Returns:
            Formatted string with all memory context
        """
        sections = []

        if self.profile:
            sections.append("# Context\n\n" + self.profile)

        if self.long_term:
            sections.append("# Relevant Memory\n\n" + self.long_term)

        if self.working_notes:
            sections.append("# Working Notes\n\n" + self.working_notes)

        return "\n\n---\n\n".join(sections)

    def is_empty(self) -> bool:
        """Check if no context was recalled."""
        return (
            not self.conversation
            and not self.working_notes
            and not self.long_term
            and not self.profile
        )


class MemoryRecall:
    """
    Orchestrates memory recall across all layers.

    The MemoryRecall class is responsible for:
    1. Determining what information is relevant to a query
    2. Searching across memory layers
    3. Combining and prioritizing results
    4. Respecting token budgets

    Example:
        recall = MemoryRecall(short_term, working, long_term, profile)

        # Get context for a query
        context = await recall.recall(
            user_id="U123",
            query="What's my preferred meeting time?",
            include_profile=True
        )

        # Use in LLM prompt
        system_context = context.to_system_context()
    """

    # Approximate token limits for each section
    # These are rough estimates (1 token ≈ 4 characters)
    MAX_CONVERSATION_TOKENS = 1500
    MAX_LONG_TERM_TOKENS = 1000
    MAX_PROFILE_TOKENS = 1000

    def __init__(
        self,
        short_term: ShortTermMemory,
        working: WorkingMemory,
        long_term: LongTermMemory,
        profile: ProfileManager
    ):
        """
        Initialize the recall system.

        Args:
            short_term: Short-term memory instance
            working: Working memory instance
            long_term: Long-term memory instance
            profile: Profile manager instance
        """
        self.short_term = short_term
        self.working = working
        self.long_term = long_term
        self.profile = profile

    async def recall(
        self,
        user_id: str,
        query: str,
        include_profile: bool = True,
        max_conversation_messages: int = 10
    ) -> MemoryContext:
        """
        Recall relevant context for a query.

        This is the main entry point for memory recall. It searches
        across all memory layers and returns combined context.

        Args:
            user_id: The Slack user ID
            query: The query to find relevant context for
            include_profile: Whether to include SOUL/USER/TOOLS files
            max_conversation_messages: Max conversation messages to include

        Returns:
            MemoryContext with all relevant context
        """
        context = MemoryContext()

        # 1. Always include recent conversation
        context.conversation = self.short_term.get_recent(
            user_id,
            limit=max_conversation_messages
        )
        logger.debug(f"Retrieved {len(context.conversation)} conversation messages")

        # 2. Include working memory notes
        context.working_notes = self.working.to_context_string(user_id)
        if context.working_notes:
            logger.debug("Included working memory notes")

        # 3. Search long-term memory for relevant entries
        context.long_term = await self._search_long_term(query)
        if context.long_term:
            logger.debug("Found relevant long-term memory")

        # 4. Include profile if requested
        if include_profile:
            context.profile = self._get_profile_context()

        # 5. Estimate total tokens
        context.total_tokens_estimate = self._estimate_tokens(context)

        logger.debug(f"Total context tokens (estimate): {context.total_tokens_estimate}")

        return context

    async def _search_long_term(self, query: str) -> str:
        """
        Search long-term memory for relevant entries.

        This uses keyword matching to find relevant entries in MEMORY.md.
        For more sophisticated semantic search, use the RAG system.

        Args:
            query: The query to search for

        Returns:
            Formatted string of relevant entries
        """
        # Search MEMORY.md
        results = await self.long_term.search(query)

        if not results:
            return ""

        # Format results
        lines = ["## From Long-Term Memory"]
        for entry in results[:10]:  # Limit to top 10 results
            lines.append(entry)

        return "\n".join(lines)

    def _get_profile_context(self) -> str:
        """
        Get profile context, truncated if necessary.

        Returns:
            Combined profile context
        """
        # Get SOUL.md (bot personality) - most important
        soul = self.profile.get_soul()

        # Get USER.md (user preferences)
        user = self.profile.get_user()

        # Build context string
        sections = []

        if soul:
            # Truncate if too long
            soul_truncated = self._truncate_to_tokens(soul, self.MAX_PROFILE_TOKENS // 2)
            sections.append("## Bot Guidelines\n" + soul_truncated)

        if user:
            user_truncated = self._truncate_to_tokens(user, self.MAX_PROFILE_TOKENS // 2)
            sections.append("## User Profile\n" + user_truncated)

        return "\n\n".join(sections)

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """
        Truncate text to approximately max_tokens.

        Uses a simple heuristic: 1 token ≈ 4 characters.

        Args:
            text: The text to truncate
            max_tokens: Maximum tokens allowed

        Returns:
            Truncated text
        """
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text

        # Truncate and add indicator
        truncated = text[:max_chars - 20]
        # Try to break at a line boundary
        last_newline = truncated.rfind("\n")
        if last_newline > max_chars * 0.8:  # Only if we don't lose too much
            truncated = truncated[:last_newline]

        return truncated + "\n\n[... truncated]"

    def _estimate_tokens(self, context: MemoryContext) -> int:
        """
        Estimate the total token count of the context.

        Uses a simple heuristic: 1 token ≈ 4 characters.

        Args:
            context: The memory context to estimate

        Returns:
            Estimated token count
        """
        total_chars = 0

        # Conversation messages
        for msg in context.conversation:
            total_chars += len(msg.get("content", ""))

        # Working notes
        total_chars += len(context.working_notes)

        # Long-term memory
        total_chars += len(context.long_term)

        # Profile
        total_chars += len(context.profile)

        return total_chars // 4

    async def recall_for_private_context(
        self,
        user_id: str,
        query: str
    ) -> MemoryContext:
        """
        Recall context for a private (DM) conversation.

        In DM context, we include the full MEMORY.md and more personal
        information. This is not used in group channels.

        Args:
            user_id: The Slack user ID
            query: The query for context

        Returns:
            MemoryContext with full personal context
        """
        # Use full recall with profile
        context = await self.recall(
            user_id=user_id,
            query=query,
            include_profile=True,
            max_conversation_messages=15  # More context in DMs
        )

        # In DMs, also include recent daily log entries
        recent_entries = await self.long_term.get_recent_entries(days=3)
        if recent_entries:
            context.long_term += "\n\n## Recent Activity\n" + "\n".join(recent_entries[:20])

        return context

    async def recall_for_public_context(
        self,
        user_id: str,
        query: str
    ) -> MemoryContext:
        """
        Recall context for a public (channel) conversation.

        In public context, we exclude personal information from MEMORY.md
        and USER.md to protect privacy.

        Args:
            user_id: The Slack user ID
            query: The query for context

        Returns:
            MemoryContext with limited context for public use
        """
        # Only include conversation and SOUL (bot personality)
        context = MemoryContext()

        context.conversation = self.short_term.get_recent(user_id, limit=5)
        context.profile = "## Bot Guidelines\n" + self.profile.get_soul()

        context.total_tokens_estimate = self._estimate_tokens(context)

        return context
