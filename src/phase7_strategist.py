# File: src/phase7_strategist.py (NEW FILE)

import logging
import json
import os
from google import genai
from google.genai import types

from src import config

def generate_strategic_insights(
    final_report_md: str,
    structured_data: dict,
    original_query: str,
    company_name: str,
    company_profile: str
) -> dict:
    """
    Generates high-level strategic insights tailored to Wacker.
    """
    logging.info(f"--- Starting Phase 7: Strategic Synthesis for {company_name} ---")
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    # Combine all available information into a comprehensive context blob
    full_context = f"""
## Original Research Objective
{original_query}

## Full Executive Report
{final_report_md}

## Structured Data Extracts
{json.dumps(structured_data, indent=2)}
    """
    
    # Increase the limit to give the strategist maximum information.
    # From 900,000 to 1,800,000 characters.
    max_chars = 1_800_000
    if len(full_context) > max_chars:
        logging.warning(f"Strategist: Full context is very large, truncating to {max_chars} chars...")
        full_context = full_context[:max_chars]

    # This prompt is now dynamically personalized.
    prompt = f"""
You are a top-tier management consultant from Boston Consulting Group (BCG), an expert in the global chemicals and coatings market. Your current client is a high-priority account.

**CLIENT PROFILE:**
- **Name:** {company_name}
- **Description:** "{company_profile}"
- **Stated Goals for this analysis:** 
    1. Identify direct competitive threats to our business.
    2. Guide our R&D investment priorities for the next 18-24 months.
    3. Inform our marketing and product positioning strategy.

You have been provided with a comprehensive market intelligence report. Your mission is to interpret this raw intelligence **through the specific lens of {company_name}'s strategic goals** and produce a concise, actionable strategy document for their leadership. Do not merely summarize the report; your value is in synthesizing threats, opportunities, and a clear path forward **for {company_name}**.

**PROVIDED INTELLIGENCE (Strictly adhere to this context):**
---
{full_context}
---

**TASK:**
Generate a JSON object that serves as a strategic brief for {company_name}'s leadership. The JSON object must contain these exact keys and follow the specified structure.

1.  `"market_positioning"`: (String) A sharp, 2-3 sentence analysis of where **{company_name}** stands in relation to the findings. How should they position themselves?

2.  `"key_opportunities"`: (Array of objects) The top 3-5 strategic opportunities for **{company_name}**. Each object MUST have:
    *   `"title"`: (String) Impactful title (e.g., "Dominate the Eco-Friendly Additives Market").
    *   `"justification"`: (String) 1-2 sentences on why this is a prime opportunity for **{company_name}**, referencing report data.
    *   `"impact"`: (String) Must be one of: "High", "Medium", "Low".
    *   `"timeframe"`: (String) Must be one of: "Short-Term (0-1yr)", "Medium-Term (1-3yr)", "Long-Term (3+yr)".

3.  `"key_threats"`: (Array of objects) The top 3-5 strategic threats facing **{company_name}**. Use the same structure as `key_opportunities`.

4.  `"recommended_actions"`: (Array of objects) A list of 3-5 concrete, non-generic next steps for **{company_name}**. Each object MUST have:
    *   `"action"`: (String) Specific action (e.g., "Launch a task force to evaluate non-silicone hydrophobic additives.").
    *   `"department"`: (String) Primary owner. Must be one of: "R&D", "Marketing", "Business Development", "Operations", "Executive Leadership".
    *   `"urgency"`: (String) Must be one of: "High", "Medium", "Low".

5.  `"executive_summary"`: (String) A final, hard-hitting paragraph for the CEO of **{company_name}**, summarizing the single most critical strategic recommendation.

**CRITICAL RULES:**
- Your entire output MUST be a single, valid JSON object. Do not include any text, explanations, or markdown formatting like ```json before or after the JSON.
- The analysis must be deeply rooted in the provided context. If the information isn't in the report, you cannot invent it.
- Maintain the persona of a world-class strategist advising a major client. The tone should be decisive, insightful, and professional.
- **Ensure there are no trailing commas** after the last element in any JSON list or object.
"""

    try:
        model = "gemini-2.5-pro"
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=prompt),
                ],
            ),
        ]
        generate_content_config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(
                thinking_budget=-1,
            ),
            safety_settings=[
                types.SafetySetting(
                    category="HARM_CATEGORY_HARASSMENT",
                    threshold="BLOCK_NONE",
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_HATE_SPEECH",
                    threshold="BLOCK_NONE",
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    threshold="BLOCK_NONE",
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_DANGEROUS_CONTENT",
                    threshold="BLOCK_NONE",
                ),
            ],
            response_mime_type="application/json",
        )

        # Collect the full response from streaming
        full_response = ""
        for chunk in client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=generate_content_config,
        ):
            if chunk.text:
                full_response += chunk.text

        insights = json.loads(full_response)
        logging.info(f"--- Finished Phase 7: Strategic Synthesis generated successfully. ---")
        return insights
    except Exception as e:
        logging.error(f"Strategist: Failed to generate strategic insights. Error: {e}", exc_info=True)
        return {"error": f"Failed to generate strategic insights: {e}"} 