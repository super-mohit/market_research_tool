# api/server.py
import uuid
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import requests
from sqlalchemy.orm import Session

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
origins = [
    "http://localhost:5173", # Default Vite dev server port
    "http://localhost:3000", # Common React dev server port
    "http://localhost:5174", # Another possible Vite port
]

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
    # Each background task gets its own database session
    db = SessionLocal()
    try:
        job = db.query(DBJob).filter(DBJob.id == job_id).first()
        if not job:
            print(f"Job {job_id} not found in DB for background task. Aborting.")
            return

        print(f"Job {job_id}: Starting research pipeline...")
        job.status = 'running'
        db.commit()

        # Run the pipeline in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result_data = loop.run_until_complete(execute_research_pipeline(query))
        
        job.result = result_data
        job.status = 'completed'
        db.commit()
        print(f"Job {job_id}: Pipeline completed successfully.")
        
        if should_upload_to_rag:
            print(f"Job {job_id}: Starting RAG upload...")
            job.rag_status = 'pending_upload'
            db.commit()
            
            try:
                collection_name = upload_artifacts_to_rag(job_id, result_data)
                
                if collection_name:
                    job.rag_collection_name = collection_name
                    job.rag_status = 'uploaded'
                    print(f"Job {job_id}: RAG upload successful. Collection: {collection_name}")
                else:
                    job.rag_status = 'failed'
                    job.rag_error = 'RAG upload failed - see logs for details'
                    print(f"Job {job_id}: RAG upload failed")
                db.commit()
            except Exception as rag_error:
                print(f"Job {job_id}: RAG upload error: {rag_error}")
                job.rag_status = 'failed'
                job.rag_error = str(rag_error)
                db.commit()
    
    except Exception as e:
        print(f"Job {job_id}: Pipeline failed. Error: {e}")
        # Make sure to update the job in the DB with the failure status
        job_in_db = db.query(DBJob).filter(DBJob.id == job_id).first()
        if job_in_db:
            job_in_db.status = 'failed'
            job_in_db.result = {"error": str(e)}
            db.commit()
    finally:
        loop.close()
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

    message = f"Job status is {job.status}"
    
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

    return {"job_id": job_id, "status": job.status, "message": message}


@app.get("/api/research/result/{job_id}", response_model=ResearchResult)
async def get_research_result(job_id: str, db: Session = Depends(get_db)):
    job = db.query(DBJob).filter(DBJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in ['pending', 'running']:
        return JSONResponse(
            status_code=202, 
            content={"job_id": job_id, "status": job.status, "detail": "Job is not yet complete. Please try again later."}
        )

    if job.status == 'failed':
        error = job.result.get('error', 'Unknown error') if job.result else 'Unknown error'
        return JSONResponse(
            status_code=500,
            content={"job_id": job_id, "status": "failed", "error": error}
        )
    
    if job.status != 'completed' or not job.result:
         raise HTTPException(status_code=404, detail="Job result not available.")

    data = job.result
    enhanced_metadata = data.get("metadata", {}).copy()
    if job.upload_to_rag:
        enhanced_metadata['rag_info'] = {
            'upload_requested': True,
            'rag_status': job.rag_status,
            'collection_name': job.rag_collection_name,
            'rag_error': job.rag_error
        }
    
    return ResearchResult(
        job_id=job_id,
        status='completed',
        original_query=data["original_query"],
        final_report_markdown=data["final_report_markdown"],
        extracted_data=_dict_to_extracted_model(data["extracted_data"]),
        metadata=enhanced_metadata
    )


@app.post("/api/rag/query", response_model=RAGQueryResponse)
async def ask_rag_collection(query_request: RAGQueryRequest, db: Session = Depends(get_db)):
    try:
        assert_rag_env()

        # Find the job associated with the collection to get/update chat context
        job = db.query(DBJob).filter(DBJob.rag_collection_name == query_request.collection_name).first()
        if not job:
            raise HTTPException(status_code=404, detail=f"Collection '{query_request.collection_name}' not associated with any known job.")

        # Pass the current context from the DB
        answer_payload = query_rag_collection(
            collection_name=query_request.collection_name,
            question=query_request.question,
            current_chat_context=job.rag_chat_context # Pass current context
        )

        # Update the chat context in the DB
        if answer_payload and 'chat_context' in answer_payload:
            new_fragment = answer_payload['chat_context']
            separator = " " if job.rag_chat_context else ""
            job.rag_chat_context += separator + new_fragment
            db.commit()

        return RAGQueryResponse(
            collection_name=query_request.collection_name,
            question=query_request.question,
            answer=answer_payload
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"RAG system not properly configured: {str(e)}")
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else 500
        error_detail = e.response.text if e.response else str(e)
        raise HTTPException(status_code=status_code, detail=f"Error from RAG API: {error_detail}")
    except Exception as e:
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