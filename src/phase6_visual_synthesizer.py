# File: src/phase6_visual_synthesizer.py (REVISED)

import logging
import json
import re
from collections import Counter
from google import genai
from google.genai import types

from src import config

# A basic list of stop words for the word cloud. Can be expanded.
STOP_WORDS = set([
    'a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 'and', 'any', 'are', 'as', 'at',
    'be', 'because', 'been', 'before', 'being', 'below', 'between', 'both', 'but', 'by', 'can', 'did',
    'do', 'does', 'doing', 'down', 'during', 'each', 'few', 'for', 'from', 'further', 'had', 'has', 'have',
    'having', 'he', 'her', 'here', 'hers', 'herself', 'him', 'himself', 'his', 'how', 'i', 'if', 'in',
    'into', 'is', 'it', 'its', 'itself', 'just', 'me', 'more', 'most', 'my', 'myself', 'no', 'nor', 'not',
    'now', 'o', 'of', 'on', 'once', 'only', 'or', 'other', 'our', 'ours', 'ourselves', 'out', 'over', 'own',
    's', 'same', 'she', 'should', 'so', 'some', 'such', 't', 'than', 'that', 'the', 'their', 'theirs',
    'them', 'themselves', 'then', 'there', 'these', 'they', 'this', 'those', 'through', 'to', 'too', 'under',
    'until', 'up', 'very', 'was', 'we', 'were', 'what', 'when', 'where', 'which', 'while', 'who', 'whom',
    'why', 'will', 'with', 'you', 'your', 'yours', 'yourself', 'yourselves', 'report', 'market', 'coating',
    'coatings', 'industry', 'analysis', 'research', 'data', 'information', 'global', 'company', 'companies'
])

def _call_gemini(prompt: str, client: genai.Client, response_type: str = "application/json") -> dict | list | str | None:
    """Generic helper to call Gemini and parse JSON/text, with error handling."""
    try:
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=prompt),
                ],
            ),
        ]
        generate_content_config = types.GenerateContentConfig(
            thinking_config = types.ThinkingConfig(
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
            response_mime_type=response_type,
        )

        # Collect the streamed response
        response_text = ""
        for chunk in client.models.generate_content_stream(
            model="gemini-2.5-flash",
            contents=contents,
            config=generate_content_config,
        ):
            response_text += chunk.text
        
        if response_type == "application/json":
            return json.loads(response_text)
        return response_text.strip()
        
    except (json.JSONDecodeError, IndexError, Exception) as e:
        logging.warning(f"Visualizer: A sub-task with prompt starting '{prompt[:50]}...' failed. Error: {e}")
        return None

def _generate_short_summary(final_report: str, client: genai.Client) -> str | None:
    """Generates a concise executive paragraph and bullet points."""
    logging.info("  -> Visualizer: Generating short summary...")
    prompt = f"""
You are an executive assistant skilled at briefing senior leaders. Your task is to distill the following market intelligence report into a highly concise, impactful summary.

REPORT CONTENT:
---
{final_report[:20000]}
---

TASK:
1. Write a 2-3 sentence executive paragraph summarizing the most critical strategic insight from the report.
2. Below the paragraph, add the top 3-5 most important findings as a Markdown bulleted list. Each bullet point should be a complete, actionable sentence.

Your entire response must be a single block of Markdown text. Do not add titles or headers.
"""
    return _call_gemini(prompt, client, response_type="text/plain")

def _generate_word_cloud_data(final_report: str, extracted_data: dict) -> list[dict]:
    """Generates word frequency data for a word cloud, excluding stop words."""
    logging.info("  -> Visualizer: Generating word cloud data...")
    text_corpus = final_report
    for category in extracted_data.values():
        for item in category:
            text_corpus += f" {item.get('title', '')} {item.get('summary', '')}"

    words = re.findall(r'\b[a-z]{3,15}\b', text_corpus.lower())
    filtered_words = [word for word in words if word not in STOP_WORDS]
    word_counts = Counter(filtered_words)
    
    # --- THIS IS THE FIX ---
    # The react-tagcloud library expects keys 'value' (for the word) and 'count' (for the frequency).
    return [{"value": word, "count": count} for word, count in word_counts.most_common(75)]

def _generate_swot_data(full_text_context: str, client: genai.Client) -> dict | None:
    """Generates a SWOT analysis from the report."""
    logging.info("  -> Visualizer: Generating SWOT data...")
    prompt = f"""
You are a Chief Strategy Officer creating a SWOT analysis based on the provided intelligence.

REPORT CONTEXT:
---
{full_text_context[:250000]}
---

TASK:
Generate a concise SWOT analysis. For each quadrant, identify the top 3-4 most critical points.
- Strengths/Weaknesses should be inferred based on the client's likely position relative to the market.
- Opportunities/Threats should be external market forces.

**MANDATORY JSON FORMAT:**
- Your response MUST be a single, valid JSON object.
- The object must have four keys: "strengths", "weaknesses", "opportunities", "threats".
- Each key's value must be a list of short, descriptive strings.
- **CRITICAL:** Do not add a comma after the last item in any list (no trailing commas).

**EXAMPLE OF PERFECT JSON:**
{{
  "strengths": ["Strong R&D in polyurethane dispersions", "Established brand in North America"],
  "weaknesses": ["Limited portfolio in bio-based resins", "High dependency on architectural segment"],
  "opportunities": ["Growth in sustainable building materials market", "Acquisition target with novel additive technology"],
  "threats": ["New EU regulations on specific isocyanates", "Aggressive pricing from APAC competitors"]
}}
"""
    return _call_gemini(prompt, client)

def _generate_map_data(full_text_context: str, client: genai.Client) -> dict | None:
    """Generates geographic insights for a world map visual."""
    logging.info("  -> Visualizer: Generating geographic map data...")
    prompt = f"""
Analyze the provided text for any mentions of countries or major world regions related to market activities, manufacturing, R&D, or regulatory changes.

REPORT CONTEXT:
---
{full_text_context[:250000]}
---

**TASK:**
For each distinct country or region found, provide a 1-sentence summary of the key activity mentioned.
Return a single, valid JSON object where the key is the country/region name (in English) and the value is the summary string.
- **CRITICAL:** Ensure no trailing commas after the last key-value pair.

**EXAMPLE OF PERFECT JSON:**
{{"Germany": "Hosting a key conference on new polymer technologies.", "China": "Announced new environmental regulations impacting solvent-based coatings."}}
"""
    return _call_gemini(prompt, client)

def _generate_radar_chart_data(full_text_context: str, client: genai.Client) -> dict | None:
    """Generates competitive analysis data for a radar chart."""
    logging.info("  -> Visualizer: Generating competitive radar chart data...")
    prompt = f"""
You are a competitive intelligence analyst. From the provided research, identify the top 3-4 key competitors. Evaluate them on a scale of 1 (weak) to 10 (strong) across these five dimensions: Innovation, Market Presence, Brand Strength, Sustainability, and Pricing Power. Base scores on evidence in the text.

REPORT CONTEXT:
---
{full_text_context[:250000]}
---

**TASK:**
Return a single, valid JSON object with two keys: "labels" and "competitors".
- "labels" must be a list of the five dimension strings.
- "competitors" must be a list of objects, where each object has a "name" (string) and "scores" (a list of 5 integers).
- **CRITICAL:** Ensure no trailing commas.

**EXAMPLE OF PERFECT JSON:**
{{
  "labels": ["Innovation", "Market Presence", "Brand Strength", "Sustainability", "Pricing Power"],
  "competitors": [
    {{"name": "AkzoNobel", "scores": [8, 9, 9, 7, 6]}},
    {{"name": "PPG", "scores": [7, 9, 8, 8, 7]}},
    {{"name": "Sherwin-Williams", "scores": [6, 8, 9, 6, 8]}}
  ]
}}
"""
    return _call_gemini(prompt, client)

def _generate_hype_cycle_data(full_text_context: str, client: genai.Client) -> list | None:
    """Generates technology maturity data for a hype cycle visual."""
    logging.info("  -> Visualizer: Generating technology hype cycle data...")
    prompt = f"""
You are a Gartner-style technology analyst. Analyze the provided research to identify 5-7 key technologies. For each, assess its current maturity stage based on the Gartner Hype Cycle model (Innovation Trigger, Peak of Inflated Expectations, Trough of Disillusionment, Slope of Enlightenment, Plateau of Productivity).

REPORT CONTEXT:
---
{full_text_context[:250000]}
---

**TASK:**
Return a single, valid JSON array of technology objects. Each object must have three keys: "name" (string), "stage" (string, one of the five hype cycle phases), and "summary" (string, a 1-sentence justification for the placement).
- **CRITICAL:** Ensure the entire output is one JSON array `[...]` and there are no trailing commas.

**EXAMPLE OF PERFECT JSON:**
[
  {{"name": "Self-Healing Coatings", "stage": "Peak of Inflated Expectations", "summary": "Significant media attention and startup activity, but widespread commercial adoption is still 5-10 years away."}},
  {{"name": "Bio-based Polyols", "stage": "Slope of Enlightenment", "summary": "Second-generation products are entering the market, with clearer use cases and proven performance benefits."}},
  {{"name": "Graphene Additives", "stage": "Trough of Disillusionment", "summary": "Early hype has faded as challenges in cost and dispersion have slowed adoption outside of niche applications."}}
]
"""
    return _call_gemini(prompt, client)

def generate_overview_data(final_report: str, extracted_data: dict) -> dict:
    """
    Orchestrates the generation of all data needed for the visual overview dashboard.
    """
    logging.info("--- Starting Phase 6: Visual Synthesizer ---")
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    full_text_context = final_report
    for category in extracted_data.values():
        for item in category:
            full_text_context += f"\n\nItem: {item.get('title', '')}\nSummary: {item.get('summary', '')}"

    overview_payload = {
        "short_summary": _generate_short_summary(final_report, client),
        "word_cloud": _generate_word_cloud_data(final_report, extracted_data),
        "swot_analysis": _generate_swot_data(full_text_context, client),
        "geographic_insights": _generate_map_data(full_text_context, client),
        "competitive_radar": _generate_radar_chart_data(full_text_context, client),
        "tech_hype_cycle": _generate_hype_cycle_data(full_text_context, client),
    }

    logging.info("--- Finished Phase 6: Visual Synthesizer ---")
    return overview_payload 