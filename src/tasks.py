# File: src/tasks.py (NEW FILE)
import asyncio
import logging
import time
from celery_worker import celery_app # Import our Celery app instance
from api.sheets_logger import log_to_sheets # <-- Add this import

# --- All the imports from the original run_and_store_results function ---
from database.session import SessionLocal
from database.models import Job as DBJob
from src.main import execute_research_pipeline
from src.rag_uploader import upload_artifacts_to_rag
import threading

# Define the task using the @celery_app.task decorator
@celery_app.task(name="run_research_pipeline_task")
def run_research_pipeline_task(job_id: str, query: str, should_upload_to_rag: bool):
    """
    This is the Celery task that executes the full research pipeline.
    It's the same logic as the old background task, but now it runs in a Celery worker.
    """
    logging.info(f"Celery task started for job_id: {job_id}")
    start_time = time.time() # <-- Track start time
    db = SessionLocal()
    try:
        job = db.query(DBJob).filter(DBJob.id == job_id).first()
        if not job:
            logging.error(f"Job {job_id} not found in DB for Celery task. Aborting.")
            return

        logging.info(f"Job {job_id}: Starting research pipeline...")
        job.status = 'running'
        job.job_stage = 'initializing'
        job.job_progress = 5
        db.commit()

        # --- This status callback is the same as before ---
        async def update_status_in_db(stage: str = None, progress: int = None, message: str = None):
            # This needs its own DB session because it's in an async context
            db_session = SessionLocal()
            try:
                job_to_update = db_session.query(DBJob).filter(DBJob.id == job_id).first()
                if job_to_update:
                    if stage: job_to_update.job_stage = stage
                    if progress: job_to_update.job_progress = progress
                    if message:
                        if job_to_update.logs is None: job_to_update.logs = []
                        job_to_update.logs = job_to_update.logs + [message]
                    db_session.commit()
                    
                    # +++ NEW LOGGING FOR STAGES +++
                    if stage:
                        log_to_sheets(
                            eventType="job_stage_update",
                            jobId=job_id,
                            status="running",
                            stage=stage,
                            details={"progress": progress}
                        )
            finally:
                db_session.close()
            await asyncio.sleep(0)

        # Run the main research pipeline
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result_data = loop.run_until_complete(
                execute_research_pipeline(query, update_status_in_db)
            )
        finally:
            loop.close()
        
        duration = time.time() - start_time # <-- Calculate duration
        
        # +++ NEW LOGGING FOR COMPLETION +++
        log_to_sheets(
            eventType="job_completed",
            jobId=job_id,
            status="completed",
            stage="finished",
            details={"duration_seconds": round(duration, 2)}
        )

        logging.info(f"Job {job_id}: Pipeline completed. Marking as COMPLETED immediately.")
        job.result = result_data
        job.status = 'completed'
        job.job_stage = 'finished'
        job.job_progress = 100
        
        if should_upload_to_rag:
            job.upload_to_rag = True
            job.rag_status = 'pending_upload'
        else:
            job.upload_to_rag = False
            job.rag_status = 'not_requested'
        
        db.commit()
        logging.info(f"Job {job_id}: Status set to COMPLETED in DB.")
        
        # Start RAG upload in a background thread (same logic)
        if should_upload_to_rag:
            logging.info(f"Job {job_id}: Starting RAG upload in background thread...")
            # This part remains identical, using a thread within the Celery worker
            def run_rag_upload():
                try:
                    collection_name = upload_artifacts_to_rag(job_id, result_data)
                    with SessionLocal() as rag_db:
                        rag_job = rag_db.query(DBJob).filter(DBJob.id == job_id).first()
                        if rag_job:
                            if collection_name:
                                rag_job.rag_collection_name = collection_name
                                rag_job.rag_status = 'uploaded'
                                
                                # +++ NEW LOGGING FOR RAG UPLOAD +++
                                log_to_sheets(
                                    eventType="rag_upload_status",
                                    jobId=job_id,
                                    status="success",
                                    ragCollection=collection_name
                                )
                            else:
                                rag_job.rag_status = 'failed'
                                rag_job.rag_error = 'RAG upload returned no collection name'
                                
                                # +++ NEW LOGGING FOR RAG FAILURE +++
                                log_to_sheets(
                                    eventType="rag_upload_status",
                                    jobId=job_id,
                                    status="failed",
                                    errorMessage="Upload returned no collection name"
                                )
                            rag_db.commit()
                except Exception as rag_error:
                    logging.error(f"Job {job_id}: RAG upload failed.", exc_info=True)
                    
                    # +++ NEW LOGGING FOR RAG FAILURE +++
                    log_to_sheets(
                        eventType="rag_upload_status",
                        jobId=job_id,
                        status="failed",
                        errorMessage=str(rag_error)
                    )
                    
                    with SessionLocal() as rag_db:
                        rag_job = rag_db.query(DBJob).filter(DBJob.id == job_id).first()
                        if rag_job:
                            rag_job.rag_status = 'failed'
                            rag_job.rag_error = str(rag_error)
                            rag_db.commit()
            
            rag_thread = threading.Thread(target=run_rag_upload, daemon=True)
            rag_thread.start()
    
    except Exception as e:
        logging.error(f"Job {job_id}: Celery task failed with an unhandled exception.", exc_info=True)
        duration = time.time() - start_time
        
        # +++ NEW LOGGING FOR JOB FAILURE +++
        log_to_sheets(
            eventType="job_failed",
            jobId=job_id,
            status="failed",
            stage=job.job_stage, # Log the stage where it failed
            errorMessage=str(e),
            details={"duration_seconds": round(duration, 2)}
        )
        
        job.status = 'failed'
        job.job_stage = 'error'
        job.job_progress = 0
        job.result = {"error": str(e)}
        db.commit()
    finally:
        db.close() 