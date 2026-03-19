"""
PDF Data Processing Module - Phase 2 of the RAG Pipeline

This module handles the initial data preparation for RAG:
1. Loading PDFs from disk
2. Chunking text into manageable pieces
3. Converting chunks to vector embeddings

Why This Matters:
- PDFs can be thousands of pages, too large for LLM context windows
- Chunking splits documents into ~1000 char pieces for relevance
- Embeddings convert text to 3,072-dimensional vectors for similarity search
- Same embedding model used for questions and documents ensures consistency

Configuration:
- chunk_size=1000: Each chunk ~1000 characters (~200-250 words)
- chunk_overlap=200: Overlap between chunks preserves cross-chunk concepts
- embedding_model: text-embedding-3-large (3,072 dimensions)

Flow:
PDF File → PDFReader → Extract Text → SentenceSplitter → Text Chunks → OpenAI API → Embeddings
"""

from dotenv import load_dotenv
from llama_index.core.node_parser import SentenceSplitter
from llama_index.readers.file import PDFReader
from openai import OpenAI

# Load environment variables (including OPENAI_API_KEY)
load_dotenv()

# Initialize OpenAI client for embedding generation
client = OpenAI()

# Embedding model configuration
# text-embedding-3-large: 3,072 dimensional embeddings, excellent for semantic search
EMBED_MODEL = "text-embedding-3-large"
EMBED_DIM = 3072  # Fixed dimension size for this model

# Configure text splitter for document chunking
# - chunk_size=1000: Each chunk is approximately 1000 characters
# - chunk_overlap=200: 200 character overlap between chunks
# Overlap preserves context when concepts span multiple chunks
splitter = SentenceSplitter(chunk_size=1000, chunk_overlap=200)


def load_and_chunk_pdf(path: str) -> list[str]:
    """
    Load a PDF file and split it into manageable text chunks.
    
    Part of Phase 2: Data Processing
    This is the first step in the "load-and-chunk" Inngest step.
    
    Why Chunking?
    - PDFs can have 10,000+ pages
    - LLMs have token limits (context windows)
    - Smaller chunks improve semantic search relevance
    - Overlap preserves context across chunk boundaries
    
    Args:
        path (str): File path to the PDF document
                   Must be an absolute path to the PDF file
    
    Returns:
        list[str]: List of text chunks extracted from the PDF
                  Each chunk is approximately 1000 characters
                  Chunks are extracted in document order
    
    Raises:
        FileNotFoundError: If PDF file doesn't exist at the path
        PDFReadError: If PDF is corrupted or unreadable
    
    Example:
        >>> chunks = load_and_chunk_pdf('uploads/policy.pdf')
        >>> len(chunks)
        42
        >>> len(chunks[0])
        1005
    """
    # Use LlamaIndex PDFReader to reliably extract text from PDFs
    # Handles various PDF formats and encodings automatically
    docs = PDFReader().load_data(file=path)
    
    # Extract text content from loaded documents
    # Filter out any documents without text content
    texts = [d.text for d in docs if getattr(d, "text", None)]
    
    # Split each document's text into chunks
    # SentenceSplitter respects sentence boundaries for better context
    chunks = []
    for t in texts:
        chunks.extend(splitter.split_text(t))
    
    return chunks


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Convert text chunks into vector embeddings using OpenAI API.
    
    Part of Phase 2: Data Processing
    This is the second part of the "embed-and-upsert" Inngest step.
    
    What are Embeddings?
    - Convert text to a list of 3,072 numbers (coordinates in 3,072D space)
    - Similar text produces similar embeddings (nearby in vector space)
    - Used for semantic search: find meaning-based matches, not keyword matches
    - Same model for questions and documents ensures compatibility
    
    How It Works:
    1. Send text chunks to OpenAI Embeddings API
    2. API returns 3,072-dimensional vectors for each text
    3. Vectors stored in Qdrant for fast similarity search
    4. When user asks question, question is embedded same way
    5. Find vectors closest to question vector (cosine similarity)
    
    Args:
        texts (list[str]): List of text chunks to embed
                          Can be document chunks or a question
                          API batches multiple texts efficiently
    
    Returns:
        list[list[float]]: List of embedding vectors
                          Each vector has 3,072 float values
                          Order matches input texts list
    
    Example:
        >>> chunks = ['The policy covers...', 'Section 2 discusses...']
        >>> embeddings = embed_texts(chunks)
        >>> len(embeddings)
        2
        >>> len(embeddings[0])
        3072
    
    Note:
        - Uses text-embedding-3-large model (excellent for semantic search)
        - OpenAI API batches requests internally (no manual batching needed)
        - Each embedding costs approximately $0.00002 per 1K tokens
        - First request might have higher latency
    """
    # Call OpenAI Embeddings API
    # Converts text to 3,072-dimensional vectors
    response = client.embeddings.create(
        model=EMBED_MODEL,
        input=texts,  # Can be a single string or list of strings
    )
    
    # Extract embedding vectors from response
    # Each embedding is a list of 3,072 float values
    return [item.embedding for item in response.data]
