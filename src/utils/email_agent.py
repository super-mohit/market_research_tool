# src/utils/email_agent.py
import os
import httpx
import logging
import json

# Get credentials from environment variables
SUPERVITY_API_TOKEN = os.getenv("SUPERVITY_API_TOKEN")
SUPERVITY_ORG_ID = os.getenv("SUPERVITY_ORG_ID")
EMAIL_AGENT_ID = os.getenv("EMAIL_AGENT_ID")
EMAIL_SKILL_ID = os.getenv("EMAIL_SKILL_ID")

API_URL = "https://api.supervity.ai/botapi/draftSkills/v2/execute/"

async def send_report_email(user_name: str, user_email: str, pdf_link: str, query: str):
    """
    Calls the Supervity email agent by sending a direct JSON payload.

    Args:
        user_name: The name of the recipient.
        user_email: The email address of the recipient.
        pdf_link: The permanent URL to the generated PDF report.
        query: The original research query that prompted the report.
    """
    logging.info(f"Preparing to trigger email agent for {user_email}")
    
    # --- This is the key change: We build the exact JSON structure ---
    # The agent expects a main JSON body with an 'inputText' field,
    # which itself contains the structured data.
    
    input_text_payload = {
        "receiver_name": user_name,
        "receiver_email": user_email,
        "file_link": pdf_link,
        "original_query": query,
        # You can add any other fields the agent might need here
        "Agent_Status": "answered" # As seen in your example
    }

    main_payload = {
        "v2AgentId": EMAIL_AGENT_ID,
        "v2SkillId": EMAIL_SKILL_ID,
        "inputText": input_text_payload  # Nest the data inside 'inputText'
    }

    headers = {
        'x-api-token': SUPERVITY_API_TOKEN,
        'x-api-org': SUPERVITY_ORG_ID,
        'Content-Type': 'application/json' # Important: specify the content type
    }
    
    # Check if all required env vars are present
    if not all([SUPERVITY_API_TOKEN, SUPERVITY_ORG_ID, EMAIL_AGENT_ID, EMAIL_SKILL_ID]):
        logging.error("Email agent credentials are not fully configured in environment variables.")
        raise Exception("Email service is not configured.")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # We send the main_payload as a JSON body directly.
            # No more 'files' or 'data' forms.
            response = await client.post(API_URL, headers=headers, json=main_payload)
            
            response.raise_for_status()
            logging.info(f"Successfully triggered email agent for {user_email}. Status: {response.status_code}")
            return {"success": True, "message": "Email process initiated."}
            
    except httpx.HTTPStatusError as e:
        error_body = e.response.text
        logging.error(f"Email agent API error: {e.response.status_code} - {error_body}")
        raise Exception(f"Failed to trigger email agent: {error_body}")
    except Exception as e:
        logging.error(f"An unexpected error occurred while calling email agent: {e}", exc_info=True)
        raise 