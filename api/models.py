# api/models.py
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field
from datetime import datetime

# --- Request Models ---

class ResearchRequest(BaseModel):
    """The user's initial request to start a research job."""
    query: str = Field(
        ...,
        description="The natural language query for the market research.",
        example="Show me the latest innovations in Weatherability of Decorative Coatings.",
        min_length=10,
        max_length=2000
    )
    upload_to_rag: bool = Field(
        default=True,
        description="If true, all generated artifacts will be uploaded to the internal RAG system for future querying."
    )

class RAGQueryRequest(BaseModel):
    """Request to query a RAG collection."""
    collection_name: str = Field(
        ..., 
        description="The name of the RAG collection to query (e.g., 'research_job_<uuid>')",
        example="research_job_12345678_1234_5678_9abc_123456789def"
    )
    question: str = Field(
        ..., 
        description="The question to ask the RAG system.",
        example="What are the latest innovations in coating technology?",
        min_length=5,
        max_length=1000
    )

# --- Response Models ---

class JobSubmissionResponse(BaseModel):
    """Response after submitting a job, providing the ID and status URL."""
    job_id: str
    status: str = "pending"
    status_url: str
    result_url: str


class JobStatusResponse(BaseModel):
    """Response for checking the status of a job."""
    job_id: str
    status: str = Field(..., description="Current job status: pending, running, completed, or failed")
    message: str = Field(..., description="Detailed status message including RAG upload status if applicable")
    stage: Optional[str] = Field(None, description="The current machine-readable stage of the pipeline")
    progress: Optional[int] = Field(None, description="An estimated progress percentage for the current stage")
    logs: Optional[List[str]] = Field(None, description="A list of the latest log messages from the job.")


class StructuredDataItem(BaseModel):
    """A single extracted item, like a news article or patent."""
    type: str = Field(..., description="Type of the item (News, Patents, Conference, etc.)")
    title: str = Field(..., description="Title of the item")
    summary: str = Field(..., description="Summary or description of the item")
    date: Optional[str] = Field(None, description="Publication or event date")
    source_url: str = Field(..., description="Original URL of the item")


class ExtractedData(BaseModel):
    """The categorized collection of all structured items."""
    News: List[StructuredDataItem] = Field(default_factory=list, description="News articles and updates")
    Patents: List[StructuredDataItem] = Field(default_factory=list, description="Patent filings and innovations")
    Conference: List[StructuredDataItem] = Field(default_factory=list, description="Conference proceedings and presentations")
    Legalnews: List[StructuredDataItem] = Field(default_factory=list, description="Legal news and regulatory updates")
    Other: List[StructuredDataItem] = Field(default_factory=list, description="Other miscellaneous items")


class RAGInfo(BaseModel):
    """Information about RAG upload status and collection."""
    upload_requested: bool = Field(..., description="Whether RAG upload was requested")
    rag_status: Optional[str] = Field(None, description="Status of RAG upload: pending, uploaded, failed")
    collection_name: Optional[str] = Field(None, description="Name of the created RAG collection")
    rag_error: Optional[str] = Field(None, description="Error message if RAG upload failed")


class ResearchResult(BaseModel):
    """The final, complete result of a research job."""
    job_id: str
    status: str
    original_query: str = Field(..., description="The original research query")
    final_report_markdown: str = Field(..., description="Complete final report in markdown format")
    extracted_data: ExtractedData = Field(..., description="Structured extracted data categorized by type")
    metadata: Dict[str, Any] = Field(..., description="Additional metadata including extraction stats and RAG info")


class RAGQueryResponse(BaseModel):
    """Response from querying a RAG collection."""
    collection_name: str
    question: str
    answer: Union[Dict[str, Any], str] = Field(..., description="The answer from the RAG system")
    
    class Config:
        # Allow for flexibility in the answer format
        extra = "allow"


class RAGCollectionInfo(BaseModel):
    """Information about a job's RAG collection."""
    job_id: str
    rag_status: str = Field(..., description="Status: pending, uploaded, failed, unknown")
    collection_name: Optional[str] = Field(None, description="Name of the RAG collection if available")
    rag_error: Optional[str] = Field(None, description="Error message if upload failed")
    can_query: bool = Field(..., description="Whether the collection is ready for querying")


# +++ NEW: Models for Job History +++
class JobHistoryItem(BaseModel):
    id: str
    original_query: str
    status: str
    created_at: datetime  # We'll use this for display and sorting

    class Config:
        from_attributes = True

class JobHistoryResponse(BaseModel):
    jobs: List[JobHistoryItem]