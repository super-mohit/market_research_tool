# api/server.py
import uuid
import os  # Add this import
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import requests
from sqlalchemy.orm import Session
from sqlalchemy import text

# --- DB Imports ---
from database.session import SessionLocal, init_db, engine
from database.models import Job as DBJob # Use an alias to avoid name conflicts

# --- App Imports ---
from api.models import (
    ResearchRequest, JobSubmissionResponse, JobStatusResponse, ResearchResult, ExtractedData,
    RAGQueryRequest, RAGQueryResponse, RAGCollectionInfo
)
from src.main import execute_research_pipeline
from src.config import assert_all_env, assert_rag_env
from src.rag_uploader import upload_artifacts_to_rag, query_rag_collection

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
print(f"Allowing origins: {origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods (GET, POST, etc.)
    allow_headers=["*"], # Allows all headers
)

# --- Database Initialization on Startup ---
@app.on_event("startup")
def on_startup():
    init_db()

# --- Dependency to get a DB session ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Background Task (Now DB-aware) ---
def run_and_store_results(job_id: str, query: str, should_upload_to_rag: bool):
    """
    🔥 FIXED: Job processing with immediate completion and parallel RAG upload
    """
    db = SessionLocal()
    try:
        job = db.query(DBJob).filter(DBJob.id == job_id).first()
        if not job:
            print(f"Job {job_id} not found in DB for background task. Aborting.")
            return

        print(f"Job {job_id}: Starting research pipeline...")
        job.status = 'running'
        job.job_stage = 'initializing'
        job.job_progress = 5
        db.commit()

        async def update_status_in_db(stage: str = None, progress: int = None, message: str = None):
            db_session = SessionLocal()
            try:
                job_to_update = db_session.query(DBJob).filter(DBJob.id == job_id).first()
                if job_to_update:
                    if stage: 
                        job_to_update.job_stage = stage
                    if progress: 
                        job_to_update.job_progress = progress
                    if message:
                        if job_to_update.logs is None:
                            job_to_update.logs = []
                        job_to_update.logs = job_to_update.logs + [message]
                    db_session.commit()
            except Exception as e:
                print(f"Error updating job status: {e}")
            finally:
                db_session.close()
            await asyncio.sleep(0)

        # Run the research pipeline
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result_data = loop.run_until_complete(
                execute_research_pipeline(query, update_status_in_db)
            )
        finally:
            loop.close()
        
        # 🔥 CRITICAL: Mark job as completed IMMEDIATELY
        print(f"Job {job_id}: Pipeline completed. Marking as COMPLETED immediately...")
        job.result = result_data
        job.status = 'completed'  # This is the key change
        job.job_stage = 'finished'
        job.job_progress = 100
        
        # 🔥 CRITICAL: Set RAG status properly
        if should_upload_to_rag:
            job.upload_to_rag = True
            job.rag_status = 'pending_upload'
        else:
            job.upload_to_rag = False
            job.rag_status = 'not_requested'
        
        db.commit()
        print(f"Job {job_id}: ✅ Status set to COMPLETED. Frontend can now detect completion.")
        
        # 🔥 CRITICAL: Start RAG upload in background thread (doesn't block completion)
        if should_upload_to_rag:
            print(f"Job {job_id}: Starting RAG upload in background...")
            
            def run_rag_upload():
                try:
                    collection_name = upload_artifacts_to_rag(job_id, result_data)
                    
                    # Update RAG status
                    with SessionLocal() as rag_db:
                        rag_job = rag_db.query(DBJob).filter(DBJob.id == job_id).first()
                        if rag_job:
                            if collection_name:
                                rag_job.rag_collection_name = collection_name
                                rag_job.rag_status = 'uploaded'
                                print(f"Job {job_id}: ✅ RAG upload successful. Collection: {collection_name}")
                            else:
                                rag_job.rag_status = 'failed'
                                rag_job.rag_error = 'RAG upload failed'
                                print(f"Job {job_id}: ❌ RAG upload failed")
                            rag_db.commit()
                except Exception as rag_error:
                    print(f"Job {job_id}: RAG error: {rag_error}")
                    with SessionLocal() as rag_db:
                        rag_job = rag_db.query(DBJob).filter(DBJob.id == job_id).first()
                        if rag_job:
                            rag_job.rag_status = 'failed'
                            rag_job.rag_error = str(rag_error)
                            rag_db.commit()
            
            import threading
            rag_thread = threading.Thread(target=run_rag_upload, daemon=True)
            rag_thread.start()
    
    except Exception as e:
        print(f"Job {job_id}: ❌ Pipeline failed: {e}")
        job.status = 'failed'
        job.job_stage = 'error'
        job.job_progress = 0
        job.result = {"error": str(e)}
        db.commit()
    finally:
        db.close()


def _dict_to_extracted_model(raw_dict: dict) -> ExtractedData:
    padded = {k: raw_dict.get(k, []) for k in ["News", "Patents", "Conference", "Legalnews", "Other"]}
    return ExtractedData(**padded)


# --- API Endpoints (Now DB-aware) ---

@app.post("/api/research", response_model=JobSubmissionResponse, status_code=202)
async def create_research_job(
    request: Request,
    research_request: ResearchRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db) # <-- Dependency Injection
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
        rag_status="pending" if research_request.upload_to_rag else None
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    background_tasks.add_task(
        run_and_store_results,
        job_id,
        research_request.query,
        research_request.upload_to_rag
    )

    return {
        "job_id": job_id,
        "status": "pending",
        "status_url": f"{base_url}api/research/status/{job_id}",
        "result_url": f"{base_url}api/research/result/{job_id}"
    }


@app.get("/api/research/status/{job_id}", response_model=JobStatusResponse)
async def get_research_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(DBJob).filter(DBJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

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
async def get_research_result(job_id: str):
    """
    🔥 FIXED: Result endpoint with proper RAG info
    """
    db = SessionLocal()
    try:
        job = db.query(DBJob).filter(DBJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
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
            print(f"Job {job_id}: RAG Info - Status: {job.rag_status}, Can Query: {job.rag_status == 'uploaded'}")
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
            extracted_data=_dict_to_extracted_model(job.result.get("extracted_data", {})),
            metadata=enhanced_metadata
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error retrieving job result {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve job result: {str(e)}")
    finally:
        db.close()


@app.post("/api/rag/query", response_model=RAGQueryResponse)
async def ask_rag_collection(query_request: RAGQueryRequest, db: Session = Depends(get_db)):
    try:
        assert_rag_env()

        # Find the job associated with the collection to get/update chat context
        job = db.query(DBJob).filter(DBJob.rag_collection_name == query_request.collection_name).first()
        if not job:
            raise HTTPException(status_code=404, detail=f"Collection '{query_request.collection_name}' not associated with any known job.")

        print(f"Processing RAG query for collection: {query_request.collection_name}")
        print(f"Question: {query_request.question}")

        # Pass the current context from the DB
        answer_payload = query_rag_collection(
            collection_name=query_request.collection_name,
            question=query_request.question,
            current_chat_context=job.rag_chat_context # Pass current context
        )

        print(f"RAG API returned: {answer_payload}")

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
        
        print(f"Returning response: {response.dict()}")
        return response
        
    except ValueError as e:
        print(f"RAG configuration error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"RAG system not properly configured: {str(e)}")
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else 500
        error_detail = e.response.text if e.response else str(e)
        print(f"RAG API HTTP error: {status_code} - {error_detail}")
        raise HTTPException(status_code=status_code, detail=f"Error from RAG API: {error_detail}")
    except Exception as e:
        print(f"Unexpected error in RAG query: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {str(e)}")


@app.get("/api/research/{job_id}/rag", response_model=RAGCollectionInfo)
async def get_job_rag_info(job_id: str, db: Session = Depends(get_db)):
    job = db.query(DBJob).filter(DBJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
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
    """
    db = SessionLocal()
    completion_sent = False
    
    try:
        while True:
            job = db.query(DBJob).filter(DBJob.id == job_id).first()
            if not job:
                break

            # Send status updates
            status_data = {
                'status': job.status, 
                'stage': job.job_stage, 
                'progress': job.job_progress
            }
            yield f"event: status\ndata: {json.dumps(status_data)}\n\n"

            # When job is completed, send result and close
            if job.status == 'completed' and job.result and not completion_sent:
                completion_sent = True
                
                # Send the full result
                final_payload = {
                    "job_id": job.id,
                    "status": 'completed',
                    "original_query": job.result.get("original_query"),
                    "final_report_markdown": job.result.get("final_report_markdown"),
                    "extracted_data": _dict_to_extracted_model(job.result.get("extracted_data", {})).dict(),
                    "metadata": job.result.get("metadata", {})
                }
                yield f"event: result\ndata: {json.dumps(final_payload)}\n\n"
                
                # Close the connection
                yield f"event: close\ndata: Job finished\n\n"
                break

            if job.status == 'failed':
                yield f"event: close\ndata: Job failed\n\n"
                break

            await asyncio.sleep(2)
            
    finally:
        db.close()

# --- NEW: SSE Endpoint ---
@app.get("/api/research/stream/{job_id}")
async def stream_research_status(job_id: str):
    return StreamingResponse(job_update_generator(job_id), media_type="text/event-stream")