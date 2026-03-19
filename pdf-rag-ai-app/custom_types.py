"""
Custom data types for the RAG (Retrieval Augmented Generation) pipeline.

This module defines Pydantic models for type safety and validation across
the application. These models ensure data consistency between different
components of the RAG system:

1. PDF Ingestion Flow: PDF chunks flow through the system as RAGChunkAndSrc
2. Vector Storage: Results come back as RAGUpsertResult
3. Vector Search: Retrieved documents as RAGSearchResult
4. LLM Query: Final answer formatted as RAGQueryResult

Using Pydantic models provides:
- Type validation at runtime
- Clear API contracts between functions
- Helpful error messages if data is invalid
- Easy serialization/deserialization
"""
import pydantic


class RAGChunkAndSrc(pydantic.BaseModel):
    """
    Represents chunked PDF data with source information.
    
    Used internally to pass data between Inngest function steps.
    
    Attributes:
        chunks (list[str]): List of text chunks extracted from PDF
                           Each chunk is ~1000 characters (~200-250 words)
        source_id (str | None): Name/identifier of the source PDF file
                               Used to track which document chunks came from
    """
    chunks: list[str]
    source_id: str | None = None


class RAGUpsertResult(pydantic.BaseModel):
    """
    Result of inserting vectors into the Qdrant database.
    
    Returned after the "embed-and-upsert" step in PDF ingestion.
    
    Attributes:
        ingested (int): Number of text chunks successfully converted to vectors
                       and stored in the vector database
    """
    ingested: int


class RAGSearchResult(pydantic.BaseModel):
    """
    Result of searching the vector database for similar documents.
    
    Returned after the "embed-and-search" step when processing a question.
    
    Attributes:
        contexts (list[str]): List of text chunks matching the query
                             Retrieved via semantic similarity (cosine distance)
                             Ranked by relevance (most similar first)
        sources (list[str]): List of source file names these chunks came from
                            Allows users to verify and trace information
    """
    contexts: list[str]
    sources: list[str]


class RAGQueryResult(pydantic.BaseModel):
    """
    Final answer from the complete RAG pipeline.
    
    Returned by the rag_query_pdf_ai Inngest function.
    Displayed to the user in the Streamlit UI.
    
    Attributes:
        answer (str): Generated answer from GPT-4o-mini
                     Based on retrieved context chunks
                     Factual (temperature=0.2) to reduce hallucinations
        sources (list[str]): Document files used to generate the answer
                            Provides transparency and traceability
        num_contexts (int): Number of context chunks retrieved and used
                           Indicates confidence (more context = better grounding)
    """
    answer: str
    sources: list[str]
    num_contexts: int
