"""
Channel Indexer
===============

Indexes Slack channel messages into the vector store for RAG search.

The indexer:
1. Fetches recent messages from Slack channels
2. Generates embeddings for each message
3. Stores them in the vector store

Indexing Strategy:
- Index the most recent N messages per channel (configurable)
- Skip very short messages (configurable minimum length)
- Re-index periodically to capture new messages
- Avoid duplicate entries using message timestamps as IDs

Background Indexing:
    In production, indexing should run in the background:
    - Initial index when bot joins a channel
    - Periodic re-indexing (e.g., every 6 hours)
    - Triggered indexing when user requests it
"""

from datetime import datetime
from typing import TYPE_CHECKING

from src.rag.embeddings import EmbeddingGenerator
from src.rag.vectorstore import VectorStore, VectorDocument
from src.utils.logger import Logger

if TYPE_CHECKING:
    from slack_sdk.web.async_client import AsyncWebClient

logger = Logger("Indexer")


class ChannelIndexer:
    """
    Indexes Slack channel messages for RAG search.

    Example:
        indexer = ChannelIndexer(
            slack_client=client,
            embeddings=embedding_generator,
            vectorstore=vector_store,
            messages_per_channel=200
        )

        # Index a single channel
        count = await indexer.index_channel("C123ABC", "general")
        print(f"Indexed {count} messages")

        # Index multiple channels
        results = await indexer.index_multiple([
            {"id": "C123", "name": "general"},
            {"id": "C456", "name": "engineering"}
        ])
    """

    def __init__(
        self,
        slack_client: "AsyncWebClient",
        embeddings: EmbeddingGenerator,
        vectorstore: VectorStore,
        messages_per_channel: int = 200,
        min_message_length: int = 10
    ):
        """
        Initialize the indexer.

        Args:
            slack_client: Async Slack client for fetching messages
            embeddings: Embedding generator for creating vectors
            vectorstore: Vector store for persisting documents
            messages_per_channel: Max messages to index per channel
            min_message_length: Minimum message length to index
        """
        self.slack_client = slack_client
        self.embeddings = embeddings
        self.vectorstore = vectorstore
        self.messages_per_channel = messages_per_channel
        self.min_message_length = min_message_length

    async def index_channel(
        self,
        channel_id: str,
        channel_name: str
    ) -> int:
        """
        Index messages from a single channel.

        Fetches recent messages, generates embeddings, and stores them.

        Args:
            channel_id: The Slack channel ID
            channel_name: Human-readable channel name

        Returns:
            Number of messages indexed
        """
        logger.info(f"Indexing channel: #{channel_name} ({channel_id})")

        # Fetch messages from Slack
        messages = await self._fetch_messages(channel_id)

        if not messages:
            logger.debug(f"No messages to index in #{channel_name}")
            return 0

        # Filter and prepare messages
        prepared = self._prepare_messages(messages, channel_id, channel_name)

        if not prepared:
            logger.debug(f"No indexable messages in #{channel_name}")
            return 0

        # Generate embeddings in batch
        contents = [m["content"] for m in prepared]
        embeddings_list = await self.embeddings.generate_batch(contents)

        # Create and store documents
        documents = []
        for msg, embedding in zip(prepared, embeddings_list):
            doc = VectorDocument(
                id=msg["id"],
                content=msg["content"],
                embedding=embedding,
                metadata=msg["metadata"]
            )
            documents.append(doc)

        self.vectorstore.add_batch(documents)

        logger.info(f"Indexed {len(documents)} messages from #{channel_name}")
        return len(documents)

    async def _fetch_messages(
        self,
        channel_id: str
    ) -> list[dict]:
        """
        Fetch recent messages from a channel.

        Args:
            channel_id: The Slack channel ID

        Returns:
            List of message dictionaries from Slack API
        """
        try:
            # Use conversations.history to get recent messages
            response = await self.slack_client.conversations_history(
                channel=channel_id,
                limit=self.messages_per_channel
            )

            if not response["ok"]:
                logger.error(f"Failed to fetch messages: {response.get('error')}")
                return []

            return response.get("messages", [])

        except Exception as e:
            logger.error(f"Error fetching messages from {channel_id}", e)
            return []

    def _prepare_messages(
        self,
        messages: list[dict],
        channel_id: str,
        channel_name: str
    ) -> list[dict]:
        """
        Prepare messages for indexing.

        Filters out short messages, system messages, and formats the content.

        Args:
            messages: Raw messages from Slack API
            channel_id: The channel ID
            channel_name: The channel name

        Returns:
            List of prepared message dicts ready for embedding
        """
        prepared = []

        for msg in messages:
            # Skip system messages (subtype indicates special message types)
            if msg.get("subtype"):
                continue

            # Get the message text
            text = msg.get("text", "")

            # Skip very short messages
            if len(text) < self.min_message_length:
                continue

            # Skip messages that are just links or mentions
            if text.startswith("<") and text.endswith(">"):
                continue

            # Create unique ID from channel and timestamp
            msg_ts = msg.get("ts", "")
            doc_id = f"{channel_id}_{msg_ts}"

            # Format timestamp for display
            try:
                ts_float = float(msg_ts)
                timestamp = datetime.fromtimestamp(ts_float).isoformat()
            except (ValueError, TypeError):
                timestamp = msg_ts

            prepared.append({
                "id": doc_id,
                "content": text,
                "metadata": {
                    "channel": channel_id,
                    "channel_name": channel_name,
                    "author": msg.get("user", "unknown"),
                    "timestamp": timestamp,
                    "ts": msg_ts,  # Original Slack timestamp
                }
            })

        return prepared

    async def index_multiple(
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
        results = {}

        for channel in channels:
            channel_id = channel.get("id")
            channel_name = channel.get("name", "unknown")

            if not channel_id:
                continue

            try:
                count = await self.index_channel(channel_id, channel_name)
                results[channel_id] = count
            except Exception as e:
                logger.error(f"Error indexing channel {channel_name}", e)
                results[channel_id] = 0

        total = sum(results.values())
        logger.info(f"Indexed {total} messages across {len(channels)} channels")

        return results

    async def get_indexable_channels(self) -> list[dict]:
        """
        Get list of channels the bot can index.

        Returns channels the bot is a member of.

        Returns:
            List of channel dicts with 'id' and 'name'
        """
        try:
            # Get channels the bot is a member of
            response = await self.slack_client.conversations_list(
                types="public_channel,private_channel",
                exclude_archived=True,
                limit=100
            )

            if not response["ok"]:
                logger.error(f"Failed to list channels: {response.get('error')}")
                return []

            channels = []
            for channel in response.get("channels", []):
                # Only include channels we're a member of
                if channel.get("is_member"):
                    channels.append({
                        "id": channel["id"],
                        "name": channel["name"]
                    })

            return channels

        except Exception as e:
            logger.error("Error listing channels", e)
            return []
