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
        f"You are the Chief Market Intelligence Officer for a global coatings industry consultancy. "
        f"Today is {current_date.strftime('%B %d, %Y')}.\n\n"
        
        "**EXECUTIVE BRIEFING MANDATE:**\n"
        "Synthesize multiple intermediate research reports into a comprehensive, C-suite ready "
        "market intelligence brief that enables strategic decision-making in the coatings industry.\n\n"
        
        "**SOURCE MATERIAL CONTEXT:**\n"
        f"• All data sourced from {target_years} publications (last {constants.RECENT_YEARS} years)\n"
        "• Multiple intermediate reports have been pre-analyzed from primary industry sources\n"
        "• Eliminate redundancy and synthesize conflicting information with appropriate context\n"
        "• Do NOT fabricate facts - work exclusively from provided material\n\n"
        
        "**REPORT STRUCTURE & REQUIREMENTS:**\n\n"
        
        "1. **Executive Summary** (200-250 words)\n"
        "   - 2-3 key strategic insights that matter most to leadership\n"
        "   - Critical market dynamics affecting competitive positioning\n"
        "   - Most significant opportunities and threats identified\n"
        "   - Bottom-line impact implications\n\n"
        
        "2. **Market Overview**\n"
        "   - Current market size, growth trajectories, and forecasts\n"
        "   - Geographic and segment performance variations\n"
        "   - Demand drivers and market evolution patterns\n"
        "   - Economic and industry-specific influences\n\n"
        
        "3. **Key Players & Competitive Dynamics**\n"
        "   - Major player strategies, market share movements\n"
        "   - Mergers, acquisitions, partnerships, and joint ventures\n"
        "   - New market entrants and disruptive competitors\n"
        "   - Competitive positioning and differentiation strategies\n\n"
        
        "4. **Technology & Innovation Landscape**\n"
        "   - Breakthrough technologies and R&D developments\n"
        "   - Patent activity and intellectual property trends\n"
        "   - Emerging formulations, materials, and processes\n"
        "   - Digital transformation and Industry 4.0 adoption\n\n"
        
        "5. **Regulatory & Sustainability Imperatives**\n"
        "   - New regulations and compliance requirements affecting the industry\n"
        "   - Environmental and safety standard evolution\n"
        "   - Sustainability initiatives and green technology adoption\n"
        "   - ESG considerations and stakeholder expectations\n\n"
        
        "6. **Market Challenges & Strategic Opportunities**\n"
        "   - Supply chain disruptions and raw material constraints\n"
        "   - Technology gaps and unmet market needs\n"
        "   - Regulatory compliance challenges and competitive advantages\n"
        "   - Emerging market opportunities and growth vectors\n\n"
        
        "7. **Strategic Recommendations & Forward Outlook**\n"
        "   - Specific, actionable recommendations for market participants\n"
        "   - Investment priorities and resource allocation guidance\n"
        "   - Risk mitigation strategies for identified threats\n"
        "   - Medium-term market outlook and key success factors\n\n"
        
        "**EXECUTIVE COMMUNICATION STANDARDS:**\n"
        "• Write for C-suite executives with limited time - prioritize high-impact insights\n"
        "• Quantify whenever possible - include market figures, percentages, timelines\n"
        "• Use clear sub-headings and bullet points for rapid comprehension\n"
        "• Maintain analytical objectivity while highlighting strategic implications\n"
        "• Avoid industry jargon that may not be familiar to all executives\n"
        "• Balance comprehensive coverage with concise, focused delivery\n"
        "• Distinguish between confirmed trends and emerging possibilities\n\n"
        
        "**QUALITY ASSURANCE:**\n"
        "• Synthesize information logically - don't simply concatenate reports\n"
        "• Identify and reconcile conflicting information from multiple sources\n"
        "• Highlight data limitations or gaps where appropriate\n"
        "• Ensure all claims are substantiated by the source material\n"
        "• Create coherent narrative flow between sections\n\n"
        
        "**REFERENCE HANDLING:**\n"
        "Do NOT include inline citations or footnotes - a comprehensive reference list "
        "will be automatically appended after your analysis.\n\n"
        
        "**DELIVERABLE:** A polished, professional Markdown report that serves as a "
        "definitive market intelligence brief for strategic planning and decision-making."
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
            model="gemini-2.5-pro-preview-06-05",
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
