"""
Vector Database Module - Using Qdrant for Fast Semantic Search

This module manages persistent vector storage for the RAG system.
Qdrant is a high-performance vector database designed for semantic search.

Key Concepts:
- Collections: Like tables in SQL, store vectors with metadata
- Vectors: 3,072-dimensional representations of text (embeddings)
- Payloads: Metadata stored alongside vectors (source file, original text)
- Distance Metric: COSINE measures angle between vectors (perfect for semantic similarity)

Why Qdrant?
- Fast: Optimized for vector similarity search at scale
- Local: Runs on your machine with Docker (no cloud dependency)
- Persistent: Data survives application restarts
- Scalable: Can handle millions of vectors

Data Flow:
1. PDF chunks are embedded (text → 3,072 floats)
2. Stored in Qdrant with metadata (source filename, original text)
3. When user asks question:
   - Question is embedded using same model
   - Search finds most similar vectors (cosine similarity)
   - Return top_k matching chunks + their sources
"""

from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct


class QdrantStorage:
    """
    Manages vector storage and retrieval using Qdrant vector database.
    
    This class provides the interface between the RAG pipeline and Qdrant.
    Handles:
    - Connection management to Qdrant server
    - Collection creation and initialization
    - Upserting (inserting/updating) vectors with metadata
    - Semantic search for similar vectors
    
    The collection uses:
    - Vector size: 3,072 dimensions (text-embedding-3-large model)
    - Distance metric: COSINE (measures angle between vectors)
    - Payloads: {"source": filename, "text": original_chunk}
    """

    def __init__(self, url="http://localhost:6333", collection="docs", dim=3072):
        """
        Initialize Qdrant client and ensure collection exists.
        
        Sets up connection to Qdrant server and creates the collection
        if it doesn't already exist. The collection is configured for
        semantic search using cosine distance.
        
        Args:
            url (str): Qdrant server URL (default: localhost:6333)
                      Should match Docker port mapping
            collection (str): Collection name (default: "docs")
                             Like a table name in SQL databases
            dim (int): Vector dimensions (default: 3072)
                      Must match embedding model dimensions
                      text-embedding-3-large uses 3,072 dimensions
        
        Example:
            >>> storage = QdrantStorage()
            >>> storage = QdrantStorage(url="http://localhost:6333", collection="documents")
        """
        # Connect to Qdrant server with 30-second timeout
        self.client = QdrantClient(url=url, timeout=30)
        self.collection = collection
        
        # Create collection if it doesn't exist
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=dim,  # Vector dimensions
                    distance=Distance.COSINE  # Similarity metric
                ),
            )

    def upsert(self, ids: list, vectors: list[list[float]], payloads: list[dict]) -> None:
        """
        Insert or update vectors into the database.
        
        "Upsert" = insert if new, update if already exists (by ID).
        
        This stores both the embedding vectors and their associated metadata.
        Used in the "embed-and-upsert" step of PDF ingestion.
        
        Args:
            ids (list): Unique identifiers for each vector/chunk
                       Format: UUID strings (uuid.uuid5 based on source:position)
                       Example: ["550e8400-e29b-41d4-a716-446655440000", ...]
            vectors (list[list[float]]): Embedding vectors to store
                                        Each vector has 3,072 floats
                                        Generated from OpenAI embeddings
            payloads (list[dict]): Metadata for each vector
                                  Format: {"source": "filename.pdf", "text": "chunk text"}
                                  Source: original PDF filename
                                  Text: original text chunk (for context retrieval)
        
        Example:
            >>> ids = ["uuid1", "uuid2", "uuid3"]
            >>> vectors = [[...3072 floats...], [...], [...]]
            >>> payloads = [
            ...     {"source": "policy.pdf", "text": "Chapter 1..."},
            ...     {"source": "policy.pdf", "text": "Chapter 2..."},
            ...     {"source": "policy.pdf", "text": "Chapter 3..."}
            ... ]
            >>> storage.upsert(ids, vectors, payloads)
        """
        # Create PointStruct objects combining ID, vector, and payload
        points = [
            PointStruct(
                id=ids[i],
                vector=vectors[i],
                payload=payloads[i]
            )
            for i in range(len(ids))
        ]
        
        # Upsert into Qdrant collection
        # If ID exists, it updates; otherwise it inserts
        self.client.upsert(self.collection, points=points)

    def search(self, query_vector: list[float], top_k: int = 5) -> dict:
        """
        Search for similar vectors and return matching documents.
        
        Performs semantic similarity search by finding vectors closest
        to the query vector in vector space.
        
        Used in the "embed-and-search" step of query processing.
        
        Semantic Search Process:
        1. Compare query vector against all stored vectors
        2. Use cosine similarity to find closest matches
        3. Return top_k results with highest similarity scores
        4. Extract text and sources from payloads
        5. Return to LLM for answer generation
        
        Args:
            query_vector (list[float]): Embedded query as 3,072-dimensional vector
                                       Generated from user's question using same
                                       embedding model as document chunks
            top_k (int): Number of results to return (default: 5)
                        Limits returned chunks for LLM context window
                        Higher k = more context but more tokens
        
        Returns:
            dict: Search results containing:
                - 'contexts' (list[str]): Top matching text chunks
                                         Ranked by relevance (most similar first)
                - 'sources' (list[str]): Source files for these chunks
                                        Used to cite sources in answer
        
        Example:
            >>> query_vec = [0.1, 0.2, ..., 0.3]  # 3,072 floats
            >>> results = storage.search(query_vec, top_k=5)
            >>> results['contexts']
            ["Chapter 1 discusses...", "Section 2.1 states...", ...]
            >>> results['sources']
            ["policy.pdf", "guidelines.pdf"]
        
        Note:
            - Cosine similarity: measures angle between vectors
            - Result order: most similar first (ranked by similarity score)
            - Payloads included: enables retrieval of original text
        """
        # Query Qdrant for similar vectors
        results = self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            with_payload=True,  # Include metadata (source, text)
            limit=top_k
        )
        
        # Extract text chunks and sources from results
        contexts = []
        sources = set()  # Use set to avoid duplicate sources

        for r in results.points:
            payload = r.payload or {}
            text = payload.get("text", "")
            source = payload.get("source", "")
            if text:
                contexts.append(text)
                sources.add(source)

        return {"contexts": contexts, "sources": list(sources)}
