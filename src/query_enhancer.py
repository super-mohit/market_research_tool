# File: src/query_enhancer.py (REVISED)

import logging
import json
from google import genai
from google.genai import types

from src import config

def generate_tags_from_topic(topic: str) -> dict:
    """
    Uses a Gemini LLM to analyze a user's topic, extract core concepts,
    and expand them into a structured set of user-friendly, business-oriented tags.

    Args:
        topic: The user's research topic or full query.

    Returns:
        A dictionary containing categorized lists of conceptual tags.
    """
    logging.info(f"Query Enhancer: Generating conceptual tags for topic: '{topic[:100]}...'")

    client = genai.Client(api_key=config.GEMINI_API_KEY)

    prompt = f"""
You are an expert semantic analysis engine for the chemical and coatings industry. Your task is to analyze a user's research objective, identify the core concepts within it, and then generate a list of related, high-value keywords and topics that would be relevant to a business or R&D professional.

**USER'S RESEARCH OBJECTIVE:**
"{topic}"

**YOUR TWO-STEP TASK:**

**Step 1: Deconstruction & Concept Identification**
First, meticulously break down the user's query into its fundamental components. Identify:
- Core Technologies (e.g., "polyurethane", "epoxy resin")
- Performance Attributes (e.g., "weatherability", "scuff resistance")
- Market Segments (e.g., "automotive", "architectural", "industrial")
- High-Level Concepts (e.g., "sustainability", "innovation", "emerging trends")
- Document Types (e.g., "patents", "conferences")
- Key Competitors (e.g., "BASF", "AkzoNobel")

**Step 2: Expansion & Categorization**
Based on the identified concepts, generate a structured list of short, user-friendly tags (1-3 words each). These tags should feel like clickable topics, not complex search queries. Group them into logical categories. If you identify a company, include it in the 'Key Players & Products' category.

**MANDATORY RULES:**
- **Tag Style:** Tags must be concise and clear (e.g., "UV Resistance", not "technologies related to UV resistance").
- **Relevance:** Every tag must be highly relevant to the core concepts identified in the user's query.
- **Categorization:** You MUST use the following categories as keys in your JSON output. If no relevant tags are found for a category, return an empty list for that key.
    - `performance_attributes`: Physical or chemical properties and benefits.
    - `technologies_and_materials`: Specific chemistries, materials, or processes.
    - `market_and_business`: High-level business, market, or strategic concepts.
    - `key_players_and_products`: Specific companies or well-known product lines.
- **JSON Format Only**: Your entire response MUST be a single, valid JSON object. Do not include any explanatory text or markdown formatting.

**--- EXAMPLE ---**

**USER INPUT:** "Show me the latest innovations in Weatherability of Decorative Coatings. What trends are emerging in the Sustainability of industrial coatings in 2025? Find recent conferences or Patents discussing Scuff-Resistance in coatings from BASF."

**CORRECT JSON OUTPUT:**
{{
  "performance_attributes": [
    "Weatherability",
    "Scuff Resistance",
    "UV Resistance",
    "Color Stability",
    "Abrasion Resistance"
  ],
  "technologies_and_materials": [
    "Decorative Coatings",
    "Industrial Coatings",
    "Waterborne Coatings",
    "Low-VOC Formulations",
    "Bio-based Resins",
    "Nanotechnology Additives",
    "Polyurethane Dispersions"
  ],
  "market_and_business": [
    "Innovation",
    "Sustainability",
    "Emerging Trends",
    "Circular Economy",
    "Industry Conferences",
    "Patents"
  ],
  "key_players_and_products": [
    "BASF",
    "AkzoNobel",
    "Sherwin-Williams"
  ]
}}

**--- END EXAMPLE ---**

Now, generate the JSON for the user's research objective provided at the top.
"""

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
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
        ],
        response_mime_type="application/json",
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generate_content_config,
        )
        
        raw_json = response.candidates[0].content.parts[0].text
        data = json.loads(raw_json)
        
        # Ensure all keys are present, even if empty
        expected_keys = ["performance_attributes", "technologies_and_materials", "market_and_business", "key_players_and_products"]
        validated_data = {key: data.get(key, []) for key in expected_keys}
        
        logging.info("Query Enhancer: Successfully generated conceptual tags.")
        return validated_data

    except (json.JSONDecodeError, IndexError, Exception) as e:
        logging.error(f"Query Enhancer: Failed to generate or parse tags. Error: {e}")
        # Return a structured empty response on failure
        return {
            "performance_attributes": [],
            "technologies_and_materials": [],
            "market_and_business": [],
            "key_players_and_products": []
        } 