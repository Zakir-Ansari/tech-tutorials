"""
FastAPI Backend with Inngest Orchestration - Phase 4 of RAG Pipeline

This module is the core of the RAG application, implementing:
1. Two Inngest functions for PDF ingestion and query processing
2. Event-driven architecture with built-in reliability
3. Automatic retries for failed steps
4. Observable execution with Inngest dashboard

Architecture:
- Inngest Client: Manages event routing, retries, and orchestration
- Function 1 (rag_ingest_pdf): Handles PDF upload and vector storage
- Function 2 (rag_query_pdf_ai): Processes user questions and generates answers
- FastAPI: Serves Inngest functions at /api/inngest endpoint

Why Inngest?
- Event-Driven: Functions triggered by events (PDF upload, user query)
- Reliable: Automatic retries (up to 5 times) for transient failures
- Observable: Dashboard shows every step, timing, logs, and errors
- Durable: Survives crashes, restarts, and handles state management

Data Flow:
Streamlit → Inngest Event → Route to Function → Multi-Step Execution → Result → Streamlit

Each function has multiple steps that are tracked independently.
If a step fails, it retries automatically before giving up.
"""

import logging
import os
import uuid

import inngest.fast_api
from dotenv import load_dotenv
from fastapi import FastAPI
from inngest import Inngest, TriggerEvent, Context, PydanticSerializer
from inngest.experimental import ai

from custom_types import RAGUpsertResult, RAGChunkAndSrc, RAGSearchResult
from data_loader import load_and_chunk_pdf, embed_texts
from vector_db import QdrantStorage

# Load environment variables from .env file (including OPENAI_API_KEY)
load_dotenv()

# ============================================================================
# INNGEST CLIENT SETUP
# ============================================================================
# Inngest orchestrates the entire RAG pipeline with:
# - Event routing: Which function to call for each event type
# - Automatic retries: 5 attempts by default for failed steps
# - Step tracking: Monitor each step separately with timing
# - Observability: Dashboard shows all executions, errors, and logs
# - Durable execution: Survives crashes and restarts

inngest_client = Inngest(
    app_id="rag_app",  # Unique ID for your application
    logger=logging.getLogger("uvicorn"),  # Use uvicorn's logger for consistency
    is_production=False,  # Development mode (no authentication required)
    serializer=PydanticSerializer(),  # Use Pydantic for type validation
)

# ============================================================================
# FUNCTION 1: INGEST PDF
# ============================================================================
# Handles complete PDF ingestion pipeline:
# 1. Load PDF from disk
# 2. Split into chunks
# 3. Generate embeddings
# 4. Store in vector database
#
# Inngest tracks:
# - Step: "load-and-chunk" - PDF loading and text splitting
# - Step: "embed-and-upsert" - Vector generation and storage
# - Retries: If either step fails, Inngest retries automatically


@inngest_client.create_function(
    fn_id="RAG: Ingest PDF",
    trigger=TriggerEvent(event="rag/ingest_pdf")
)
async def rag_ingest_pdf(ctx: Context):
    """
    Orchestrated PDF ingestion function.
    
    Part of Phase 4: Backend Implementation
    Triggered by: "rag/ingest_pdf" event from Streamlit UI
    
    Expected event data:
    {
        "pdf_path": "/path/to/file.pdf",
        "source_id": "optional_source_name"
    }
    
    Process:
    1. Load and chunk PDF → returns chunks list
    2. Embed chunks and store in Qdrant → returns ingestion count
    3. Inngest tracks each step with retries on failure
    
    Returns:
        dict: {"ingested": number_of_chunks}
    
    Note:
        - Each step is retried up to 5 times if it fails
        - Inngest dashboard shows step execution timing and logs
        - Idempotent: Safe to run multiple times with same PDF
    """
    def _load(ctx: Context) -> RAGChunkAndSrc:
        """
        Step 1: Load and chunk the PDF
        
        Extracts text from PDF file and splits into manageable chunks.
        Chunk configuration:
        - Size: ~1000 characters (~200-250 words)
        - Overlap: 200 characters (preserves cross-chunk context)
        """
        pdf_path = ctx.event.data["pdf_path"]
        source_id = ctx.event.data.get("source_id", pdf_path)
        chunks = load_and_chunk_pdf(pdf_path)
        return RAGChunkAndSrc(chunks=chunks, source_id=source_id)

    def _upsert(chunks_and_src: RAGChunkAndSrc) -> RAGUpsertResult:
        """
        Step 2: Embed chunks and store in database
        
        Process:
        1. Convert each chunk to 3,072-dimensional vector (embedding)
        2. Generate unique IDs for each chunk
        3. Create payloads with source and text
        4. Store in Qdrant for fast similarity search
        """
        chunks = chunks_and_src.chunks
        source_id = chunks_and_src.source_id

        # Generate embeddings for all chunks using OpenAI API
        # API handles batching internally for efficiency
        vecs = embed_texts(chunks)

        # Create unique IDs for each chunk
        # Format: UUID based on source name + position
        # Ensures same file produces same IDs (idempotent)
        ids = [
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}:{i}"))
            for i in range(len(chunks))
        ]

        # Create payloads (metadata) for each vector
        # Stored alongside vectors in Qdrant for context retrieval
        payloads = [
            {"source": source_id, "text": chunks[i]}
            for i in range(len(chunks))
        ]

        # Store in Qdrant vector database
        QdrantStorage().upsert(ids, vecs, payloads)
        return RAGUpsertResult(ingested=len(chunks))

    # Execute steps with Inngest's step.run()
    # This provides:
    # - Retry logic: automatically retries on failure
    # - Execution tracking: each step is tracked in dashboard
    # - Type safety: output types are validated

    chunks_and_src = await ctx.step.run(
        "load-and-chunk",
        lambda: _load(ctx),
        output_type=RAGChunkAndSrc
    )

    ingested = await ctx.step.run(
        "embed-and-upsert",
        lambda: _upsert(chunks_and_src),
        output_type=RAGUpsertResult
    )

    return ingested.model_dump()


# ============================================================================
# FUNCTION 2: QUERY PDF WITH AI
# ============================================================================
# Handles complete RAG pipeline:
# 1. Embed the question
# 2. Search for relevant documents
# 3. Send to LLM with context
# 4. Return answer with sources
#
# Inngest tracks:
# - Step: "embed-and-search" - Question embedding and vector search
# - Step: "llm-answer" - LLM call for answer generation
# - Retries: Automatic retry on failures


@inngest_client.create_function(
    fn_id="RAG: Query PDF",
    trigger=TriggerEvent(event="rag/query_pdf_ai")
)
async def rag_query_pdf_ai(ctx: Context):
    """
    Orchestrated RAG query function.
    
    Part of Phase 4: Backend Implementation
    Triggered by: "rag/query_pdf_ai" event from Streamlit UI
    
    Expected event data:
    {
        "question": "Your question here",
        "top_k": 5  # Optional: number of results to retrieve
    }
    
    Process:
    1. Embed question using same model as documents
    2. Search Qdrant for similar vectors
    3. Build augmented prompt with context chunks
    4. Send to GPT-4o-mini for answer generation
    5. Return answer with sources
    
    Returns:
        dict: {
            "answer": "Generated answer",
            "sources": ["file1.pdf", "file2.pdf"],
            "num_contexts": 3
        }
    """

    def _search(question: str, top_k: int = 5) -> RAGSearchResult:
        """
        Step 1: Search vector database for relevant chunks
        
        Process:
        1. Embed the question (same model as documents)
        2. Search Qdrant for top_k most similar vectors
        3. Return matching text chunks and their sources
        
        Why same embedding model?
        - Ensures question and documents are comparable
        - Same 3,072-dimensional space
        - Cosine similarity produces meaningful results
        """
        # Embed question using OpenAI API (same model as documents)
        query_vec = embed_texts([question])[0]

        # Search Qdrant for similar vectors
        store = QdrantStorage()
        found = store.search(query_vec, top_k)

        return RAGSearchResult(contexts=found["contexts"], sources=found["sources"])

    # Extract data from event
    question = ctx.event.data["question"]
    top_k = int(ctx.event.data.get("top_k", 5))

    # Step 1: Search for relevant context
    found = await ctx.step.run(
        "embed-and-search",
        lambda: _search(question, top_k),
        output_type=RAGSearchResult
    )

    # Step 2: Prepare augmented prompt
    # This is the core of RAG: provide LLM with retrieved context
    # so it can generate accurate, grounded answers

    # Format retrieved chunks into structured context block
    context_block = "\n\n".join(f"- {c}" for c in found.contexts)

    # Create the augmented prompt combining:
    # 1. System instruction (how to behave)
    # 2. Retrieved context chunks
    # 3. Original user question
    user_content = (
        "Use the following context to answer the question.\n\n"
        f"Context:\n{context_block}\n\n"
        f"Question: {question}\n"
        "Answer concisely using the context above. "
        "If the answer is not in the context, say you don't know."
    )

    # Step 3: Send to LLM
    # Use Inngest's AI adapter for proper error handling and retries
    adapter = ai.openai.Adapter(
        auth_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-mini"  # Fast, cost-effective model
    )

    res = await ctx.step.ai.infer(
        "llm-answer",
        adapter=adapter,
        body={
            "max_tokens": 1024,  # Limit response length
            "temperature": 0.2,  # Lower = more factual, less creative
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful assistant that answers questions using only the provided context."
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ]
        }
    )

    # Extract and return the answer
    answer = res["choices"][0]["message"]["content"].strip()
    return {
        "answer": answer,
        "sources": found.sources,
        "num_contexts": len(found.contexts)
    }


# ============================================================================
# FASTAPI SETUP
# ============================================================================

app = FastAPI(
    title="RAG AI Agent",
    description="Production-ready PDF RAG application with Inngest orchestration"
)

# Serve Inngest functions through FastAPI
# This exposes the functions at /api/inngest endpoint
# Inngest SDK handles all the HTTP routing and event processing
inngest.fast_api.serve(app, inngest_client, [rag_ingest_pdf, rag_query_pdf_ai])


@app.get("/health")
def health_check():
    """
    Simple health check endpoint for monitoring.
    
    Returns:
        dict: {"status": "healthy"} if service is running
    """
    return {"status": "healthy"}
