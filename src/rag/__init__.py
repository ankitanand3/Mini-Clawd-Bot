"""
RAG (Retrieval Augmented Generation) System
============================================

The RAG system provides semantic search over Slack channel history.
Instead of loading entire channel histories into context (which would
exceed token limits), RAG:

1. Indexes messages as vector embeddings
2. Searches for semantically similar content
3. Returns only the most relevant messages

Components:
- embeddings.py: Generate vector embeddings from text
- vectorstore.py: Store and search vectors
- indexer.py: Index Slack channels in the background

How RAG Works:
1. During indexing: Messages are converted to vectors and stored
2. During search: Query is converted to a vector, similar vectors are found
3. Retrieved messages are included in the LLM context

Why RAG?
- Channels can have thousands of messages
- LLMs have context limits (e.g., 128k tokens)
- Semantic search finds relevant content even with different wording
- Efficient - only load what's needed
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.rag.embeddings import EmbeddingGenerator
from src.rag.vectorstore import VectorStore, VectorDocument
from src.rag.indexer import ChannelIndexer
from src.utils.config import get_config
from src.utils.logger import Logger

if TYPE_CHECKING:
    from slack_sdk.web.async_client import AsyncWebClient

logger = Logger("RAG")


@dataclass
class RAGResult:
    """
    A single search result from the RAG system.

    Attributes:
        content: The message text
        channel: The Slack channel ID
        channel_name: Human-readable channel name
        author: The user who sent the message
        timestamp: When the message was sent
        score: Similarity score (0-1, higher is more similar)
    """
    content: str
    channel: str
    channel_name: str
    author: str
    timestamp: str
    score: float


class RAGManager:
    """
    Main interface for the RAG system.

    The RAGManager coordinates embeddings, vector storage, and indexing.
    It provides a simple interface for searching channel history.

    Example:
        rag = RAGManager(slack_client)

        # Index a channel
        await rag.index_channel("C123ABC", "general")

        # Search for relevant messages
        results = await rag.search("database migration", top_k=5)
        for result in results:
            print(f"[{result.channel_name}] {result.content[:100]}...")

        # Check if we should use RAG for a query
        if rag.should_use_rag("summarize #engineering"):
            results = await rag.search("engineering discussions")
    """

    def __init__(self, slack_client: "AsyncWebClient"):
        """
        Initialize the RAG manager.

        Args:
            slack_client: Async Slack client for fetching messages
        """
        config = get_config()

        self.embeddings = EmbeddingGenerator(
            api_key=config.openai.api_key,
            model=config.openai.embedding_model
        )

        self.vectorstore = VectorStore(
            storage_path=config.memory.directory.parent / "data" / "vectorstore"
        )

        self.indexer = ChannelIndexer(
            slack_client=slack_client,
            embeddings=self.embeddings,
            vectorstore=self.vectorstore,
            messages_per_channel=config.rag.messages_per_channel,
            min_message_length=config.rag.min_message_length
        )

        self._index_frequency_hours = config.rag.index_frequency_hours

        logger.info("RAG system initialized")

    async def search(
        self,
        query: str,
        top_k: int = 10,
        channel_filter: str | None = None
    ) -> list[RAGResult]:
        """
        Search for messages similar to the query.

        Uses semantic search to find messages that are conceptually
        similar to the query, even if they don't share exact words.

        Args:
            query: The search query
            top_k: Maximum number of results to return
            channel_filter: Optional channel ID to limit search to

        Returns:
            List of RAGResult objects, sorted by relevance
        """
        logger.debug(f"RAG search: '{query[:50]}...'")

        # Generate embedding for the query
        query_embedding = await self.embeddings.generate(query)

        # Search the vector store
        results = self.vectorstore.search(
            query_vector=query_embedding,
            top_k=top_k,
            filter_metadata={"channel": channel_filter} if channel_filter else None
        )

        # Convert to RAGResults
        rag_results = []
        for doc in results:
            rag_results.append(RAGResult(
                content=doc.content,
                channel=doc.metadata.get("channel", "unknown"),
                channel_name=doc.metadata.get("channel_name", "unknown"),
                author=doc.metadata.get("author", "unknown"),
                timestamp=doc.metadata.get("timestamp", ""),
                score=doc.score or 0.0
            ))

        logger.debug(f"Found {len(rag_results)} results")
        return rag_results

    async def index_channel(
        self,
        channel_id: str,
        channel_name: str
    ) -> int:
        """
        Index messages from a channel.

        This fetches recent messages and adds them to the vector store.
        Should be called periodically to keep the index fresh.

        Args:
            channel_id: The Slack channel ID
            channel_name: Human-readable channel name

        Returns:
            Number of messages indexed
        """
        return await self.indexer.index_channel(channel_id, channel_name)

    async def index_all_channels(
        self,
        channels: list[dict]
    ) -> dict[str, int]:
        """
        Index multiple channels.

        Args:
            channels: List of channel dicts with 'id' and 'name' keys

        Returns:
            Dict mapping channel_id to number of messages indexed
        """
        return await self.indexer.index_multiple(channels)

    def should_use_rag(self, query: str) -> bool:
        """
        Determine if RAG should be used for this query.

        RAG is useful when the user is asking about:
        - Past discussions or conversations
        - Channel history
        - Summarization of activity
        - Finding specific topics that were discussed

        Args:
            query: The user's query

        Returns:
            True if RAG would likely be helpful
        """
        query_lower = query.lower()

        # Keywords that suggest RAG would be helpful
        rag_indicators = [
            "summarize", "summary", "what happened", "what did",
            "discussed", "talking about", "mentioned",
            "last 24 hours", "yesterday", "this week", "recent",
            "find", "search", "look for", "any mention",
            "channel", "#",  # Channel references
        ]

        return any(indicator in query_lower for indicator in rag_indicators)

    def format_results_for_context(
        self,
        results: list[RAGResult],
        max_results: int = 5
    ) -> str:
        """
        Format RAG results as context for the LLM.

        Args:
            results: List of RAG search results
            max_results: Maximum results to include

        Returns:
            Formatted string for LLM context
        """
        if not results:
            return ""

        lines = ["## Relevant Messages from Slack"]

        for result in results[:max_results]:
            lines.append(
                f"- [{result.channel_name}] {result.author}: {result.content}"
            )

        return "\n".join(lines)


__all__ = [
    "RAGManager",
    "RAGResult",
    "EmbeddingGenerator",
    "VectorStore",
    "VectorDocument",
    "ChannelIndexer",
]
