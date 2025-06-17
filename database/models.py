# database/models.py
from sqlalchemy import Column, String, JSON, Boolean, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database.session import Base

# +++ NEW User Model +++
class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # This creates the link back to the Job model
    jobs = relationship("Job", back_populates="owner")


# --- MODIFIED Job Model ---
class Job(Base):
    __tablename__ = "jobs"

    # Core job details
    id = Column(String, primary_key=True, index=True)
    status = Column(String, index=True, default="pending")
    original_query = Column(Text)
    result = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # RAG-specific details
    upload_to_rag = Column(Boolean, default=False)
    rag_status = Column(String, nullable=True)
    rag_collection_name = Column(String, nullable=True)
    rag_error = Column(String, nullable=True)
    
    # To store the conversational history for RAG
    rag_chat_context = Column(Text, default="") 

    # --- NEW: Add these two columns for structured status tracking ---
    job_stage = Column(String, nullable=True, default="pending")
    job_progress = Column(Integer, nullable=True, default=0)
    
    # --- NEW: Add this column to store live logs ---
    logs = Column(JSON, default=[]) 

    # +++ NEW: Link to the User model +++
    user_id = Column(String, ForeignKey("users.id"))
    owner = relationship("User", back_populates="jobs") 