# src/phase2_searcher.py

from concurrent.futures import ThreadPoolExecutor, as_completed
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from src import config
from src.constants import MAX_SEARCH_RESULTS, MAX_SEARCH_WORKERS
from src import constants
from datetime import date
import threading
import time
import collections

# Thread-local storage for service instances
_thread_local = threading.local()

def _get_service():
    """
    Get or create a thread-local Google Custom Search service instance.
    This ensures each thread has its own service object.
    """
    if not hasattr(_thread_local, 'service'):
        _thread_local.service = build(
            "customsearch", "v1", developerKey=config.GOOGLE_API_KEY
        )
    return _thread_local.service

def _execute_single_query(query_info: tuple) -> tuple:
    """
    Execute a single search query and return results.
    
    Args:
        query_info: Tuple of (query_index, bucket, query_string, num_results)
    
    Returns:
        Tuple of (query_index, bucket, query_string, urls_list, error_message)
    """
    query_index, bucket, query, num_results = query_info
    urls = []
    error_msg = None
    
    try:
        service = _get_service()
        year_from = date.today().year - constants.RECENT_YEARS
        sort_range = f"date:r:{year_from}0101:{date.today().strftime('%Y%m%d')}"

        # First attempt
        try:
            res = service.cse().list(
                q=query,
                cx=config.GOOGLE_CSE_ID,
                num=num_results,
                sort=sort_range
            ).execute()
        except HttpError as http_err:
                if http_err.resp.status == 400:
                    # Retry without sort param if 400 error
                    res = service.cse().list(
                        q=query,
                        cx=config.GOOGLE_CSE_ID,
                        num=num_results
                    ).execute()
                elif http_err.resp.status == 503:
                    print(f"    -> 503 error for query '{query}', retrying once...")
                    time.sleep(1)  # Brief pause before retry
                    res = service.cse().list(
                        q=query,
                        cx=config.GOOGLE_CSE_ID,
                        num=num_results,
                        sort=sort_range
                    ).execute()
                else:
                    # Re-raise other HTTP errors
                    raise http_err
        
        # Extract the 'link' from each search item
        if 'items' in res:
            urls = [item['link'] for item in res['items']]
        
    except Exception as e:
        error_msg = str(e)
    
    # Tag each URL with its bucket
    tagged = [(link, bucket) for link in urls]
    
    return query_index, bucket, query, tagged, error_msg

def execute_cse_searches(
    queries_by_type: dict[str, list[str]],
    num_results: int = MAX_SEARCH_RESULTS,
    max_workers: int = MAX_SEARCH_WORKERS
) -> list[tuple[str, str]]:      # (url, guessed_type)
    """
    Executes bucketed searches using Google Custom Search Engine (CSE) API in parallel.

    Args:
        queries_by_type: A dictionary of search query strings organized by type/bucket.
        num_results: The number of results to fetch for each query.
        max_workers: Maximum number of parallel threads for search execution.

    Returns:
        A list of unique (URL, bucket_type) tuples.
    """
    # Flatten queries for thread pool execution
    flat = [(bucket, q) for bucket, lst in queries_by_type.items() for q in lst]
    
    print(f"\nPhase 2: Executing {len(flat)} searches with Google CSE (parallel with {max_workers} workers)...")
    
    # Validate that we can build a service first
    try:
        # Test service creation
        test_service = build("customsearch", "v1", developerKey=config.GOOGLE_API_KEY)
    except Exception as e:
        print(f"FATAL: Could not build Google Search client. Error: {e}")
        return []

    all_tagged_urls: dict[str, set[str]] = collections.defaultdict(set)
    
    # Prepare query information for parallel execution
    query_infos = [(i, bucket, query, num_results) for i, (bucket, query) in enumerate(flat)]
    
    # Execute searches in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all queries
        future_to_query = {
            executor.submit(_execute_single_query, query_info): query_info 
            for query_info in query_infos
        }
        
        # Process completed queries as they finish
        for future in as_completed(future_to_query):
            query_info = future_to_query[future]
            query_index, bucket, query, tagged_urls, error_msg = future.result()
            
            print(f"  - Completed ({query_index + 1}/{len(flat)}): \"{query}\" [{bucket}]")
            
            if error_msg:
                print(f"    -> Error: {error_msg}")
            elif tagged_urls:
                for link, bucket in tagged_urls:
                    all_tagged_urls[bucket].add(link)
                print(f"    -> Found {len(tagged_urls)} URLs")
            else:
                print(f"    -> No results found")

    # flatten
    unique_tagged_urls = [(u, b) for b, urls in all_tagged_urls.items() for u in urls]
    print(f"Successfully collected {len(unique_tagged_urls)} unique tagged URLs from parallel execution.")
    return unique_tagged_urls