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

async def execute_research_pipeline(
    user_query: str, 
    update_status: Callable
) -> dict:
    """
    OPTIMIZED: Pipeline with better parallelization.
    """
    assert_all_env()
    start_time = time.perf_counter()
    print(f"--- Starting Optimized Pipeline for query: '{user_query[:50]}...' ---")
    
    # Phase 1 & 2 unchanged...
    await update_status(stage="planning", progress=10, message="Analyzing request and planning search strategies...")
    search_queries = generate_search_queries(user_query)
    if not search_queries:
        raise ValueError("Pipeline Error: No search queries were generated.")
    
    total_queries = sum(len(queries) for queries in search_queries.values())
    print(f"-> Phase 1 Complete: {total_queries} queries generated.")
    
    await update_status(stage="searching", progress=25, message=f"Scouring {total_queries} web sources...")
    tagged_urls = await execute_cse_searches(search_queries)
    if not tagged_urls:
        raise ValueError("Pipeline Error: No URLs were collected from search.")
    
    print(f"-> Phase 2 Complete: {len(tagged_urls)} URLs collected.")
    
    # Prepare URL buckets
    bucketed: dict[str, list[str]] = {}
    for url, bucket in tagged_urls:
        bucketed.setdefault(bucket, []).append(url)

    general_urls = bucketed.get("General", [])[:MAX_GENERAL_FOR_REPORT]
    news_urls = bucketed.get("News", [])[:MAX_PER_BUCKET_EXTRACT]
    patents_urls = bucketed.get("Patents", [])[:MAX_PER_BUCKET_EXTRACT]
    conf_urls = bucketed.get("Conference", [])[:MAX_PER_BUCKET_EXTRACT]
    legalnews_urls = bucketed.get("Legalnews", [])[:MAX_PER_BUCKET_EXTRACT]

    report_urls = general_urls
    extract_urls = news_urls + patents_urls + conf_urls + legalnews_urls
    url2tag = {u: "News" for u in news_urls} | \
              {u: "Patents" for u in patents_urls} | \
              {u: "Conference" for u in conf_urls} | \
              {u: "Legalnews" for u in legalnews_urls}
    
    print(f"-> URL Distribution: Report={len(report_urls)}, Extract={len(extract_urls)}")

    # 🔥 CRITICAL CHANGE: Start extraction and synthesis in parallel
    await update_status(stage="synthesizing", progress=50, message="Starting parallel analysis...")
    
    # Start extraction immediately
    extraction_task = asyncio.create_task(
        run_structured_extraction(extract_urls, user_query, url2tag)
    )
    
    # Start intermediate synthesis in parallel
    url_batches = [report_urls[i:i+15] for i in range(0, len(report_urls), 15)]
    intermediate_reports_task = asyncio.get_event_loop().run_in_executor(
        ThreadPoolExecutor(1),
        synthesize_all_intermediate_reports,
        user_query,
        url_batches,
        "reports/intermediate_reports",
        True,
        MAX_BATCH_WORKERS
    )
    
    # Wait for both to complete
    print("-> Running extraction and synthesis in parallel...")
    intermediate_reports, extraction_payload = await asyncio.gather(
        intermediate_reports_task,
        extraction_task
    )
    
    print(f"-> Parallel processing complete.")
    
    # Final synthesis
    await update_status(stage="compiling", progress=85, message="Generating final report...")
    final_report_path = await asyncio.get_event_loop().run_in_executor(
        ThreadPoolExecutor(1),
        synthesize_final_report,
        user_query,
        intermediate_reports,
        report_urls
    )
    
    # Read final report
    try:
        with open(final_report_path, 'r', encoding='utf-8') as f:
            final_report_content = f.read()
    except FileNotFoundError:
        final_report_content = "Error: Final report could not be generated or found."

    elapsed = time.perf_counter() - start_time
    print(f"--- Optimized Pipeline complete in {elapsed:.2f} seconds ---")

    return {
        "original_query": user_query,
        "final_report_markdown": final_report_content,
        "intermediate_reports": intermediate_reports,
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