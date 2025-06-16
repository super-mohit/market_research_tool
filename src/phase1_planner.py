# src/phase1_planner.py
import base64
import os
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
    print("Phase 1: Generating search queries with Gemini...")

    try:
        # 1. Instantiate the client using the API key from our config
        client = genai.Client(api_key=config.GEMINI_API_KEY)

        # Get current date for recency context
        current_date = datetime.now()
        current_year = current_date.year
        current_month = current_date.strftime("%B")
        
        # 2. Define the enhanced prompt
        prompt = f"""
You are a world-class market intelligence strategist for a top-tier global chemical company, with deep expertise in the decorative and industrial coatings sectors. Your mission is to formulate precise search queries to uncover actionable intelligence for our business and R&D teams.

CURRENT DATE CONTEXT:
Today is {current_month} {current_date.day}, {current_year}. The intelligence must be current. Prioritize information from {current_year} and the last {constants.RECENT_YEARS} years ({current_year - constants.RECENT_YEARS + 1}-{current_year}).

USER'S STRATEGIC OBJECTIVE:
{user_input}

TASK:
Generate a JSON dictionary of Google Custom Search Engine (CSE) queries. These queries will be run against a curated list of trusted industry sources. Your queries must be designed to uncover breakthrough technologies, competitive shifts, regulatory changes, and emerging market needs.

QUERY BUCKETS:
Group your queries into the following strategic buckets:
- "News": Corporate announcements, M&A activity, financial results, partnerships.
- "Patents": Patent filings, new intellectual property, and technical whitepapers. Focus on novel chemistries and formulations.
- "Conference": Key findings, presentations, and announcements from major industry events (e.g., American Coatings Show, European Coatings Show).
- "Legalnews": New environmental regulations (like VOC limits), chemical bans, and compliance standards.
- "General": Broader queries on technology trends, market analysis, and material science innovations.

MANDATORY RULES:
1.  **Source Specificity:** Every query MUST use a `site:` operator to target a single domain from the user's provided list.
2.  **Strategic Keywords:** Go beyond simple topics. Combine technologies (e.g., "polyurethane dispersion," "silane-modified polymers," "hydrophobic additives") with performance outcomes (e.g., "scuff resistance," "weatherability," "self-healing," "oleophobic") and business context (e.g., "market trend," "supply chain," "sustainability report").
3.  **Recency Bias:** Embed recency terms in the queries: "{current_year}," "{current_year + 1} forecast," "latest," "emerging," "new."
4.  **Actionable Intelligence Focus:** Formulate queries to find data. Think like a strategist: What would you search for to find competitor weaknesses or new market opportunities?
5.  **Output Format:** Return ONLY the JSON object. Do not include any explanatory text, markdown formatting, or apologies.

EXAMPLE OF A HIGH-QUALITY QUERY:
"latest developments in scuff-resistant architectural coatings {current_year} site:coatingsworld.com"
"sustainability initiatives AkzoNobel coatings {current_year + 1} report site:paint.org"

JSON OUTPUT STRUCTURE:
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
            safety_settings=[
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
            ],
            response_mime_type="application/json",
        )

        # 5. Make the API call using the CORRECT method: client.models.generate_content
        model_name = "gemini-2.5-flash-preview-05-20"
        response = client.models.generate_content(
            model=f"models/{model_name}",
            contents=contents,
            config=generate_content_config,
        )
        
        # 6. Parse the JSON response
        raw = response.candidates[0].content.parts[0].text
        data = json.loads(raw)
        by_bucket = {k: data.get(k, []) for k in
                    ["News","Patents","Conference","Legalnews","General"]}

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
                print(f"Warning: LLM returned '{bucket_name}' but it was not a list. Using empty list.")
                cleaned_buckets[bucket_name] = []

        print(f"Successfully generated and cleaned {total_queries} search queries across {len(cleaned_buckets)} buckets.")
        return cleaned_buckets

    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse JSON from the LLM response. Error: {e}")
        raw = None
        try:
            raw = response.candidates[0].content.parts[0].text
        except Exception:
            pass
        print(f"----- LLM Raw Response -----\n{raw if raw is not None else 'No text in response'}\n--------------------------")
        return {k: [] for k in ["News","Patents","Conference","Legalnews","General"]}
    except Exception as e:
        print(f"An unexpected error occurred during query generation: {e}")
        return {k: [] for k in ["News","Patents","Conference","Legalnews","General"]}