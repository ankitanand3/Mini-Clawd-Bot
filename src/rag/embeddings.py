"""
Embedding Generation
====================

Generates vector embeddings from text using OpenAI's embedding models.

What are embeddings?
- A vector (list of numbers) that represents the meaning of text
- Texts with similar meanings have similar vectors
- Enables semantic search (finding similar content by meaning)

How it works:
1. Send text to OpenAI's embedding API
2. Receive a vector (e.g., 1536 dimensions for text-embedding-3-small)
3. Store the vector alongside the original text
4. Compare vectors using cosine similarity to find similar texts

Example:
    "How do I reset my password?" → [0.02, -0.15, 0.89, ...]
    "I forgot my login credentials" → [0.03, -0.14, 0.87, ...]
    These vectors would be very similar (high cosine similarity)

Caching:
    Embeddings are cached to avoid repeated API calls for the same text.
    This saves money and speeds up repeated queries.
"""

import hashlib
from typing import Sequence

from openai import AsyncOpenAI

from src.utils.logger import Logger

logger = Logger("Embeddings")


class EmbeddingGenerator:
    """
    Generates text embeddings using OpenAI's API.

    Features:
    - Async embedding generation
    - Simple in-memory caching
    - Batch embedding for efficiency

    Example:
        generator = EmbeddingGenerator(api_key="sk-...", model="text-embedding-3-small")

        # Single text
        vector = await generator.generate("How do I use this feature?")

        # Multiple texts (more efficient)
        vectors = await generator.generate_batch([
            "First message",
            "Second message",
            "Third message"
        ])
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small"
    ):
        """
        Initialize the embedding generator.

        Args:
            api_key: OpenAI API key
            model: Embedding model to use
        """
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

        # Simple in-memory cache
        # Key: hash of text, Value: embedding vector
        self._cache: dict[str, list[float]] = {}

        logger.info(f"Embedding generator initialized with model: {model}")

    def _hash_text(self, text: str) -> str:
        """Create a hash key for caching."""
        return hashlib.md5(text.encode()).hexdigest()

    async def generate(self, text: str) -> list[float]:
        """
        Generate an embedding for a single text.

        Args:
            text: The text to embed

        Returns:
            Vector embedding as a list of floats
        """
        # Check cache first
        cache_key = self._hash_text(text)
        if cache_key in self._cache:
            logger.debug("Embedding cache hit")
            return self._cache[cache_key]

        # Generate embedding via API
        response = await self.client.embeddings.create(
            model=self.model,
            input=text
        )

        embedding = response.data[0].embedding

        # Cache the result
        self._cache[cache_key] = embedding

        logger.debug(f"Generated embedding (dim={len(embedding)})")
        return embedding

    async def generate_batch(
        self,
        texts: Sequence[str]
    ) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.

        More efficient than calling generate() multiple times because
        it batches the API call.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors (same order as input)
        """
        if not texts:
            return []

        # Check which texts need to be generated (not in cache)
        results: list[list[float] | None] = []
        texts_to_generate: list[tuple[int, str]] = []

        for i, text in enumerate(texts):
            cache_key = self._hash_text(text)
            if cache_key in self._cache:
                results.append(self._cache[cache_key])
            else:
                results.append(None)  # Placeholder
                texts_to_generate.append((i, text))

        # If all were cached, return immediately
        if not texts_to_generate:
            logger.debug(f"All {len(texts)} embeddings found in cache")
            return [r for r in results if r is not None]

        # Generate embeddings for uncached texts
        uncached_texts = [t[1] for t in texts_to_generate]

        logger.debug(f"Generating {len(uncached_texts)} embeddings (batch)")

        response = await self.client.embeddings.create(
            model=self.model,
            input=uncached_texts
        )

        # Fill in results and cache
        for j, embedding_data in enumerate(response.data):
            original_index = texts_to_generate[j][0]
            text = texts_to_generate[j][1]
            embedding = embedding_data.embedding

            results[original_index] = embedding

            # Cache it
            cache_key = self._hash_text(text)
            self._cache[cache_key] = embedding

        # Filter out None (shouldn't happen, but type safety)
        return [r for r in results if r is not None]

    def clear_cache(self) -> None:
        """Clear the embedding cache."""
        self._cache.clear()
        logger.info("Embedding cache cleared")

    def get_cache_size(self) -> int:
        """Get the number of cached embeddings."""
        return len(self._cache)

    @property
    def dimension(self) -> int:
        """
        Get the dimension of embeddings from this model.

        Returns:
            The embedding dimension (e.g., 1536 for text-embedding-3-small)
        """
        # Known dimensions for OpenAI models
        dimensions = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        return dimensions.get(self.model, 1536)
