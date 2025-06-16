# src/main.py (Refactored)
import json
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
import os
from typing import Callable, Any  # <-- Import Callable and Any

# Keep all your existing phase imports
from src.phase1_planner import generate_search_queries
from src.phase2_searcher import execute_cse_searches
from src.phase3_intermediate_synthesizer import synthesize_all_intermediate_reports
from src.phase5_final_synthesizer import synthesize_final_report
from src.phase4_extractor import run_structured_extraction
from src.constants import MAX_SEARCH_WORKERS, MAX_GENERAL_FOR_REPORT, MAX_PER_BUCKET_EXTRACT
from src.config import assert_all_env

# Configuration: adjust parallelism limits
MAX_BATCH_WORKERS = 6

# --- NEW: Update function signature to accept a callback ---
async def execute_research_pipeline(
    user_query: str, 
    update_status: Callable # The signature is more complex now, so we simplify for typing
) -> dict:
    """
    Orchestrates the market research pipeline and returns a structured result.
    This is the core logic called by the API background task.
    """
    assert_all_env()
    start_time = time.perf_counter()
    print(f"--- Starting Pipeline for query: '{user_query[:50]}...' ---")
    await update_status(stage="planning", progress=10, message="Analyzing request and planning search strategies...")

    # Phase 1: Generate search queries
    search_queries = generate_search_queries(user_query)
    if not search_queries:
        raise ValueError("Pipeline Error: No search queries were generated.")
    total_queries = sum(len(queries) for queries in search_queries.values())
    print(f"-> Phase 1 Complete: {total_queries} queries generated across {len(search_queries)} buckets.")
    
    await update_status(stage="searching", progress=25, message=f"Scouring {total_queries} web sources...")

    # Phase 2: Execute CSE searches
    # after – call the new async func directly
    tagged_urls = await execute_cse_searches(search_queries)
    if not tagged_urls:
        raise ValueError("Pipeline Error: No URLs were collected from search.")
    
    print(f"-> Phase 2 Complete: {len(tagged_urls)} URLs collected across buckets.")
    await update_status(stage="synthesizing", progress=50, message=f"Analyzing {len(tagged_urls)} collected documents...")

    # 2-a: Collect bucketed URLs once
    # tagged_urls is List[Tuple[url, bucket]]
    bucketed: dict[str, list[str]] = {}
    for url, bucket in tagged_urls:
        bucketed.setdefault(bucket, []).append(url)

    general_urls = bucketed.get("General", [])[:MAX_GENERAL_FOR_REPORT]   # 30 max
    news_urls = bucketed.get("News", [])[:MAX_PER_BUCKET_EXTRACT]
    Patents_urls = bucketed.get("Patents", [])[:MAX_PER_BUCKET_EXTRACT]
    conf_urls = bucketed.get("Conference", [])[:MAX_PER_BUCKET_EXTRACT]
    Legalnews_urls = bucketed.get("Legalnews", [])[:MAX_PER_BUCKET_EXTRACT]

    # --- 1️⃣ URL set for the *intermediate & final* report
    report_urls = general_urls

    # --- 2️⃣ URL set for the *structured extractor*
    extract_urls = news_urls + Patents_urls + conf_urls + Legalnews_urls

    # fast look-up for guessed types (only what we pass to extractor)
    url2tag = {u: "News" for u in news_urls} | \
              {u: "Patents" for u in Patents_urls} | \
              {u: "Conference" for u in conf_urls} | \
              {u: "Legalnews" for u in Legalnews_urls}
    
    print(f"-> URL Distribution: General={len(general_urls)}, News={len(news_urls)}, Patents={len(Patents_urls)}, Conference={len(conf_urls)}, Legalnews={len(Legalnews_urls)}")
    print(f"-> Report URLs: {len(report_urls)}, Extract URLs: {len(extract_urls)}")

    # Phase 3: Intermediate reports (using only general URLs)
    url_batches = [report_urls[i:i+15] for i in range(0, len(report_urls), 15)]
    intermediate_reports = synthesize_all_intermediate_reports(
        original_user_query=user_query,
        url_batches=url_batches,
        use_parallel=True,
        max_workers=MAX_BATCH_WORKERS
    )
    print(f"-> Phase 3 Complete: {len(intermediate_reports)} intermediate reports generated.")
    await update_status(stage="extracting", progress=75, message="Organizing findings into structured data...")

    # Phase 4 & 5: Run final synthesis and structured extraction concurrently
    print("-> Starting final report synthesis and data extraction in parallel...")
    await update_status(stage="compiling", progress=90, message="Generating the final executive report...")

    final_report_task = asyncio.get_event_loop().run_in_executor(
        ThreadPoolExecutor(1),
        synthesize_final_report,
        user_query,
        intermediate_reports,
        report_urls        # <-- not *all* URLs anymore
    )
    # The extraction function returns the full extraction dictionary including metadata
    extraction_task = run_structured_extraction(
        extract_urls,
        user_query,
        url2tag          # <-- new positional arg
    )

    # Await results
    final_report_path, extraction_payload = await asyncio.gather(
        final_report_task,
        extraction_task
    )
    
    # Read the final report content from the saved file
    try:
        with open(final_report_path, 'r', encoding='utf-8') as f:
            final_report_content = f.read()
    except FileNotFoundError:
        print(f"Warning: Could not find final report file at {final_report_path}")
        final_report_content = "Error: Final report could not be generated or found."


    elapsed = time.perf_counter() - start_time
    print(f"--- Pipeline complete in {elapsed:.2f} seconds ---")

    # This is the crucial change: return a structured dictionary INCLUDING intermediate_reports
    return {
        "original_query": user_query,
        "final_report_markdown": final_report_content,
        "intermediate_reports": intermediate_reports,  # Added this for RAG uploader
        "metadata": extraction_payload["metadata"],
        "extracted_data": extraction_payload["extracted_data"],
    }


# This block is for standalone testing if you ever need it
if __name__ == "__main__":
    USER_QUERY = """Show me the latest innovations in Weatherability of Decorative Coatings.
What trends are emerging in the Sustainability of industrial coatings in 2025?
Find recent conferences or Patents discussing Scuff-Resistance in coatings.

Search tags/topics - Product, coating, architectural or similar.

Datasources/URLs (https://www.paint.org/ , https://www.coatingsworld.com/ , https://www.pcimag.com/ )"""
    
    async def main():
        # Dummy callback for standalone testing
        async def dummy_callback(stage: str, progress: int, message: str):
            print(f"[{progress}%] {stage}: {message}")
        
        try:
            results = await execute_research_pipeline(USER_QUERY, dummy_callback)
            print("\n\n--- PIPELINE RESULT ---")
            print("\n## FINAL REPORT (Snippet) ##")
            print(results['final_report_markdown'][:500] + "...")
            print("\n## EXTRACTED DATA (Summary) ##")
            print(json.dumps(results['metadata']['extraction_summary'], indent=2))
        except Exception as e:
            print(f"An error occurred: {e}")

    asyncio.run(main())