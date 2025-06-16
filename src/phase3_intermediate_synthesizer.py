# src/phase3_intermediate_synthesizer.py

import os
import re
import datetime
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
        print(f"    - Batch {batch_index}: No URLs provided — skipping.")
        return ""

    print(f"    - Batch {batch_index}: Synthesizing {len(urls_batch)} URLs...")

    client = genai.Client(api_key=config.GEMINI_API_KEY)

    # Get current date for context
    current_date = date.today()
    current_year = current_date.year
    target_years = f"{current_year - constants.RECENT_YEARS + 1}-{current_year}"

    system_instruction = (
        f"You are a senior market intelligence analyst specializing in the global coatings industry. "
        f"Today is {current_date.strftime('%B %d, %Y')}.\n\n"
        
        "**ANALYSIS PRIORITIES:**\n"
        f"• Focus on information from {target_years} (last {constants.RECENT_YEARS} years)\n"
        "• Prioritize quantitative data, market figures, and technical specifications\n"
        "• Highlight breakthrough innovations, regulatory changes, and sustainability developments\n"
        "• Identify emerging trends and competitive dynamics\n\n"
        
        "**CONTENT REQUIREMENTS:**\n"
        "Work exclusively from the provided URLs. Synthesize information into a structured report with:\n\n"
        
        "1. **Executive Summary** (2-3 sentences highlighting the most critical insights)\n"
        "2. **Key Technical Findings**\n"
        "   - Performance data, test results, specifications\n"
        "   - New formulations, technologies, or processes\n"
        "   - Comparative analysis where applicable\n\n"
        
        "3. **Market Intelligence**\n"
        "   - Market size, growth rates, forecasts\n"
        "   - Competitive landscape changes\n"
        "   - Customer demand patterns and preferences\n\n"
        
        "4. **Regulatory & Sustainability Context**\n"
        "   - New regulations, compliance requirements\n"
        "   - Environmental impact assessments\n"
        "   - Sustainability initiatives and green technology adoption\n\n"
        
        "5. **Emerging Trends & Future Outlook**\n"
        "   - R&D developments and pipeline innovations\n"
        "   - Industry partnerships and acquisitions\n"
        "   - Market disruptions and opportunities\n\n"
        
        "**QUALITY STANDARDS:**\n"
        "• Be specific and quantitative - include numbers, percentages, dates\n"
        "• When sources conflict, note the discrepancy and cite both\n"
        "• Distinguish between confirmed facts and industry speculation\n"
        "• Use bullet points for clarity and scanability\n"
        "• Maintain professional, analytical tone throughout\n\n"
        
        "**CITATION FORMAT:**\n"
        "Use inline numeric citations [1], [2] in the order URLs are provided. "
        "Do NOT add a reference section - citations will be mapped externally.\n\n"
        
        "**OUTPUT:** Deliver a concise, actionable Markdown report that enables strategic decision-making."
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
            model="models/gemini-2.5-pro-preview-06-05",
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
        print(f"    - Batch {batch_index}: sub-report saved → {path}")
        return intermediate_md

    except Exception as e:
        err = f"## Batch {batch_index} – Error during synthesis:\n{e}"
        print(f"    - {err}")
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
        print("No URL batches provided for parallel processing.")
        return []

    # Calculate optimal number of workers
    if max_workers is None:
        max_workers = min(len(url_batches), 8)  # Cap at 8 to avoid overwhelming the API
    
    print(f"Starting parallel synthesis of {len(url_batches)} batches with {max_workers} workers...")
    
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
                print(f"✓ Completed batch {batch_index}")
            except Exception as e:
                error_msg = f"## Batch {batch_index} – Error during parallel synthesis:\n{e}"
                results.append((batch_index, error_msg))
                print(f"✗ Failed batch {batch_index}: {e}")
    
    # Sort results by batch index to maintain order
    results.sort(key=lambda x: x[0])
    
    print(f"✓ Parallel synthesis completed: {len(results)} batches processed")
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
