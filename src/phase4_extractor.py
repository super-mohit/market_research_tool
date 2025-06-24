#!/usr/bin/env python3
import sys
import os
# Ensure project root is on PYTHONPATH for script execution
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import asyncio
import json
import datetime
from datetime import date
import re
import time
import logging
from google import genai
from google.genai import types
from src import config
from src.constants import MAX_GEMINI_PARALLEL, EXTRACT_BATCH_SIZE
from src import constants
from dateutil import parser as dtparse
from operator import itemgetter

def _is_recent(date_str: str | None) -> bool:
    """
    True ⇢ item year >= (today - RECENT_YEARS)  • False otherwise
    """
    if not date_str:
        return False
    try:
        yr = dtparse.parse(date_str, fuzzy=True).year
        return yr >= date.today().year - constants.RECENT_YEARS
    except (dtparse.ParserError, TypeError):
        return False

# --- New: guarantee every category key exists  ------------------
EXPECTED_CATEGORIES = ["News", "Patents", "Conference", "Legalnews", "Other"]

def _pad_categories(cat_dict: dict) -> dict:
    """Return a dict that has every required category, even if empty."""
    return {k: list(cat_dict.get(k, [])) for k in EXPECTED_CATEGORIES}
# ----------------------------------------------------------------

def extract_data_from_single_url_sync(
    url: str,
    client: genai.Client
) -> list[dict]:
    """
    Uses Gemini to extract structured items (news, Patents, conferences, Legalnews) from a URL.
    Returns parsed list of item dicts.
    """
    logging.info(f"    - Extracting from: {url}")
    try:
        # Get current date for context
        current_date = date.today()
        current_year = current_date.year
        target_years = f"{current_year - constants.RECENT_YEARS + 1}-{current_year}"
        
        instruction = f"""
You are a high-precision, automated data extraction engine. Your sole function is to parse an online document and extract specific, structured information related to the coatings industry. You must be rigorous and discard any item that does not meet the criteria perfectly. Today's date is {current_date.strftime('%Y-%m-%d')}.

**Source URL to Analyze:** {url}

**Extraction Task & Categories:**
From the URL content, extract ONLY English-language items from the last {constants.RECENT_YEARS} years ({target_years}) that fit one of these exact categories:
- **News**: Company announcements, M&A activity, market reports, financial updates.
- **Patents**: Patent applications, grants, or detailed technical whitepapers on novel technology.
- **Conference**: Announcements or summaries of industry events, webinars, or presentations.
- **Legalnews**: Regulatory updates, new chemical standards, or legal cases relevant to coatings.

**JSON Object Field Requirements (MANDATORY):**
For each qualifying item, create a JSON object with these exact 5 fields:
1.  **`type`**: (String) MUST be one of: "News", "Patents", "Conference", "Legalnews".
2.  **`title`**: (String) The official title. If none, create a concise, descriptive title (5-15 words).
3.  **`summary`**: (String, 100-300 words) A self-contained, detailed summary. MUST include key entities (companies, products), quantitative data (percentages, values), and the core finding's significance to the coatings industry.
4.  **`date`**: (String or Null) The publication date in **YYYY-MM-DD** format. If only month/year are available, use the first day (e.g., "2024-05-01"). If the date is outside the {constants.RECENT_YEARS}-year window or cannot be found, this field MUST be `null`.
5.  **`source_url`**: (String) The exact URL: `{url}`

**Rigorous Quality Control Protocol:**
- **Precision is Key:** If an item is ambiguous or its relevance to coatings is weak, **DO NOT** include it. It is better to return an empty array than incorrect data.
- **No Duplicates:** If one article mentions two separate products, create two distinct JSON objects.
- **Validate Dates:** Strictly enforce the recency filter. If an item is too old, do not include it.
- **Strict JSON:** The final output must be a single, valid JSON array `[...]`. No text before or after.

**Final Output Format:**
Return a valid JSON array of objects. Return an empty array `[]` if no qualifying items are found.
"""

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part(text=instruction)
                ],
            )
        ]
        tools = [types.Tool(url_context=types.UrlContext())]
        config_obj = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(
                thinking_budget=-1,
            ),
            tools=tools,
            response_modalities=["TEXT"],
            safety_settings=[
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
            ],
            response_mime_type="text/plain",
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=config_obj,
        )
        
        if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
            logging.warning(f"      → No content part in Gemini response for: {url}")
            return []
            
        text_output = response.candidates[0].content.parts[0].text
        # Clean the response to find the JSON
        match = re.search(r'\[.*\]', text_output, re.DOTALL)
        if not match:
            logging.warning(f"      → No JSON array in response for: {url}\n        Response: {text_output[:100]}...")
            return []
            
        items = json.loads(match.group(0))
        return items if isinstance(items, list) else []

    except json.JSONDecodeError as e:
        logging.error(f"      → JSONDecodeError for URL {url}: {e}")
        return []
    except Exception as e:
        logging.error(f"      → Error processing {url}: {e}", exc_info=True)
        return []

async def run_structured_extraction(
    urls: list[str],
    original_user_query: str,
    url2tag: dict[str,str],
    output_dir: str = "extractions"
) -> dict:
    """
    Parallel extraction with concurrency control using batching.
    Processes all URLs in batches to respect API limits.

    Args:
      urls: List of URLs to extract from (all processed in batches).
      original_user_query: Query string for metadata.
      url2tag: Dictionary mapping URLs to their bucket types.
      output_dir: Directory to save structured JSON.
    Returns:
      Categorized dict of extracted items.
    """
    logging.info(f"\nPhase 4: Extracting structured data from {len(urls)} URLs in batches...")
    os.makedirs(output_dir, exist_ok=True)
    
    # ————— fast concurrent extraction —————
    sem = asyncio.Semaphore(constants.MAX_GEMINI_PARALLEL)
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    async def one(url):
        async with sem:
            # Run the synchronous extraction in a thread executor
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, 
                lambda: extract_data_from_single_url_sync(url, client)
            )

    t0 = time.perf_counter()
    out_lists = await asyncio.gather(*(one(u) for u in urls))
    elapsed = time.perf_counter() - t0
    logging.info(f"✓ Phase 4 – extracted {len(urls)} URLs in {elapsed:0.1f}s "
          f"({constants.MAX_GEMINI_PARALLEL} Gemini workers)")
    
    categorized = {k: [] for k in EXPECTED_CATEGORIES}
    total_items = 0
    
    for items in out_lists:
        for item in items:
            if not _is_recent(item.get("date")):
                # silently drop anything older than RECENT_YEARS
                continue
            
            # --- Add a parsed date for sorting ---
            # We'll parse the date string into a real date object.
            # We add this temporarily and will remove it before saving.
            try:
                # The 'fuzzy=True' helps parse incomplete dates like "2024-05"
                item['_parsed_date'] = dtparse.parse(item.get("date", ""), fuzzy=True)
            except (dtparse.ParserError, TypeError):
                # If date is invalid, default to a very old date so it goes to the bottom.
                item['_parsed_date'] = datetime.datetime(1970, 1, 1)
            
            # When normalising each item - use url2tag for type guessing
            item_type = (item.get("type") or url2tag.get(item.get("source_url"), "Other")) or "Other"
            item["type"] = item_type
            
            t = item.get("type", "Other")
            categorized.setdefault(t if t in EXPECTED_CATEGORIES else "Other", categorized["Other"]).append(item)
            total_items += 1

    # --- Sorting Logic ---
    # Now, iterate through each category and sort its list of items.
    print("    - Sorting extracted items by date...")
    for category in categorized:
        # Sort the list in-place.
        # `itemgetter` is slightly faster than a lambda function.
        # `reverse=True` puts the newest dates first.
        categorized[category].sort(key=itemgetter('_parsed_date'), reverse=True)
        
        # Clean up the temporary '_parsed_date' key from each item.
        for item in categorized[category]:
            del item['_parsed_date']

    # Prepare metadata and write output
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = re.sub(r'\W+', '_', (original_user_query or '')[:50]) or 'structured_extraction'
    filename = f"{timestamp}_{safe_title}.json"
    filepath = os.path.join(output_dir, filename)

    categorized = _pad_categories(categorized)

    urls_processed = len(urls)
    metadata = {
        "timestamp": timestamp,
        "original_query": original_user_query,
        "urls_processed": urls_processed,
        "total_items_extracted": total_items,
        "extraction_summary": {cat: len(lst) for cat, lst in categorized.items()}
    }
    output = {"metadata": metadata, "extracted_data": categorized, "processed_urls": urls}

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"✅ Structured extraction saved to {filepath}")
    print(f"📊 {total_items} items extracted:")
    for cat, lst in categorized.items():
        if lst:
            print(f"   - {cat}: {len(lst)}")

    return output

if __name__ == '__main__':
    sample_urls = [
        "https://www.coatingsworld.com/issues/2025-01-01/view_features/renovations-diy-drive-growth-in-architectural-coatings-market/",
        "https://www.paint.org/wp-content/uploads/dlm_uploads/2020/04/2020-ACA-Sustainability-Report-1.pdf"
    ]
    sample_url2tag = {url: "News" for url in sample_urls}  # Sample mapping
    extracted = asyncio.run(run_structured_extraction(sample_urls, 'Test Extraction', sample_url2tag))
    print("\nFinal extracted data:")
    print(json.dumps(extracted, indent=2)) 