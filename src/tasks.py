# File: src/tasks.py (REVISED AND FINAL)
import asyncio
import logging
import time
from celery_worker import celery_app
from api.sheets_logger import log_to_sheets

from database.session import SessionLocal
from database.models import Job as DBJob
from src.main import execute_research_pipeline
from src.rag_uploader import upload_artifacts_to_rag
from src.phase6_visual_synthesizer import generate_overview_data
from src.phase7_strategist import generate_strategic_insights

@celery_app.task(name="run_research_pipeline_task")
def run_research_pipeline_task(job_id: str, query: str, should_upload_to_rag: bool):
    """
    Celery task that executes the full research, visualization, and strategy pipeline.
    This version correctly handles RAG uploads synchronously and uses asyncio.run().
    """
    logging.info(f"Celery task started for job_id: {job_id}")
    db = SessionLocal()
    job = None  # Initialize job to None
    try:
        job = db.query(DBJob).filter(DBJob.id == job_id).first()
        if not job:
            logging.error(f"Job {job_id} not found in DB. Aborting.")
            return

        # +++ GET COMPANY INFO FROM THE JOB'S USER +++
        user = job.owner
        if not user or not user.company_name:
            logging.warning(f"Job {job_id} owner or company name not found. Using default profile.")
            company_name = "the client company"
            company_profile = "A company in the coatings industry."
        else:
            # Using the exact profile provided in the prompt
            company_name = user.company_name
            company_profile = "A leading global chemical company seeking to enhance its market intelligence capabilities. Their business teams need a solution that enables them to efficiently gather, synthesize, and analyze up-to-date information on market trends, innovations, and competitive activity—specifically from trusted, industry-relevant sources. The solution must focus on topics critical to the decorative coatings sector, such as weatherability, scuff-resistance, hydrophobicity, and sustainability, and support the needs of global business and R&D teams."

        job.status = 'running'
        job.job_stage = 'initializing'
        job.job_progress = 5
        db.commit()

        # This async helper function will be passed to the pipeline
        async def update_status_in_db(stage: str = None, progress: int = None, message: str = None):
            with SessionLocal() as s:
                job_to_update = s.query(DBJob).filter(DBJob.id == job_id).first()
                if job_to_update:
                    if stage: job_to_update.job_stage = stage
                    if progress: job_to_update.job_progress = progress
                    if message:
                        job_to_update.logs = (job_to_update.logs or []) + [message]
                    s.commit()
            await asyncio.sleep(0.01)

        # Replace the manual loop management with a single call to asyncio.run()
        result_data = asyncio.run(
            execute_research_pipeline(query, update_status_in_db)
        )
        
        # Run Visual Synthesizer
        asyncio.run(update_status_in_db(stage="generating_visuals", progress=85, message="Creating visual dashboard data..."))
        try:
            overview_data = generate_overview_data(
                result_data.get('final_report_markdown', ''),
                result_data.get('extracted_data', {})
            )
            result_data['overview_data'] = overview_data
            logging.info(f"Job {job_id}: Successfully generated overview data.")
        except Exception as e:
            logging.error(f"Job {job_id}: Failed to generate overview data. Error: {e}", exc_info=True)
            result_data['overview_data'] = None

        # +++ RUN STRATEGIC SYNTHESIZER +++
        asyncio.run(update_status_in_db(stage="generating_strategy", progress=95, message=f"Generating personalized strategy for {company_name}..."))
        try:
            strategic_data = generate_strategic_insights(
                final_report_md=result_data.get('final_report_markdown', ''),
                structured_data=result_data.get('extracted_data', {}),
                original_query=query,
                company_name=company_name,
                company_profile=company_profile
            )
            result_data['strategic_insights'] = strategic_data
            logging.info(f"Job {job_id}: Successfully generated strategic insights.")
        except Exception as e:
            logging.error(f"Job {job_id}: Failed to generate strategic insights. Error: {e}", exc_info=True)
            result_data['strategic_insights'] = {"error": "Strategy generation failed."}

        # Update job as completed BEFORE potential RAG upload
        job = db.query(DBJob).filter(DBJob.id == job_id).first() # Re-fetch job to be safe
        job.result = result_data
        job.status = 'completed'
        job.job_stage = 'finished'
        job.job_progress = 100
        if should_upload_to_rag:
            job.rag_status = 'uploading'
        else:
            job.rag_status = 'not_requested'
        db.commit()
        
        # Handle RAG Upload Sequentially
        if should_upload_to_rag:
            logging.info(f"Job {job_id}: Starting RAG upload process...")
            collection_name = upload_artifacts_to_rag(job_id, result_data)
            
            job = db.query(DBJob).filter(DBJob.id == job_id).first() # Re-fetch again
            if collection_name:
                job.rag_status = 'uploaded'
                job.rag_collection_name = collection_name
                job.rag_error = None
                logging.info(f"Job {job_id}: RAG upload successful. Status updated to 'uploaded'.")
            else:
                job.rag_status = 'failed'
                job.rag_error = "RAG upload process failed. Check worker logs."
                logging.error(f"Job {job_id}: RAG upload failed. Status updated to 'failed'.")
            
            db.commit()

    except Exception as e:
        logging.error(f"Job {job_id}: Celery task failed.", exc_info=True)
        # Ensure job is not None before trying to update it
        if job:
            job.status = 'failed'
            job.job_stage = 'error'
            job.job_progress = 0
            job.result = {"error": str(e)}
            db.commit()
    finally:
        db.close() 