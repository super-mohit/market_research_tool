# src/phase2_searcher.py  (fully rewritten)

import asyncio, re, time, logging
import httpx
from datetime import date
from src import config, constants

CSE_ENDPOINT = "https://customsearch.googleapis.com/customsearch/v1"

async def _single_cse(client: httpx.AsyncClient, query: str, bucket: str,
                      num_results: int, idx: int) -> list[tuple[str, str]]:
    """Fire one CSE request, return (url, bucket) pairs."""
    year_from = date.today().year - constants.RECENT_YEARS
    params = {
        "q": query,
        "cx": config.GOOGLE_CSE_ID,
        "key": config.GOOGLE_API_KEY,
        "num": num_results,
        "sort": f"date:r:{year_from}0101:{date.today():%Y%m%d}",
    }
    try:
        r = await client.get(CSE_ENDPOINT, params=params, timeout=20)
        r.raise_for_status()
        items = r.json().get("items", [])
        return [(it["link"], bucket) for it in items]
    except httpx.HTTPStatusError as e:
        # retry once without the sort parameter on 400
        if e.response.status_code == 400 and "sort" in params:
            params.pop("sort", None)
            r = await client.get(CSE_ENDPOINT, params=params, timeout=20)
            r.raise_for_status()
            items = r.json().get("items", [])
            return [(it["link"], bucket) for it in items]
        logging.warning(f"CSE error {e.response.status_code} for query #{idx}: {query[:60]}")
    except Exception as e:
        logging.warning(f"{e} on query #{idx}")
    return []

async def execute_cse_searches(queries_by_type: dict[str, list[str]],
                               num_results: int = constants.MAX_SEARCH_RESULTS,
                               max_concurrency: int = constants.MAX_SEARCH_WORKERS
                               ) -> list[tuple[str, str]]:
    """
    Fully asynchronous Google CSE runner.  No thread pools, HTTP/2, 1-RTT.
    Returns deduped (url, bucket) list.
    """
    flat: list[tuple[str, str]] = [
        (bucket, q) for bucket, lst in queries_by_type.items() for q in lst
    ]
    if not flat:
        return []

    t0 = time.perf_counter()
    tagset: set[tuple[str, str]] = set()

    limits = httpx.Limits(max_connections=max_concurrency, max_keepalive_connections=max_concurrency)
    async with httpx.AsyncClient(http2=True, limits=limits) as client:
        sem = asyncio.Semaphore(max_concurrency)

        async def _wrapped(i, bucket, query):
            async with sem:
                return await _single_cse(client, query, bucket, num_results, i)

        tasks = [
            asyncio.create_task(_wrapped(i, bucket, query))
            for i, (bucket, query) in enumerate(flat)
        ]
        for coro in asyncio.as_completed(tasks):
            for link, bucket in await coro:
                tagset.add((link, bucket))

    elapsed = time.perf_counter() - t0
    logging.info(f"Phase 2 – {len(tagset)} unique URLs in {elapsed:0.1f}s "
          f"({len(flat)} queries, {max_concurrency} concurrency)")
    return list(tagset)