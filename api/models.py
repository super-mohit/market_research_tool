# api/models.py
from typing import List, Optional, Dict, Any, Union, Literal
from pydantic import BaseModel, Field, constr
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


# +++ START: ADD THIS NEW MODEL +++
class OverviewData(BaseModel):
    """
    Pydantic model for the visual overview data generated in Phase 6.
    """
    short_summary: Optional[str] = None
    word_cloud: Optional[List[Dict[str, Any]]] = None
    swot_analysis: Optional[Dict[str, Any]] = None
    geographic_insights: Optional[Dict[str, Any]] = None
    competitive_radar: Optional[Dict[str, Any]] = None
    tech_hype_cycle: Optional[List[Dict[str, Any]]] = None

    class Config:
        from_attributes = True
        extra = "allow" # Allows for flexibility if more fields are added
# +++ END: ADD THIS NEW MODEL +++


# +++ START: ADD NEW MODELS FOR PERSONALIZED STRATEGY +++
class StrategicInsightItem(BaseModel):
    title: str
    justification: str
    impact: Literal["High", "Medium", "Low"]
    timeframe: Literal["Short-Term (0-1yr)", "Medium-Term (1-3yr)", "Long-Term (3+yr)"]

class ActionItem(BaseModel):
    action: str
    department: Literal["R&D", "Marketing", "Business Development", "Operations", "Executive Leadership"]
    urgency: Literal["High", "Medium", "Low"]

class StrategicInsightsData(BaseModel):
    market_positioning: Optional[str] = None
    key_opportunities: Optional[List[StrategicInsightItem]] = None
    key_threats: Optional[List[StrategicInsightItem]] = None
    recommended_actions: Optional[List[ActionItem]] = None
    executive_summary: Optional[str] = None
    error: Optional[str] = None
# +++ END: ADD NEW MODELS +++


class ResearchResult(BaseModel):
    """The final, complete result of a research job."""
    job_id: str
    status: str
    original_query: str = Field(..., description="The original research query")
    final_report_markdown: str = Field(..., description="Complete final report in markdown format")
    extracted_data: ExtractedData = Field(..., description="Structured extracted data categorized by type")
    overview_data: Optional[OverviewData] = Field(None, description="Data for visual overview dashboard")
    strategic_insights: Optional[StrategicInsightsData] = Field(None, description="Personalized strategic analysis for Wacker")
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


# --- NEW: Models for Smart Tag Generation ---

class TopicRequest(BaseModel):
    """Request to generate categorized search tags from a topic."""
    topic: str = Field(
        ...,
        description="The user's initial research topic or a full query.",
        example="Innovations in epoxy coatings",
        min_length=3,
        max_length=2000
    )

class GeneratedTagsResponse(BaseModel):
    """Response containing AI-generated, categorized conceptual tags."""
    performance_attributes: List[str] = Field(..., description="Physical or chemical properties and benefits.")
    technologies_and_materials: List[str] = Field(..., description="Specific chemistries, materials, or processes.")
    market_and_business: List[str] = Field(..., description="High-level business, market, or strategic concepts.")
    key_players_and_products: List[str] = Field(..., description="Specific companies or well-known product lines.")


# --- NEW: Models for the Export Center ---

class ExportAsset(BaseModel):
    """Defines a single asset to be included in the export package."""
    type: Literal["report", "data"] = Field(..., description="The type of asset to export.")
    format: Literal["pdf", "md", "csv", "json"] = Field(..., description="The desired file format for the asset.")
    include: Optional[List[str]] = Field(None, description="For 'data' type, a list of categories to include (e.g., ['News', 'Patents']).")

class ExportRequest(BaseModel):
    """The request body for the export endpoint."""
    assets: List[ExportAsset] = Field(..., min_items=1, description="A list of assets to be exported.")