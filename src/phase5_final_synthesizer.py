# src/phase5_final_synthesizer.py

import os
import re
import datetime
from datetime import date
from google import genai
from google.genai import types
from src import config
from src import constants
import hashlib

def synthesize_final_report(
    original_user_query: str,
    intermediate_reports_text: list[str],
    all_original_urls: list[str],
    output_dir: str = "reports"
) -> str:
    """
    Consolidates intermediate sub-reports into a comprehensive Markdown report.
    """
    os.makedirs(output_dir, exist_ok=True)
    print(f"\nPhase 5: Generating final report from {len(intermediate_reports_text)} intermediate documents...")

    if not intermediate_reports_text:
        return _create_fallback_report(original_user_query, output_dir, "No intermediate reports available")

    formatted_content = _format_intermediate_reports(intermediate_reports_text)
    if len(formatted_content) > 100_000:
        print("    - Warning: content truncated for context limit")
        formatted_content = formatted_content[:100_000] + "\n\n[Content truncated due to length...]"

    client = genai.Client(api_key=config.GEMINI_API_KEY)

    # Get current date for context
    current_date = date.today()
    current_year = current_date.year
    target_years = f"{current_year - constants.RECENT_YEARS + 1}-{current_year}"

    system_instruction = (
        f"You are the Chief Market Intelligence Officer for a global chemical company. Your audience is the CEO and the Board of Directors. Your task is to synthesize a collection of internal research briefings into a single, cohesive, and forward-looking executive report. Today is {current_date.strftime('%B %d, %Y')}.\n\n"
        
        "**MANDATE: Synthesize, Don't Summarize.**\n"
        "Do not simply concatenate the provided intermediate reports. Your value is in finding the 'golden threads' that connect them. Identify the overarching trends, reconcile conflicting data points, and expose the critical strategic narrative hidden within the details. For every fact, you must answer the business-critical question: **'So what?'**\n\n"
        
        "**STRATEGIC REPORT STRUCTURE:**\n"
        "Structure your brief using the following Markdown format. Each section must be analytical and focused on strategic implications.\n\n"
        
        "1.  **Executive Summary (The 3-Minute Briefing)**\n"
        "    - Start with the single most critical conclusion from this research.\n"
        "    - Present 2-3 key opportunities and threats that demand immediate leadership attention.\n"
        "    - Conclude with the bottom-line impact for our company.\n\n"
        
        "2.  **Market Trajectory & Headwinds**\n"
        "    - Synthesize market size and growth forecasts. Where are the pockets of growth, and where is the market stagnating?\n"
        "    - What are the primary economic or consumer behavior trends driving demand?\n\n"
        
        "3.  **Competitive Arena: Key Moves & Vulnerabilities**\n"
        "    - Analyze the strategic maneuvers of key competitors (e.g., PPG, AkzoNobel, BASF). Where are they investing? Where do they appear weak?\n"
        "    - Highlight any M&A activity or partnerships that could reshape the market.\n\n"
        
        "4.  **Technology & Innovation: The Next Frontier**\n"
        "    - What are the 1-2 breakthrough technologies that could disrupt the market (e.g., in sustainability, application, performance)?\n"
        "    - What does the patent landscape suggest about the future of coatings R&D?\n\n"
        
        "5.  **Regulatory & ESG: Risks and Opportunities**\n"
        "    - What new regulations or environmental standards pose the greatest risk to our current product portfolio?\n"
        "    - How can we leverage sustainability trends (e.g., circular economy, bio-based materials) into a competitive advantage?\n\n"
        
        "6.  **Actionable Strategic Recommendations**\n"
        "    - **This is the most important section.** Provide 3-5 specific, bold, and actionable recommendations.\n"
        "    - Frame them as clear directives. Example: 'Recommend allocating an additional $5M in R&D to develop a proprietary scuff-resistant resin to counter Competitor X's new product launch' instead of 'We should invest in R&D.'\n\n"
        
        "**EXECUTIVE COMMUNICATION PROTOCOL:**\n"
        "•   **Be Decisive:** Use strong, declarative sentences. Avoid hedging language.\n"
        "•   **Quantify Everything:** Use all available figures, percentages, and timelines to support your analysis.\n"
        "•   **Clarity and Brevity:** Use headings and bullet points. Assume your audience has only five minutes.\n"
        "•   **Reference Integrity:** Do NOT include inline citations. A reference list of the source URLs will be appended automatically.\n\n"
        
        "**DELIVERABLE:** A polished, professional Markdown report that can be directly used for the company's strategic planning session."
    )

    # Combine system instruction with user instruction since Gemini only accepts "user" and "model" roles
    combined_instruction = (
        f"{system_instruction}\n\n"
        f"**RESEARCH OBJECTIVE:**\n{original_user_query}\n\n"
        f"**INTERMEDIATE REPORTS TO SYNTHESIZE ({len(intermediate_reports_text)} parts):**\n"
        f"{formatted_content}\n\n"
        "**TASK:** Create a comprehensive, executive-ready market intelligence report that "
        "addresses the research objective using the provided intermediate analysis."
    )

    contents = [
        types.Content(role="user", parts=[types.Part(text=combined_instruction)])
    ]

    config_obj = types.GenerateContentConfig(
        tools=[],
        safety_settings=[
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_MEDIUM_AND_ABOVE"),
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_MEDIUM_AND_ABOVE"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_MEDIUM_AND_ABOVE"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_MEDIUM_AND_ABOVE"),
        ],
        response_modalities=["TEXT"]
    )

    try:
        print("    - Calling Gemini for final synthesis...")
        stream = client.models.generate_content_stream(
            model="gemini-2.5-flash-preview-05-20",
            contents=contents,
            config=config_obj,
        )
        final_text = "".join(chunk.text for chunk in stream).strip()

        removed_count = len(all_original_urls)
        if removed_count < 12:   # keeps report honest if data set is now small
            final_text = (
                f"> **Note ·**  After applying the {constants.RECENT_YEARS}-year "
                "freshness filter only "
                f"{removed_count} source URLs remained.\n\n"
            ) + final_text

        final_with_refs = _add_references_section(final_text, all_original_urls)
        filepath = _save_final_report(final_with_refs, original_user_query, output_dir)

        print(f"✅ Final report saved to {filepath} ({len(final_with_refs):,} chars, {len(all_original_urls)} references)")
        return filepath

    except Exception as e:
        print(f"❌ Gemini error: {e}")
        return _create_fallback_report(original_user_query, output_dir, str(e), intermediate_reports_text)

def _format_intermediate_reports(reports: list[str]) -> str:
    return "\n\n".join(
        f"\n\n{'='*60}\nINTERMEDIATE REPORT #{i+1}\n{'='*60}\n\n{r.strip()}"
        for i, r in enumerate(reports)
    )

def _add_references_section(report_md: str, urls: list[str]) -> str:
    if not urls:
        return report_md + "\n\n---\n\n## References\n\n_No URLs provided._\n"
    refs = "\n".join(f"{i+1}. {url}" for i, url in enumerate(urls))
    return report_md + f"\n\n---\n\n## References\n\n*Synthesized from {len(urls)} sources:*\n\n{refs}\n"

def _save_final_report(content: str, query: str, output_dir: str) -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = hashlib.sha1(query.encode()).hexdigest()[:16]
    path = os.path.join(output_dir, f"{ts}_{safe}_FINAL_REPORT.md")
    with open(path, "w", encoding="utf‑8") as f:
        f.write(content)
    return path

def _create_fallback_report(query: str, output_dir: str, reason: str, reports: list[str] = None) -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = hashlib.sha1(query.encode()).hexdigest()[:16]
    path = os.path.join(output_dir, f"{ts}_{safe}_FALLBACK_REPORT.md")
    content = f"# Report: {query}\n\n**Status:** Incomplete\n\n**Reason:** {reason}\n\n"
    if reports:
        content += "## Intermediate Reports\n\n" + "\n\n".join(f"### Report #{i+1}\n{r}" for i, r in enumerate(reports))
    with open(path, "w", encoding="utf‑8") as f:
        f.write(content)
    return path
