"""
Vector Store
============

A simple file-based vector database for storing and searching embeddings.

Why build our own instead of using Pinecone/Weaviate/ChromaDB?
1. Educational - understand how vector search works
2. No external dependencies - runs entirely locally
3. Sufficient for moderate scale (thousands of documents)
4. Easy to inspect and debug (just JSON files)

For production at scale, consider:
- Pinecone: Managed vector database
- Weaviate: Open-source, feature-rich
- ChromaDB: Simple, Python-native
- pgvector: PostgreSQL extension

How Vector Search Works:
1. Store documents with their embedding vectors
2. When searching, compute cosine similarity between query and all stored vectors
3. Return the top-k most similar documents

Cosine Similarity:
    cos(A, B) = (A · B) / (||A|| * ||B||)
    - Returns a value from -1 to 1
    - 1 means identical direction (most similar)
    - 0 means perpendicular (unrelated)
    - -1 means opposite direction
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import numpy as np

from src.utils.logger import Logger

logger = Logger("VectorStore")


@dataclass
class VectorDocument:
    """
    A document stored in the vector store.

    Attributes:
        id: Unique identifier for the document
        content: The original text content
        embedding: The vector embedding
        metadata: Additional data (channel, author, timestamp, etc.)
        score: Similarity score (set during search)
    """
    id: str
    content: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "content": self.content,
            "embedding": self.embedding,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VectorDocument":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            content=data["content"],
            embedding=data["embedding"],
            metadata=data.get("metadata", {}),
        )


class VectorStore:
    """
    File-based vector store with cosine similarity search.

    The store maintains an in-memory index for fast search while
    persisting to disk for durability.

    Data is stored in two files:
    - documents.json: Document content and metadata
    - embeddings.npy: Numpy array of embeddings (more efficient)

    Example:
        store = VectorStore(Path("data/vectorstore"))

        # Add documents
        store.add(VectorDocument(
            id="msg_123",
            content="The API is returning 500 errors",
            embedding=[0.1, -0.2, ...],
            metadata={"channel": "C123", "author": "U456"}
        ))

        # Search
        query_embedding = [0.15, -0.18, ...]
        results = store.search(query_embedding, top_k=5)
    """

    def __init__(self, storage_path: Path):
        """
        Initialize the vector store.

        Args:
            storage_path: Directory to store data files
        """
        self.storage_path = storage_path
        self.documents_file = storage_path / "documents.json"
        self.embeddings_file = storage_path / "embeddings.npy"

        # In-memory index
        self._documents: dict[str, VectorDocument] = {}
        self._embeddings: np.ndarray | None = None
        self._id_to_index: dict[str, int] = {}

        # Ensure directory exists
        storage_path.mkdir(parents=True, exist_ok=True)

        # Load existing data
        self._load()

        logger.info(f"Vector store initialized with {len(self._documents)} documents")

    def _load(self) -> None:
        """Load existing data from disk."""
        if not self.documents_file.exists():
            return

        try:
            # Load documents
            with open(self.documents_file) as f:
                docs_data = json.load(f)

            for i, doc_data in enumerate(docs_data):
                doc = VectorDocument.from_dict(doc_data)
                self._documents[doc.id] = doc
                self._id_to_index[doc.id] = i

            # Load embeddings if available
            if self.embeddings_file.exists():
                self._embeddings = np.load(self.embeddings_file)

            logger.debug(f"Loaded {len(self._documents)} documents from disk")

        except Exception as e:
            logger.error(f"Error loading vector store: {e}")

    def _save(self) -> None:
        """Save data to disk."""
        try:
            # Save documents
            docs_list = [doc.to_dict() for doc in self._documents.values()]
            with open(self.documents_file, "w") as f:
                json.dump(docs_list, f)

            # Save embeddings as numpy array (more efficient)
            if self._embeddings is not None:
                np.save(self.embeddings_file, self._embeddings)

            logger.debug(f"Saved {len(self._documents)} documents to disk")

        except Exception as e:
            logger.error(f"Error saving vector store: {e}")

    def add(self, document: VectorDocument) -> None:
        """
        Add a document to the store.

        If a document with the same ID exists, it will be replaced.

        Args:
            document: The document to add
        """
        # Check if this is an update
        is_update = document.id in self._documents

        # Add to documents dict
        self._documents[document.id] = document

        # Update embeddings array
        embedding = np.array(document.embedding)

        if self._embeddings is None:
            # First document
            self._embeddings = embedding.reshape(1, -1)
            self._id_to_index[document.id] = 0
        elif is_update:
            # Update existing
            idx = self._id_to_index[document.id]
            self._embeddings[idx] = embedding
        else:
            # Append new
            self._embeddings = np.vstack([self._embeddings, embedding])
            self._id_to_index[document.id] = len(self._embeddings) - 1

    def add_batch(self, documents: list[VectorDocument]) -> None:
        """
        Add multiple documents efficiently.

        Args:
            documents: List of documents to add
        """
        for doc in documents:
            self.add(doc)

        # Save after batch
        self._save()
        logger.debug(f"Added batch of {len(documents)} documents")

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filter_metadata: dict[str, Any] | None = None
    ) -> list[VectorDocument]:
        """
        Search for similar documents.

        Uses cosine similarity to find documents with similar embeddings.

        Args:
            query_vector: The query embedding
            top_k: Number of results to return
            filter_metadata: Optional metadata filters (e.g., {"channel": "C123"})

        Returns:
            List of VectorDocuments sorted by similarity (highest first)
        """
        if self._embeddings is None or len(self._documents) == 0:
            return []

        # Convert query to numpy array
        query = np.array(query_vector)

        # Compute cosine similarities
        # cos_sim = (A · B) / (||A|| * ||B||)
        query_norm = np.linalg.norm(query)
        doc_norms = np.linalg.norm(self._embeddings, axis=1)

        # Avoid division by zero
        doc_norms = np.where(doc_norms == 0, 1, doc_norms)

        similarities = np.dot(self._embeddings, query) / (doc_norms * query_norm)

        # Create list of (doc_id, similarity) tuples
        id_list = list(self._id_to_index.keys())
        results: list[tuple[str, float]] = [
            (id_list[i], float(similarities[i]))
            for i in range(len(similarities))
        ]

        # Apply metadata filters
        if filter_metadata:
            filtered_results = []
            for doc_id, score in results:
                doc = self._documents[doc_id]
                # Check if all filter conditions match
                matches = all(
                    doc.metadata.get(k) == v
                    for k, v in filter_metadata.items()
                    if v is not None
                )
                if matches:
                    filtered_results.append((doc_id, score))
            results = filtered_results

        # Sort by similarity (descending)
        results.sort(key=lambda x: x[1], reverse=True)

        # Return top_k documents with scores
        output = []
        for doc_id, score in results[:top_k]:
            doc = self._documents[doc_id]
            # Create a copy with the score
            doc_with_score = VectorDocument(
                id=doc.id,
                content=doc.content,
                embedding=doc.embedding,
                metadata=doc.metadata,
                score=score
            )
            output.append(doc_with_score)

        return output

    def delete(self, doc_id: str) -> bool:
        """
        Delete a document by ID.

        Args:
            doc_id: The document ID to delete

        Returns:
            True if the document was found and deleted
        """
        if doc_id not in self._documents:
            return False

        # Remove from documents
        del self._documents[doc_id]

        # Rebuild embeddings array (not the most efficient, but simple)
        self._rebuild_embeddings()

        self._save()
        return True

    def _rebuild_embeddings(self) -> None:
        """Rebuild the embeddings array from documents."""
        if not self._documents:
            self._embeddings = None
            self._id_to_index = {}
            return

        embeddings_list = []
        self._id_to_index = {}

        for i, (doc_id, doc) in enumerate(self._documents.items()):
            embeddings_list.append(doc.embedding)
            self._id_to_index[doc_id] = i

        self._embeddings = np.array(embeddings_list)

    def get(self, doc_id: str) -> VectorDocument | None:
        """Get a document by ID."""
        return self._documents.get(doc_id)

    def clear(self) -> None:
        """Clear all documents from the store."""
        self._documents.clear()
        self._embeddings = None
        self._id_to_index.clear()
        self._save()
        logger.info("Vector store cleared")

    def __len__(self) -> int:
        """Get the number of documents in the store."""
        return len(self._documents)
