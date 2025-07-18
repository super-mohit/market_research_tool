# api/server.py
import uuid
import os  # Add this import
import logging
from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
import asyncio
import json
import requests
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import text, desc
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from io import BytesIO, StringIO
import tempfile
import zipfile
import csv
from weasyprint import HTML  # ++ NEW IMPORT for PDF generation

# --- Logging Import ---
from api.logging_config import setup_logging
from api.sheets_logger import log_to_sheets

# --- DB Imports ---
from database.session import SessionLocal, init_db, engine
from database.models import Job as DBJob, User as DBUser # Use aliases to avoid name conflicts

# --- Auth Imports ---
from api import auth  # Our new auth module
from api.auth import get_current_user_from_query  # Import the new dependency

# --- App Imports ---
from api.models import (
    ResearchRequest, JobSubmissionResponse, JobStatusResponse, ResearchResult, ExtractedData,
    RAGQueryRequest, RAGQueryResponse, RAGCollectionInfo, JobHistoryResponse,
    TopicRequest, GeneratedTagsResponse, OverviewData,  # <-- ADD OverviewData import
    ExportRequest  # <-- NEW IMPORT for Export Center
)
from src.config import assert_all_env, assert_rag_env
from src.rag_uploader import query_rag_collection
from src.query_enhancer import generate_tags_from_topic # <-- NEW IMPORT

# +++ Import the Celery task +++
from src.tasks import run_research_pipeline_task

# +++ Import PDF generation utilities +++
from src.utils.pdf_generator import ProfessionalPDFGenerator



# +++ NEW: Pydantic models for auth +++
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    company_name: str  # <--- ADD THIS

class UserPublic(BaseModel):
    id: str
    email: EmailStr
    name: Optional[str] = None
    company_name: Optional[str] = None  # <--- ADD THIS
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str



# --- App Setup ---
app = FastAPI(
    title="Market Research Automation API",
    description="An API to run an automated market research pipeline.",
    version="1.0.0"
)

# This is the crucial part. It allows your frontend to talk to the backend.
# We will get the production URL from an environment variable.
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173") 

origins = [
    "http://localhost:5173", # Default Vite dev server port
    "http://localhost:3000", # Common React dev server port
    "http://localhost:5174", # Another possible Vite port
    FRONTEND_URL, # Add your production URL here
]

# Remove any duplicates if FRONTEND_URL is a localhost one
origins = list(set(origins)) 
logging.info(f"Allowing origins: {origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods (GET, POST, etc.)
    allow_headers=["*"], # Allows all headers
)

# --- Database Initialization and Logging on Startup ---
@app.on_event("startup")
def on_startup():
    setup_logging()  # Set up logging first
    init_db()

# --- Dependency to get a DB session ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# +++ NEW: Auth Endpoints +++
@app.post("/api/auth/signup", response_model=UserPublic)
def signup(user_in: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(DBUser).filter(DBUser.email == user_in.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = auth.get_password_hash(user_in.password)
    new_user = DBUser(
        id=str(uuid.uuid4()),
        email=user_in.email,
        name=user_in.name,
        company_name=user_in.company_name,  # <--- SAVE THE COMPANY NAME
        hashed_password=hashed_password
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # +++ NEW LOGGING +++
    log_to_sheets(
        eventType="user_signup",
        userId=new_user.id,
        userEmail=new_user.email
    )

    return new_user

@app.post("/api/auth/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(DBUser).filter(DBUser.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # +++ NEW LOGGING +++
    log_to_sheets(
        eventType="user_login",
        userId=user.id,
        userEmail=user.email
    )
    
    access_token = auth.create_access_token(data={"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer"}


# --- NEW: Smart Query Generation Endpoint ---
@app.post("/api/research/generate-tags", response_model=GeneratedTagsResponse)
async def suggest_research_tags(
    request: TopicRequest,
    current_user: DBUser = Depends(auth.get_current_user) # Protect the route
):
    """
    Accepts a user's topic and uses an LLM to generate a structured set
    of categorized keywords and search phrases for refining the research.
    """
    if not request.topic.strip():
        raise HTTPException(status_code=400, detail="Topic cannot be empty.")

    try:
        tags_data = generate_tags_from_topic(request.topic)
        return tags_data
    except Exception as e:
        logging.error(f"Error in generate-tags endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate tags due to an internal error.")


# --- Background Task (Moved to Celery) ---
# The run_and_store_results function has been moved to src/tasks.py as a Celery task


def _dict_to_extracted_model(raw_dict: dict) -> ExtractedData:
    padded = {k: raw_dict.get(k, []) for k in ["News", "Patents", "Conference", "Legalnews", "Other"]}
    return ExtractedData(**padded)


# --- Helper function for CSV generation ---
def _generate_csv_bytes(items: List[dict]) -> bytes:
    """Converts a list of dictionaries to CSV formatted bytes."""
    if not items:
        return b""
    
    # Use StringIO to build the CSV in memory
    output = StringIO()
    # Use the keys from the first item as headers
    headers = items[0].keys()
    writer = csv.DictWriter(output, fieldnames=headers)
    
    writer.writeheader()
    writer.writerows(items)
    
    # Return the string as UTF-8 encoded bytes
    return output.getvalue().encode('utf-8')


# --- API Endpoints (Now DB-aware) ---

@app.post("/api/research", response_model=JobSubmissionResponse, status_code=202)
async def create_research_job(
    request: Request,
    research_request: ResearchRequest,
    db: Session = Depends(get_db),
    current_user: DBUser = Depends(auth.get_current_user) # <-- PROTECT THE ROUTE
):
    assert_all_env()
    if research_request.upload_to_rag:
        try:
            assert_rag_env()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Cannot process RAG upload: {e}")

    job_id = str(uuid.uuid4())
    base_url = str(request.base_url)

    # Create the job record in the database
    new_job = DBJob(
        id=job_id,
        status="pending",
        original_query=research_request.query,
        upload_to_rag=research_request.upload_to_rag,
        rag_status="pending" if research_request.upload_to_rag else None,
        user_id=current_user.id  # <-- LINK THE JOB TO THE USER
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    # +++ NEW LOGGING +++
    log_to_sheets(
        eventType="job_created",
        userId=current_user.id,
        userEmail=current_user.email,
        jobId=new_job.id,
        query=new_job.original_query,
        status="pending",
        details={"rag_requested": new_job.upload_to_rag}
    )

    # --- THIS IS THE KEY CHANGE ---
    # Instead of using BackgroundTasks, we send the job to the Celery queue.
    # The .delay() method is a shortcut to send a task message.
    run_research_pipeline_task.delay(
        job_id=job_id,
        query=research_request.query,
        should_upload_to_rag=research_request.upload_to_rag
    )
    logging.info(f"Dispatched job {job_id} to Celery worker.")

    return {
        "job_id": job_id,
        "status": "pending",
        "status_url": f"{base_url}api/research/status/{job_id}",
        "result_url": f"{base_url}api/research/result/{job_id}"
    }


@app.get("/api/research/status/{job_id}", response_model=JobStatusResponse)
async def get_research_status(job_id: str, db: Session = Depends(get_db), current_user: DBUser = Depends(auth.get_current_user)):
    job = db.query(DBJob).filter(DBJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check if the job belongs to the current user
    if job.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied: Job belongs to another user")

    # --- MODIFIED: Construct a more detailed message and response ---
    message = f"Job status is {job.status}"
    if job.status == 'running' and job.job_stage:
        message = f"Executing stage: {job.job_stage.replace('_', ' ').title()}"
    
    if job.upload_to_rag:
        rag_status = job.rag_status or 'unknown'
        if rag_status == 'uploaded':
            message += f". RAG upload successful (Collection: {job.rag_collection_name or 'unknown'})"
        elif rag_status == 'failed':
            message += f". RAG upload failed: {job.rag_error or 'Unknown RAG error'}"
        else:
             message += f". RAG status: {rag_status}"
    
    if job.status == 'failed':
        error_msg = job.result.get('error', 'Unknown error') if job.result else 'Unknown error'
        message = f"Job failed. Error: {error_msg}"

    return {
        "job_id": job_id,
        "status": job.status,
        "message": message,
        "stage": job.job_stage,
        "progress": job.job_progress,
        # --- NEW: Return the logs array ---
        "logs": job.logs[-10:] if job.logs else [] # Return last 10 logs
    }


@app.get("/api/research/result/{job_id}", response_model=ResearchResult)
async def get_research_result(job_id: str, current_user: DBUser = Depends(auth.get_current_user)):
    """
    🔥 FIXED: Result endpoint with proper RAG info
    """
    db = SessionLocal()
    try:
        job = db.query(DBJob).filter(DBJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Check if the job belongs to the current user
        if job.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied: Job belongs to another user")
        
        if job.status == 'pending' or job.status == 'running':
            raise HTTPException(status_code=202, detail="Job still in progress")
        
        if job.status == 'failed':
            error_msg = job.result.get("error", "Unknown error") if job.result else "Unknown error"
            raise HTTPException(status_code=500, detail=f"Job failed: {error_msg}")
        
        if not job.result:
            raise HTTPException(status_code=500, detail="Job completed but no result found")
        
        # 🔥 CRITICAL: Build metadata with RAG info
        enhanced_metadata = job.result.get("metadata", {}).copy()
        
        if job.upload_to_rag:
            enhanced_metadata['ragInfo'] = {
                'upload_requested': True,
                'rag_status': job.rag_status or 'pending_upload',
                'collection_name': job.rag_collection_name,
                'rag_error': job.rag_error,
                'can_query': job.rag_status == 'uploaded'
            }
            logging.info(f"Job {job_id}: RAG Info - Status: {job.rag_status}, Can Query: {job.rag_status == 'uploaded'}")
        else:
            enhanced_metadata['ragInfo'] = {
                'upload_requested': False,
                'rag_status': 'not_requested',
                'can_query': False
            }
        
        response = ResearchResult(
            job_id=job.id,
            status='completed',
            original_query=job.result.get("original_query"),
            final_report_markdown=job.result.get("final_report_markdown"),
            # +++ THIS IS THE FIX: Pass the overview_data to the response model +++
            overview_data=job.result.get("overview_data"),
            # +++ ADD THIS LINE +++
            strategic_insights=job.result.get("strategic_insights"),
            extracted_data=_dict_to_extracted_model(job.result.get("extracted_data", {})),
            metadata=enhanced_metadata
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error retrieving job result {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve job result: {str(e)}")
    finally:
        db.close()


# +++ NEW: Endpoint to get user's job history +++
@app.get("/api/research/history", response_model=JobHistoryResponse)
async def get_user_research_history(
    db: Session = Depends(get_db),
    current_user: DBUser = Depends(auth.get_current_user)
):
    """
    Retrieves a list of all research jobs submitted by the current user.
    """
    # Query the database for jobs belonging to the current user,
    # ordering by the creation date in descending order (newest first).
    jobs = (
        db.query(DBJob)
        .filter(DBJob.user_id == current_user.id)
        .order_by(desc(DBJob.created_at))
        .all()
    )
    
    if not jobs:
        return {"jobs": []}  # Return an empty list if no jobs are found
        
    return {"jobs": jobs}


@app.post("/api/rag/query", response_model=RAGQueryResponse)
async def ask_rag_collection(query_request: RAGQueryRequest, db: Session = Depends(get_db), current_user: DBUser = Depends(auth.get_current_user)):
    try:
        assert_rag_env()

        # Find the job associated with the collection to get/update chat context
        job = db.query(DBJob).filter(DBJob.rag_collection_name == query_request.collection_name).first()
        if not job:
            raise HTTPException(status_code=404, detail=f"Collection '{query_request.collection_name}' not associated with any known job.")
        
        # Check if the job belongs to the current user
        if job.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied: Collection belongs to another user")

        logging.info(f"Processing RAG query for collection: {query_request.collection_name}")
        logging.info(f"Question: {query_request.question}")

        # Pass the current context from the DB
        answer_payload = await query_rag_collection(
            collection_name=query_request.collection_name,
            question=query_request.question,
            current_chat_context=job.rag_chat_context # Pass current context
        )

        logging.info(f"RAG API returned: {answer_payload}")

        # Update the chat context in the DB
        if answer_payload and 'chat_context' in answer_payload:
            new_fragment = answer_payload['chat_context']
            separator = " " if job.rag_chat_context else ""
            job.rag_chat_context += separator + new_fragment
            db.commit()

        # Ensure we're returning the correct structure
        response = RAGQueryResponse(
            collection_name=query_request.collection_name,
            question=query_request.question,
            answer=answer_payload
        )
        
        logging.info(f"Returning response: {response.dict()}")
        return response
        
    except ValueError as e:
        logging.error(f"RAG configuration error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"RAG system not properly configured: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error in RAG query: {str(e)}", exc_info=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {str(e)}")


@app.get("/api/research/{job_id}/rag", response_model=RAGCollectionInfo)
async def get_job_rag_info(job_id: str, db: Session = Depends(get_db), current_user: DBUser = Depends(auth.get_current_user)):
    job = db.query(DBJob).filter(DBJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check if the job belongs to the current user
    if job.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied: Job belongs to another user")
    
    if not job.upload_to_rag:
        raise HTTPException(status_code=400, detail="RAG upload was not requested for this job")
    
    return RAGCollectionInfo(
        job_id=job_id,
        rag_status=job.rag_status or 'unknown',
        collection_name=job.rag_collection_name,
        rag_error=job.rag_error,
        can_query=(job.rag_status == 'uploaded' and job.rag_collection_name is not None)
    )


async def job_update_generator(job_id: str):
    """
    Yields real-time updates for a given job as Server-Sent Events.
    This version uses short-lived DB sessions to avoid stale data reads.
    """
    while True:
        db = SessionLocal()  # <-- Session created on EACH loop iteration
        try:
            job = db.query(DBJob).filter(DBJob.id == job_id).first()
            if not job:
                logging.warning(f"SSE stream for job {job_id} terminated: Job not found in DB.")
                break

            # Send status updates
            status_data = {
                'status': job.status,
                'stage': job.job_stage,
                'progress': job.job_progress
            }
            yield f"event: status\ndata: {json.dumps(status_data)}\n\n"

            # Check for completion
            if job.status == 'completed' and job.result:
                logging.info(f"SSE stream for job {job_id}: Detected 'completed' status. Sending final result and closing.")
                final_payload = {
                    "job_id": job.id,
                    "status": 'completed',
                    "original_query": job.result.get("original_query"),
                    "final_report_markdown": job.result.get("final_report_markdown"),
                    "extracted_data": _dict_to_extracted_model(job.result.get("extracted_data", {})).dict(),
                    "metadata": job.result.get("metadata", {})
                }
                yield f"event: result\ndata: {json.dumps(final_payload)}\n\n"
                yield f"event: close\ndata: Job finished\n\n"
                break # Exit the loop

            # Check for failure
            if job.status == 'failed':
                logging.warning(f"SSE stream for job {job_id}: Detected 'failed' status. Closing connection.")
                yield f"event: close\ndata: Job failed\n\n"
                break # Exit the loop

        finally:
            db.close()  # <-- Session closed on EACH loop iteration

        # Wait before the next check
        await asyncio.sleep(2)

# --- NEW: SSE Endpoint ---
@app.get("/api/research/stream/{job_id}")
async def stream_research_status(
    job_id: str, 
    # --- THIS IS THE CHANGE ---
    current_user: DBUser = Depends(auth.get_user_from_header_or_query)
):
    # Verify the job belongs to the current user before streaming
    db = SessionLocal()
    try:
        job = db.query(DBJob).filter(DBJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Check if the job belongs to the current user
        if job.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied: Job belongs to another user")
    finally:
        db.close()
    
    return StreamingResponse(job_update_generator(job_id), media_type="text/event-stream")


# +++ NEW: PDF download endpoint +++
@app.get("/api/research/{job_id}/download-pdf")
async def download_research_pdf(
    job_id: str, 
    db: Session = Depends(get_db), 
    current_user: DBUser = Depends(auth.get_current_user)
):
    job = db.query(DBJob).filter(DBJob.id == job_id, DBJob.user_id == current_user.id).first()
    if not job or job.status != 'completed':
        raise HTTPException(status_code=404, detail="Completed job not found")

    report_md = job.result.get("final_report_markdown", "No content available.")
    
    # Extract a more meaningful title from the query instead of a hard truncation.
    # We'll use the first non-empty line as the subtitle.
    query_lines = job.original_query.strip().split('\n')
    report_title = next((line.strip() for line in query_lines if line.strip()), "Market Research Summary")
    
    # Apply a more generous length limit to prevent excessively long subtitles.
    # The CSS will handle wrapping the text gracefully.
    report_title = report_title[:200]

    try:
        pdf_generator = ProfessionalPDFGenerator()
        pdf_bytes = pdf_generator.generate_pdf_from_markdown(report_md, report_title, current_user.name or current_user.email)

        file_name = f"Supervity_Report_{job_id[:8]}.pdf"
        headers = {'Content-Disposition': f'attachment; filename="{file_name}"'}
        
        return StreamingResponse(BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)

    except Exception as e:
        logging.error(f"PDF generation failed for job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate PDF report.")


# +++ NEW: The Export Center Endpoint +++
@app.post("/api/research/{job_id}/export")
async def export_research_package(
    job_id: str,
    request: ExportRequest,
    db: Session = Depends(get_db),
    current_user: DBUser = Depends(auth.get_current_user)
):
    """
    Generates a downloadable .zip package containing selected research assets.
    """
    job = db.query(DBJob).filter(DBJob.id == job_id, DBJob.user_id == current_user.id).first()
    if not job or job.status != 'completed' or not job.result:
        raise HTTPException(status_code=404, detail="Completed job with results not found for the current user.")

    # Create an in-memory ZIP file
    in_memory_zip = BytesIO()
    with zipfile.ZipFile(in_memory_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for asset in request.assets:
            try:
                if asset.type == 'report':
                    if asset.format == 'pdf':
                        pdf_generator = ProfessionalPDFGenerator()
                        pdf_bytes = pdf_generator.generate_pdf_from_markdown(
                            job.result.get("final_report_markdown", ""),
                            job.original_query[:80],
                            current_user.name or current_user.email
                        )
                        zipf.writestr("Executive_Report.pdf", pdf_bytes)
                        logging.info(f"Job {job_id}: Added PDF report to export package.")
                    elif asset.format == 'md':
                        md_content = job.result.get("final_report_markdown", "")
                        zipf.writestr("Executive_Report.md", md_content.encode('utf-8'))
                        logging.info(f"Job {job_id}: Added Markdown report to export package.")

                elif asset.type == 'data' and asset.include:
                    structured_data = job.result.get("extracted_data", {})
                    for data_type in asset.include:
                        items = structured_data.get(data_type, [])
                        if not items:
                            continue # Skip empty data types
                        
                        if asset.format == 'csv':
                            csv_bytes = _generate_csv_bytes(items)
                            zipf.writestr(f"data/{data_type}.csv", csv_bytes)
                        elif asset.format == 'json':
                            json_bytes = json.dumps(items, indent=2).encode('utf-8')
                            zipf.writestr(f"data/{data_type}.json", json_bytes)
                    logging.info(f"Job {job_id}: Added structured data (types: {asset.include}) as {asset.format} to export package.")



            except Exception as e:
                logging.error(f"Failed to generate asset '{asset.type}' in format '{asset.format}' for job {job_id}: {e}", exc_info=True)
                # Add an error file to the zip to inform the user
                zipf.writestr(f"ERROR_{asset.type}.txt", f"Failed to generate this asset. Error: {e}")

    # Reset the buffer's pointer to the beginning before reading
    in_memory_zip.seek(0)
    
    # Set headers for file download
    file_name = f"Supervity_Export_{job_id[:8]}.zip"
    headers = {'Content-Disposition': f'attachment; filename="{file_name}"'}
    
    return StreamingResponse(in_memory_zip, media_type="application/zip", headers=headers)


