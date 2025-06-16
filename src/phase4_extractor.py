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
from google import genai
from google.genai import types
from src import config
from src.constants import MAX_GEMINI_PARALLEL, EXTRACT_BATCH_SIZE
from src import constants
from dateutil import parser as dtparse

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

async def extract_data_from_single_url(
    url: str,
    client: genai.Client,
    semaphore: asyncio.Semaphore
) -> list[dict]:
    """
    Uses Gemini to extract structured items (news, Patents, conferences, Legalnews) from a URL.
    Throttles concurrency via semaphore. Returns parsed list of item dicts.
    """
    async with semaphore:
        print(f"    - Extracting from: {url}")
        try:
            # Get current date for context
            current_date = date.today()
            current_year = current_date.year
            target_years = f"{current_year - constants.RECENT_YEARS + 1}-{current_year}"
            
            instruction = (
                f"You are a data extraction specialist for the global coatings industry. "
                f"Today is {current_date.strftime('%B %d, %Y')}.\n\n"
                
                f"**TARGET URL:** {url}\n\n"
                
                "**EXTRACTION TASK:**\n"
                "Extract ONLY ENGLISH-language items from the above URL that fall into these categories:\n"
                "• **News** - Industry news, company announcements, market updates\n"
                "• **Patents** - Patent applications, grants, IP developments\n"
                "• **Conference** - Industry events, conferences, presentations, webinars\n"
                "• **Legalnews** - Regulatory updates, compliance news, legal developments\n\n"
                
                "**TEMPORAL FILTER:**\n"
                f"Include ONLY items published from {target_years} (last {constants.RECENT_YEARS} years).\n"
                "Exclude anything older than this timeframe.\n\n"
                
                "**FIELD REQUIREMENTS:**\n"
                "For each qualifying item, extract exactly these 5 fields:\n\n"
                
                "1. **type** - One of: 'News', 'Patents', 'Conference', 'Legalnews'\n"
                "   - Use the most appropriate category based on content\n"
                "   - When uncertain, prioritize based on primary focus\n\n"
                
                "2. **title** - Clear, descriptive headline (50-100 characters)\n"
                "   - Use original title if available, otherwise create concise summary title\n"
                "   - Focus on coatings-relevant aspects\n\n"
                
                "3. **summary** - Comprehensive summary (100-300 words)\n"
                "   - Include key technical details, market impact, company names\n"
                "   - Quantify when possible (market size, percentages, dates)\n"
                "   - Highlight coatings industry relevance\n\n"
                
                "4. **date** - Publication date in ISO format (YYYY-MM-DD)\n"
                "   - Use exact publication date if available\n"
                "   - If only month/year available, use first day of month\n"
                "   - Skip items without determinable date\n\n"
                
                "5. **source_url** - The exact URL being analyzed\n"
                f"   - Use: {url}\n\n"
                
                "**QUALITY STANDARDS:**\n"
                "• Focus on items directly relevant to coatings, paints, adhesives, sealants\n"
                "• Prioritize items with quantitative data or specific technical details\n"
                "• Exclude generic business news unless coatings-specific\n"
                "• Ensure summaries are substantive and informative\n"
                "• Verify dates meet the temporal filter requirements\n\n"
                
                "**OUTPUT FORMAT:**\n"
                "Return a valid JSON array. Each object must have exactly the 5 fields above.\n"
                "Return [] (empty array) if no qualifying items are found.\n"
                "Example structure:\n"
                "[\n"
                '  {\n'
                '    "type": "News",\n'
                '    "title": "New Anti-Corrosion Coating Technology...",\n'
                '    "summary": "Company X announced a breakthrough...",\n'
                '    "date": "2024-03-15",\n'
                f'    "source_url": "{url}"\n'
                '  }\n'
                "]"
            )

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
                tools=tools,
                response_modalities=["TEXT"],
                safety_settings=[
                    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                ],
            )
            response = await client.aio.models.generate_content(
                model="gemini-2.5-pro-preview-06-05",
                contents=contents,
                config=config_obj,
            )
            
            if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
                print(f"      → No content part in Gemini response for: {url}")
                return []
                
            text_output = response.candidates[0].content.parts[0].text.strip()
            # Extract the JSON array substring
            match = re.search(r"\[.*\]", text_output, re.S)
            if not match:
                print(f"      → No JSON array in response for: {url}\n        Response: {text_output[:100]}...")
                return []
            items = json.loads(match.group(0))
            return items if isinstance(items, list) else []

        except json.JSONDecodeError as e:
            print(f"      → JSONDecodeError for URL {url}: {e}")
            return []
        except Exception as e:
            print(f"      → Error processing {url}: {e}")
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
    print(f"\nPhase 4: Extracting structured data from {len(urls)} URLs in batches...")
    os.makedirs(output_dir, exist_ok=True)
    
    semaphore = asyncio.Semaphore(MAX_GEMINI_PARALLEL)

    BATCH = EXTRACT_BATCH_SIZE
    batches = [urls[i:i+BATCH] for i in range(0, len(urls), BATCH)]
    
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    categorized = {k: [] for k in EXPECTED_CATEGORIES}
    total_items = 0
    
    # Process each batch
    for batch_idx, batch_urls in enumerate(batches):
        print(f"  Processing batch {batch_idx + 1}/{len(batches)} ({len(batch_urls)} URLs)...")
        
        # Launch all tasks for this batch
        tasks = [
            asyncio.create_task(extract_data_from_single_url(u, client, semaphore))
            for u in batch_urls
        ]

        # Collect results as each finishes (parallel)
        for completed in asyncio.as_completed(tasks):
            items = await completed
            for item in items:
                if not _is_recent(item.get("date")):
                    # silently drop anything older than RECENT_YEARS
                    continue
                # When normalising each item - use url2tag for type guessing
                item_type = (item.get("type") or url2tag.get(item.get("source_url"), "Other")) or "Other"
                item["type"] = item_type
                
                t = item.get("type", "Other")
                categorized.setdefault(t if t in EXPECTED_CATEGORIES else "Other", categorized["Other"]).append(item)
                total_items += 1

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
