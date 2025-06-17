# src/phase3_intermediate_synthesizer.py

import os
import re
import datetime
import logging
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple
from google import genai
from google.genai import types
from src import config
from src import constants
import hashlib

def synthesize_intermediate_report(
    original_user_query: str,
    urls_batch: list[str],
    batch_index: int = 0,
    output_dir: str = "reports/intermediate_reports"
) -> str:
    """
    Generates a focused Markdown sub-report for a given URL batch using Gemini's UrlContext.
    """
    if not urls_batch:
        logging.info(f"    - Batch {batch_index}: No URLs provided — skipping.")
        return ""

    logging.info(f"    - Batch {batch_index}: Synthesizing {len(urls_batch)} URLs...")

    client = genai.Client(api_key=config.GEMINI_API_KEY)

    # Get current date for context
    current_date = date.today()
    current_year = current_date.year
    target_years = f"{current_year - constants.RECENT_YEARS + 1}-{current_year}"

    system_instruction = (
        f"You are a senior market intelligence analyst at a leading chemical company like PPG or Sherwin-Williams. "
        f"Your audience is an R&D Director or a Business Unit Manager. They are technically savvy and time-poor. "
        f"They need to know the 'so what?' of the information presented. Today is {current_date.strftime('%B %d, %Y')}.\n\n"
        
        "**MISSION: Distill raw intelligence into a concise, data-driven sub-report.**\n"
        f"Work exclusively from the provided URLs. Focus on information from the last {constants.RECENT_YEARS} years ({target_years}).\n\n"
        
        "**REQUIRED REPORT STRUCTURE:**\n"
        "Synthesize your findings into the following Markdown structure. For each point, focus on its significance.\n\n"
        
        "1. **Top-Line Summary** (2-3 crucial sentences)\n"
        "   - What is the single most important takeaway from these sources for our business?\n\n"
        
        "2. **Key Technical & Performance Data**\n"
        "   - Extract specific performance metrics, test results (e.g., ASTM standards), and chemical formulations.\n"
        "   - Note any quantitative improvements mentioned (e.g., '30% increase in scuff resistance').\n"
        "   - **Implication:** Does this represent a threat to our existing products or an opportunity for innovation?\n\n"
        
        "3. **Market & Competitive Intelligence**\n"
        "   - Identify market size/growth figures, and any mention of competitor activities (e.g., product launches, plant openings by AkzoNobel, BASF, etc.).\n"
        "   - **Implication:** How does this shift the competitive landscape?\n\n"
        
        "4. **Sustainability & Regulatory Impact**\n"
        "   - Pinpoint new regulations (e.g., VOC limits) or sustainability initiatives (e.g., bio-based content, circular economy).\n"
        "   - **Implication:** What are the product development or compliance consequences for us?\n\n"
        
        "**QUALITY & TONE STANDARDS:**\n"
        "• **Lead with Data:** Prioritize numbers, percentages, and dates. If a source quantifies something, you must include it.\n"
        "• **Objective & Analytical Tone:** Avoid marketing fluff. Be direct and factual.\n"
        "• **Note Contradictions:** If sources conflict, state the discrepancy clearly.\n"
        "• **Cite Your Work:** Use inline numeric citations `[1]`, `[2]` corresponding to the URL list. Do not add a final reference list.\n\n"
        
        "**OUTPUT:** A dense, actionable Markdown report that empowers a manager to make an informed decision."
    )

    # Combine system instruction with user instruction since Gemini only accepts "user" and "model" roles
    combined_instruction = (
        f"{system_instruction}\n\n"
        f"**RESEARCH QUERY:** {original_user_query}\n\n"
        f"**SOURCE URLS (Batch {batch_index}):**\n" +
        "\n".join(f"{i+1}. {url}" for i, url in enumerate(urls_batch)) +
        "\n\n**TASK:** Analyze these sources and generate a comprehensive market intelligence sub-report following the structure above."
    )

    contents = [
        types.Content(role="user", parts=[types.Part(text=combined_instruction)])
    ]

    tools = [types.Tool(url_context=types.UrlContext())]
    config_obj = types.GenerateContentConfig(
        tools=tools,
        safety_settings=[
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_MEDIUM_AND_ABOVE"),
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_MEDIUM_AND_ABOVE"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_MEDIUM_AND_ABOVE"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_MEDIUM_AND_ABOVE"),
        ],
        response_modalities=["TEXT"],
    )

    report_fragments = []
    try:
        stream = client.models.generate_content_stream(
            model="models/gemini-2.5-flash-preview-05-20",
            contents=contents,
            config=config_obj,
        )
        for chunk in stream:
            report_fragments.append(chunk.text)
        intermediate_md = "".join(report_fragments).strip()

        # Save sub-report
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = hashlib.sha1(original_user_query.encode()).hexdigest()[:16]
        path = os.path.join(output_dir, f"{ts}_batch{batch_index}_{safe_name}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"## Batch {batch_index} Intermediate Report\n\n")
            f.write(intermediate_md)
        logging.info(f"    - Batch {batch_index}: sub-report saved → {path}")
        return intermediate_md

    except Exception as e:
        err = f"## Batch {batch_index} – Error during synthesis:\n{e}"
        logging.error(f"    - {err}")
        return err


def synthesize_intermediate_reports_parallel(
    original_user_query: str,
    url_batches: List[List[str]],
    output_dir: str = "reports/intermediate_reports",
    max_workers: int = None
) -> List[Tuple[int, str]]:
    """
    Generates multiple intermediate reports in parallel for given URL batches using Gemini's UrlContext.
    
    Args:
        original_user_query: The original research query
        url_batches: List of URL batches to process in parallel
        output_dir: Directory to save intermediate reports
        max_workers: Maximum number of parallel workers (defaults to min(len(batches), 8))
    
    Returns:
        List of tuples containing (batch_index, report_content)
    """
    if not url_batches:
        logging.info("No URL batches provided for parallel processing.")
        return []

    # Calculate optimal number of workers
    if max_workers is None:
        max_workers = min(len(url_batches), 8)  # Cap at 8 to avoid overwhelming the API
    
    logging.info(f"Starting parallel synthesis of {len(url_batches)} batches with {max_workers} workers...")
    
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all batch processing tasks
        future_to_batch = {}
        for batch_index, urls_batch in enumerate(url_batches):
            if urls_batch:  # Only submit non-empty batches
                future = executor.submit(
                    synthesize_intermediate_report,
                    original_user_query,
                    urls_batch,
                    batch_index,
                    output_dir
                )
                future_to_batch[future] = batch_index
        
        # Collect results as they complete
        for future in as_completed(future_to_batch):
            batch_index = future_to_batch[future]
            try:
                report_content = future.result()
                results.append((batch_index, report_content))
                logging.info(f"✓ Completed batch {batch_index}")
            except Exception as e:
                error_msg = f"## Batch {batch_index} – Error during parallel synthesis:\n{e}"
                results.append((batch_index, error_msg))
                logging.error(f"✗ Failed batch {batch_index}: {e}")
    
    # Sort results by batch index to maintain order
    results.sort(key=lambda x: x[0])
    
    logging.info(f"✓ Parallel synthesis completed: {len(results)} batches processed")
    return results


def synthesize_all_intermediate_reports(
    original_user_query: str,
    url_batches: List[List[str]],
    output_dir: str = "reports/intermediate_reports",
    use_parallel: bool = True,
    max_workers: int = None
) -> List[str]:
    """
    Convenience function to synthesize all intermediate reports either in parallel or sequentially.
    
    Args:
        original_user_query: The original research query
        url_batches: List of URL batches to process
        output_dir: Directory to save intermediate reports
        use_parallel: Whether to use parallel processing (default: True)
        max_workers: Maximum number of parallel workers (only used if use_parallel=True)
    
    Returns:
        List of report contents in batch order
    """
    if use_parallel:
        results = synthesize_intermediate_reports_parallel(
            original_user_query, url_batches, output_dir, max_workers
        )
        # Extract just the report contents in order
        return [report_content for _, report_content in results]
    else:
        # Sequential processing (original behavior)
        reports = []
        for batch_index, urls_batch in enumerate(url_batches):
            report = synthesize_intermediate_report(
                original_user_query, urls_batch, batch_index, output_dir
            )
            reports.append(report)
        return reports
