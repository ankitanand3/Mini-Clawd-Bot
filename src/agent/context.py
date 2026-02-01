"""
Context Assembly
================

Assembles context for the LLM from multiple sources:
- Memory (short-term, working, long-term, profile)
- RAG (semantic search over Slack history)
- Conversation history
- Tool definitions

The context assembler is responsible for:
1. Determining what context is relevant
2. Respecting token limits
3. Formatting context for the LLM

Token Budget:
    LLMs have context limits. We need to budget tokens for:
    - System message (~500-1000 tokens)
    - Memory context (~1000-2000 tokens)
    - RAG results (~500-1000 tokens)
    - Conversation history (~2000-4000 tokens)
    - Tool definitions (~500-1000 tokens)
    - User message (~100-500 tokens)
    - Response generation (~2000-4000 tokens)

    Total context is typically limited to 128k tokens for GPT-4 Turbo.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.memory import MemoryManager, MemoryContext
from src.utils.logger import Logger

if TYPE_CHECKING:
    from src.rag import RAGManager, RAGResult

logger = Logger("Context")


@dataclass
class AssembledContext:
    """
    The fully assembled context for the LLM.

    Attributes:
        system_message: The system prompt with personality and context
        messages: Conversation history in OpenAI format
        tools: List of available tools in OpenAI function format
        rag_results: Optional RAG search results
    """
    system_message: str
    messages: list[dict]
    tools: list[dict] = field(default_factory=list)
    rag_results: list["RAGResult"] = field(default_factory=list)

    def to_openai_messages(self) -> list[dict]:
        """
        Format as messages for OpenAI API.

        Returns:
            List of message dicts ready for the API
        """
        result = [{"role": "system", "content": self.system_message}]
        result.extend(self.messages)
        return result


class ContextAssembler:
    """
    Assembles context for LLM requests.

    The assembler coordinates:
    - Memory recall (what the bot remembers)
    - RAG search (relevant Slack history)
    - Conversation history
    - System prompt generation

    Example:
        assembler = ContextAssembler(memory, rag)

        context = await assembler.assemble(
            user_id="U123",
            user_message="Summarize #engineering from today",
            channel_type="dm"
        )

        response = await openai.chat.completions.create(
            messages=context.to_openai_messages(),
            tools=context.tools
        )
    """

    # Base system prompt defining the bot's behavior
    BASE_SYSTEM_PROMPT = """You are MiniClawd, an intelligent Slack assistant.

Your capabilities:
- Summarize Slack channel discussions
- Set reminders and schedule messages
- Create GitHub issues from discussions
- Create Notion pages for documentation
- Remember important information

Guidelines:
- Be helpful, concise, and professional
- Ask clarifying questions when needed
- Use tools to accomplish tasks
- Remember context from our conversation

{personality}

{user_context}

{memory_context}

{rag_context}
"""

    def __init__(
        self,
        memory: MemoryManager,
        rag: "RAGManager | None" = None
    ):
        """
        Initialize the context assembler.

        Args:
            memory: Memory manager instance
            rag: Optional RAG manager for semantic search
        """
        self.memory = memory
        self.rag = rag

    async def assemble(
        self,
        user_id: str,
        user_message: str,
        channel_type: str = "dm",
        include_rag: bool = True
    ) -> AssembledContext:
        """
        Assemble full context for an LLM request.

        Args:
            user_id: The Slack user ID
            user_message: The user's message
            channel_type: "dm" for direct messages, "channel" for public
            include_rag: Whether to search RAG for context

        Returns:
            AssembledContext with system message and conversation
        """
        logger.debug(f"Assembling context for user {user_id}")

        # 1. Recall memory context
        memory_context = await self._get_memory_context(user_id, user_message, channel_type)

        # 2. Optionally get RAG context
        rag_results = []
        rag_context_str = ""
        if include_rag and self.rag and self.rag.should_use_rag(user_message):
            rag_results = await self.rag.search(user_message, top_k=5)
            rag_context_str = self._format_rag_results(rag_results)
            logger.debug(f"Retrieved {len(rag_results)} RAG results")

        # 3. Build the system message
        system_message = self._build_system_message(
            memory_context=memory_context,
            rag_context=rag_context_str,
            channel_type=channel_type
        )

        # 4. Get conversation history
        conversation = memory_context.conversation.copy()

        # 5. Add the current user message
        conversation.append({"role": "user", "content": user_message})

        # 6. Store the user message in short-term memory
        self.memory.add_message(user_id, "user", user_message)

        # 7. Get tool definitions
        from src.tools import tool_registry
        tools = tool_registry.get_openai_functions()

        return AssembledContext(
            system_message=system_message,
            messages=conversation,
            tools=tools,
            rag_results=rag_results
        )

    async def _get_memory_context(
        self,
        user_id: str,
        query: str,
        channel_type: str
    ) -> MemoryContext:
        """
        Get memory context appropriate for the channel type.

        In DMs, we include personal memory. In channels, we limit context.
        """
        if channel_type == "dm":
            # Full memory access in DMs
            return await self.memory.recall(user_id, query, include_profile=True)
        else:
            # Limited context in public channels
            # Don't expose personal memory in public
            context = MemoryContext()
            context.conversation = self.memory.get_conversation(user_id, limit=5)
            context.profile = "## Bot Guidelines\n" + self.memory.get_soul()
            return context

    def _format_rag_results(self, results: list["RAGResult"]) -> str:
        """Format RAG results as context for the system message."""
        if not results:
            return ""

        lines = ["## Relevant Slack Messages"]
        for r in results[:5]:  # Limit to top 5
            lines.append(f"- [{r.channel_name}] {r.author}: {r.content[:200]}")

        return "\n".join(lines)

    def _build_system_message(
        self,
        memory_context: MemoryContext,
        rag_context: str,
        channel_type: str
    ) -> str:
        """Build the system message with all context."""
        # Get personality from SOUL.md
        personality = memory_context.profile if memory_context.profile else ""

        # Get user context (only in DMs)
        user_context = ""
        if channel_type == "dm":
            user_info = self.memory.get_user_profile()
            if user_info:
                user_context = f"## User Information\n{user_info[:500]}"

        # Get long-term memory context
        memory_str = memory_context.long_term if memory_context.long_term else ""

        # Build the final system message
        system_message = self.BASE_SYSTEM_PROMPT.format(
            personality=personality,
            user_context=user_context,
            memory_context=memory_str,
            rag_context=rag_context
        )

        # Clean up empty sections
        system_message = "\n".join(
            line for line in system_message.split("\n")
            if line.strip()
        )

        return system_message

    def add_assistant_message(self, user_id: str, content: str) -> None:
        """
        Add an assistant message to memory.

        Call this after generating a response.

        Args:
            user_id: The Slack user ID
            content: The assistant's response
        """
        self.memory.add_message(user_id, "assistant", content)
