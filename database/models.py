# database/models.py
from sqlalchemy import Column, String, JSON, Boolean, Text
from database.session import Base

class Job(Base):
    __tablename__ = "jobs"

    # Core job details
    id = Column(String, primary_key=True, index=True)
    status = Column(String, index=True, default="pending")
    original_query = Column(Text)
    
    # Stores the final research result dictionary as a JSON object
    # This is incredibly flexible.
    result = Column(JSON)
    
    # RAG-specific details
    upload_to_rag = Column(Boolean, default=False)
    rag_status = Column(String, nullable=True)
    rag_collection_name = Column(String, nullable=True)
    rag_error = Column(String, nullable=True)
    
    # To store the conversational history for RAG
    rag_chat_context = Column(Text, default="") 