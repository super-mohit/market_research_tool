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
        
        # 2. Define the prompt
        prompt = f"""
You are a senior market-intelligence analyst specialising in the global
coatings industry.

CURRENT DATE CONTEXT:
Today is {current_month} {current_date.day}, {current_year}. When generating queries, prioritize information from {current_year} and the most recent {constants.RECENT_YEARS} years ({current_year - constants.RECENT_YEARS + 1}-{current_year}).

USER REQUEST:
{user_input}

TASK  
Generate a JSON dictionary that groups Google Custom Search Engine
queries into the following buckets:

  • "News"        • "Patents"  
  • "Conference"  • "Legalnews"  
  • "General"     (technology & market background)

MANDATORY RULES
1.  Every query must use **one** `site:` operator that restricts the
    search to a single domain drawn from the user's allowed list.
2.  Bias the wording toward **recency** – e.g. "latest", "{current_year}", "recent", "new" –
    so results fall within the last {constants.RECENT_YEARS} calendar years ({current_year - constants.RECENT_YEARS + 1}-{current_year}).
3.  Each bucket may contain up to 15 unique queries.
4.  Vary keywords to capture innovations, regulations, performance
    testing, sustainability, and scuff-resistance.
5.  Focus on the most current developments, trends, and announcements.
6.  Return **only** this JSON object. No prose, no markdown:

{{
  "News":        [ "...", "..." ],
  "Patents":     [ "...", "..." ],
  "Conference":  [ "...", "..." ],
  "Legalnews":  [ "...", "..." ],
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
        model_name = "gemini-2.5-pro-preview-06-05"
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