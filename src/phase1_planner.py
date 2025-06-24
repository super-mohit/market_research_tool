# src/phase1_planner.py
import base64
import os
import logging
from datetime import datetime
from google import genai
from google.genai import types
import json
from src import config # Our configuration loader
from src import constants

def generate_search_queries(user_input: str) -> dict[str, list[str]]:
    """
    Uses the Gemini API to analyze user input and generate a dictionary of
    targeted Google CSE search queries organized by category using the correct SDK syntax.

    Args:
        user_input: The full text of the user's request.

    Returns:
        A dictionary with keys News, Patents, Conference, Legalnews, General,
        where each value is a list of search query strings.
        Returns empty lists for each category if generation fails.
    """
    logging.info("Phase 1: Generating search queries with Gemini...")

    try:
        # 1. Instantiate the client using the API key from our config
        client = genai.Client(api_key=config.GEMINI_API_KEY)

        # Get current date for recency context
        current_date = datetime.now()
        current_year = current_date.year
        current_month = current_date.strftime("%B")
        
        # 2. Define the enhanced prompt
        prompt = f"""
You are a world-class market intelligence strategist for a top-tier global chemical company, with deep expertise in the decorative and industrial coatings sectors. Your mission is to formulate a **strategic search plan** to uncover actionable intelligence for our business and R&D teams.

**Current Date Context:**
Today is {current_month} {current_date.day}, {current_year}. The intelligence must be current. Prioritize information from {current_year} and the last {constants.RECENT_YEARS} years ({current_year - constants.RECENT_YEARS + 1}-{current_year}).

**User's Strategic Objective:**
---
{user_input}
---

**Your Core Strategy: The 'Precision & Discovery' Model**
Your goal is to create a portfolio of queries with a mix of two types:
1.  **Precision Queries (60%):** These are highly specific, multi-term queries designed to find exact data points, competitor announcements, or specific technical papers. They are high-risk, high-reward.
2.  **Discovery Queries (40%):** These are broader, using fewer keywords and often omitting date restrictions. Their purpose is to cast a wider net and find foundational context, market overviews, or related concepts you might not have thought of.

**TASK:**
Generate a JSON dictionary of Google Custom Search Engine (CSE) queries. Aim to generate **9-18 diverse queries per bucket**. These queries will be run against a curated list of trusted industry sources.

**Query Buckets:**
- "News": Corporate announcements, M&A activity, financial results, partnerships.
- "Patents": Patent filings, new intellectual property, and technical whitepapers.
- "Conference": Key findings, presentations, and announcements from major industry events.
- "Legalnews": New environmental regulations (like VOC limits), chemical bans, and compliance standards.
- "General": Broader queries on technology trends, market analysis, and material science innovations. Use this bucket for your 'Discovery' queries.

**MANDATORY RULES & GUIDELINES:**
1.  **Source Specificity (Non-negotiable):** Every query MUST use a `site:` operator. Extract relevant domains from the user's objective (e.g., `coatingsworld.com`, `pcimag.com`, `paint.org`).
2.  **Strategic Keyword Layering:**
    *   For **Precision Queries**, combine specific technologies ("polyurethane dispersion") with performance outcomes ("scuff resistance") and business context ("market trend").
    *   For **Discovery Queries**, use more fundamental terms ("sustainability coatings trends" or "weatherability testing standards").
3.  **Intelligent Recency:**
    *   Embed date terms like "{current_year}" or "latest" in *some* queries, especially for the "News" and "Conference" buckets.
    *   For "Patents" and "General" queries, it is often better to **omit** date terms to find foundational or highly relevant older documents. Do not force a date into every query.
4.  **Output Format:** Return ONLY the JSON object. Do not include any explanatory text, markdown formatting like ```json, or apologies.

**Example of a good query mix for "General":**
- (Precision) `site:pcimag.com "hydrophobic additives" "weatherability" "coatings research" 2025`
- (Discovery) `site:coatingsworld.com "sustainability in industrial coatings"`

**JSON Output Structure:**
{{
  "News":        [ "...", "..." ],
  "Patents":     [ "...", "..." ],
  "Conference":  [ "...", "..." ],
  "Legalnews":   [ "...", "..." ],
  "General":     [ "...", "..." ]
}}
"""
        
        # 3. Structure the request using types.Content and types.Part
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part(text=prompt),
                ],
            ),
        ]
        
        # 4. Create the generation configuration object
        # This is the correct way to specify safety and response type.
        generate_content_config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(
                thinking_budget=-1,
            ),
            safety_settings=[
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
            ],
            response_mime_type="application/json",
        )

        # 5. Make the API call using the CORRECT method: client.models.generate_content
        model = "gemini-2.5-pro"
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generate_content_config,
        )
        
        # 6. Parse the JSON response
        raw_text = response.candidates[0].content.parts[0].text
        data = json.loads(raw_text)
        
        expected_buckets = ["News", "Patents", "Conference", "Legalnews", "General"]
        by_bucket = {k: data.get(k, []) for k in expected_buckets}

        # Clean the queries in each bucket to remove protocol and 'www' for the site: operator
        import re
        cleaned_buckets = {}
        total_queries = 0
        
        for bucket_name, queries in by_bucket.items():
            if isinstance(queries, list):
                cleaned_queries = []
                for q in queries:
                    # This regex finds the domain part and rebuilds the query
                    match = re.search(r"site:https?://(?:www\.)?([^/\s]+)", q)
                    if match:
                        domain = match.group(1)
                        # Replace the full url part with just the domain
                        cleaned_q = re.sub(r"site:https?://(?:www\.)?[^/\s]+", f"site:{domain}", q)
                        cleaned_queries.append(cleaned_q)
                    else:
                        cleaned_queries.append(q) # Append as-is if no match
                cleaned_buckets[bucket_name] = cleaned_queries
                total_queries += len(cleaned_queries)
            else:
                logging.warning(f"LLM returned '{bucket_name}' but it was not a list. Using empty list.")
                cleaned_buckets[bucket_name] = []

        logging.info(f"Successfully generated and cleaned {total_queries} search queries across {len(cleaned_buckets)} buckets.")
        return cleaned_buckets

    except (json.JSONDecodeError, IndexError, Exception) as e:
        logging.error(f"Failed during query generation: {e}", exc_info=True)
        return {k: [] for k in ["News","Patents","Conference","Legalnews","General"]}