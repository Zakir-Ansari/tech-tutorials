"""
Streamlit User Interface - Phase 5 of RAG Pipeline

This module provides the user-facing interface for the RAG system.
Built with Streamlit for rapid development with pure Python (no HTML/CSS/JS).

Two Main Sections:
1. PDF Upload Interface
   - Users select and upload PDF files
   - PDFs saved locally and ingestion event triggered
   - Inngest processes in background

2. Query Interface
   - Users ask questions about uploaded PDFs
   - Questions sent to Inngest as events
   - Results streamed back with sources

Architecture:
- Streamlit caches Inngest client for performance
- Events sent to FastAPI backend at localhost:8000/api/inngest
- Results polled from Inngest dev server at localhost:8288/v1
- All communication is HTTP/REST

Data Flow:
User Input → Streamlit → Inngest Event → FastAPI → Processing → Result → Display
"""

import os
import time
from pathlib import Path

import inngest
import requests
import streamlit as st
from dotenv import load_dotenv

# Load environment variables (OPENAI_API_KEY, etc.)
load_dotenv()

# Configure Streamlit page settings
st.set_page_config(
    page_title="RAG PDF Assistant",
    page_icon="📄",
    layout="centered"
)


@st.cache_resource
def get_inngest_client() -> inngest.Inngest:
    """
    Get or create cached Inngest client.
    
    Cache means this function runs only once per session.
    Improves performance by reusing the same client instance.
    
    Returns:
        inngest.Inngest: Client instance for sending events
    """
    return inngest.Inngest(app_id="rag_app", is_production=False)


def save_uploaded_pdf(file) -> Path:
    """
    Save uploaded PDF file to local uploads directory.
    
    Streamlit's file uploader returns a temporary file object.
    We save it locally so the backend FastAPI can access it.
    
    Args:
        file: Streamlit UploadedFile object
    
    Returns:
        Path: Path object to saved file (absolute path)
    
    Example:
        >>> uploaded_file = st.file_uploader("Choose PDF", type=["pdf"])
        >>> path = save_uploaded_pdf(uploaded_file)
        >>> print(path)
        /absolute/path/to/uploads/document.pdf
    """
    # Create uploads directory if it doesn't exist
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    
    # Construct file path
    file_path = uploads_dir / file.name
    
    # Get file bytes and write to disk
    file_bytes = file.getbuffer()
    file_path.write_bytes(file_bytes)
    
    return file_path


def send_rag_ingest_event(pdf_path: Path) -> None:
    """
    Trigger PDF ingestion through Inngest.
    
    Sends a "rag/ingest_pdf" event to Inngest which will:
    1. Trigger the rag_ingest_pdf function on FastAPI backend
    2. Load and chunk the PDF
    3. Generate embeddings
    4. Store vectors in Qdrant
    
    Args:
        pdf_path (Path): Absolute path to saved PDF file
    
    Returns:
        None
    
    Note:
        - Event is processed asynchronously
        - Inngest dashboard shows execution progress
        - Can check status at http://localhost:8288
    """
    client = get_inngest_client()
    client.send_sync(
        inngest.Event(
            name="rag/ingest_pdf",
            data={
                "pdf_path": str(pdf_path.resolve()),  # Absolute path
                "source_id": pdf_path.name,  # Filename for identification
            },
        )
    )


# ============================================================================
# SECTION 1: PDF UPLOAD
# ============================================================================

st.title("📄 RAG PDF Assistant")
st.markdown("Upload PDFs and ask intelligent questions about their content!")

# File uploader widget
uploaded = st.file_uploader(
    "Choose a PDF to upload",
    type=["pdf"],
    accept_multiple_files=False
)

if uploaded is not None:
    with st.spinner("Processing PDF..."):
        # Save PDF to local uploads folder
        path = save_uploaded_pdf(uploaded)
        
        # Send ingestion event to Inngest backend
        # This triggers PDF loading, chunking, embedding, and storage
        send_rag_ingest_event(path)
        
        # Small delay for better UX
        time.sleep(0.3)
    
    # Show success message
    st.success(f"✅ Successfully ingested: {path.name}")
    st.caption(
        "The PDF has been added to the knowledge base. "
        "You can now ask questions about it!"
    )

st.divider()

# ============================================================================
# SECTION 2: QUERY & ANSWER
# ============================================================================

st.title("❓ Ask a Question")


def send_rag_query_event(question: str, top_k: int) -> str:
    """
    Send query event to Inngest and get event ID.
    
    Triggers the rag_query_pdf_ai function which:
    1. Embeds the question
    2. Searches Qdrant for similar vectors
    3. Sends to LLM with context
    4. Returns answer with sources
    
    Args:
        question (str): User's question about the documents
        top_k (int): Number of context chunks to retrieve (1-20)
    
    Returns:
        str: Event ID for polling results
    
    Example:
        >>> event_id = send_rag_query_event("What is policy X?", 5)
        >>> output = wait_for_run_output(event_id)
    """
    client = get_inngest_client()
    result = client.send_sync(
        inngest.Event(
            name="rag/query_pdf_ai",
            data={
                "question": question,
                "top_k": top_k,
            },
        )
    )

    return result[0]


def _inngest_api_base() -> str:
    """
    Get Inngest API base URL.
    
    Local dev server runs at http://127.0.0.1:8288/v1 by default.
    Can be overridden with INNGEST_API_BASE environment variable.
    
    Returns:
        str: Base URL for Inngest API
    """
    return os.getenv("INNGEST_API_BASE", "http://127.0.0.1:8288/v1")


def fetch_runs(event_id: str) -> list[dict]:
    """
    Fetch function runs from Inngest API.
    
    Queries the Inngest dev server for execution results.
    
    Args:
        event_id (str): Event ID to query
    
    Returns:
        list[dict]: List of run objects for this event
    
    Raises:
        requests.HTTPError: If API call fails
    """
    # Query Inngest API for event runs
    url = f"{_inngest_api_base()}/events/{event_id}/runs"
    resp = requests.get(url)
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", [])


def wait_for_run_output(
    event_id: str,
    timeout_s: float = 120.0,
    poll_interval_s: float = 0.5
) -> dict:
    """
    Poll Inngest API until function completes.
    
    Waits for the background Inngest function to complete execution.
    Polls the API every poll_interval_s seconds.
    
    Process:
    1. Query Inngest API for run status
    2. If "Completed" or "Succeeded", return output
    3. If "Failed" or "Cancelled", raise error
    4. Otherwise, wait and retry
    5. If timeout exceeded, raise TimeoutError
    
    Args:
        event_id (str): Event ID to poll
        timeout_s (float): Maximum seconds to wait (default: 120)
        poll_interval_s (float): Seconds between polls (default: 0.5)
    
    Returns:
        dict: Function output containing answer, sources, etc.
    
    Raises:
        RuntimeError: If function run failed or was cancelled
        TimeoutError: If function didn't complete within timeout
    
    Example:
        >>> event_id = send_rag_query_event("Question?", 5)
        >>> output = wait_for_run_output(event_id)
        >>> answer = output['answer']
    """
    start = time.time()
    last_status = None
    
    while True:
        # Fetch current run status from Inngest
        runs = fetch_runs(event_id)
        
        if runs:
            run = runs[0]
            status = run.get("status")
            last_status = status or last_status
            
            # Check if function completed successfully
            if status in ("Completed", "Succeeded", "Success", "Finished"):
                return run.get("output") or {}
            
            # Check if function failed
            if status in ("Failed", "Cancelled"):
                raise RuntimeError(f"Function run {status}")
        
        # Check timeout
        if time.time() - start > timeout_s:
            raise TimeoutError(
                f"Timed out waiting for run output (last status: {last_status})"
            )
        
        # Wait before polling again
        time.sleep(poll_interval_s)


# Query form
with st.form("rag_query_form"):
    # Question input
    question = st.text_input(
        "📝 Your question:",
        placeholder="What does the policy say about...?"
    )
    
    # Number of context chunks to retrieve
    top_k = st.slider(
        "📊 Number of relevant chunks to retrieve:",
        min_value=1,
        max_value=20,
        value=5
    )
    
    # Submit button
    submitted = st.form_submit_button("🚀 Ask")

    if submitted and question.strip():
        with st.spinner("Searching and generating answer..."):
            try:
                # Send event to Inngest and wait for result
                event_id = send_rag_query_event(question.strip(), int(top_k))
                output = wait_for_run_output(event_id)
                
                # Extract answer and sources from output
                answer = output.get("answer", "")
                sources = output.get("sources", [])

                # Display results
                st.subheader("💡 Answer")
                st.write(answer or "(No answer generated)")

                # Display sources
                if sources:
                    st.subheader("📚 Sources")
                    for source in sources:
                        st.write(f"- **{source}**")

            except TimeoutError:
                st.error(
                    "⏱️ Request timed out. "
                    "Check that Inngest dev server is running at http://localhost:8288"
                )
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
