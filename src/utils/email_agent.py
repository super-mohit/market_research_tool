# src/utils/email_agent.py
import os
import httpx
import logging
import json

SUPERVITY_API_TOKEN = os.getenv("SUPERVITY_API_TOKEN")
SUPERVITY_ORG_ID = os.getenv("SUPERVITY_ORG_ID")
EMAIL_AGENT_ID = os.getenv("EMAIL_AGENT_ID")
EMAIL_SKILL_ID = os.getenv("EMAIL_SKILL_ID")
API_URL = "https://api.supervity.ai/botapi/draftSkills/v2/execute/"

async def send_report_email(receiver_email: str, company_name: str, file_link: str):
    """
    Calls the Supervity email agent by sending a direct JSON payload
    with keys matching the Step 1 prompt.
    """
    logging.info(f"Preparing to trigger email agent for {receiver_email}")
    
    # This payload has the exact keys your agent's Step 1 expects
    input_text_payload = {
        "receiver_email": receiver_email,
        "company_name": company_name,
        "file_link": file_link
    }

    main_payload = {
        "v2AgentId": EMAIL_AGENT_ID,
        "v2SkillId": EMAIL_SKILL_ID,
        "inputText": input_text_payload
    }

    headers = {
        'x-api-token': SUPERVITY_API_TOKEN,
        'x-api-org': SUPERVITY_ORG_ID,
        'Content-Type': 'application/json'
    }
    
    if not all([SUPERVITY_API_TOKEN, SUPERVITY_ORG_ID, EMAIL_AGENT_ID, EMAIL_SKILL_ID]):
        logging.error("Email agent credentials are not fully configured.")
        raise Exception("Email service is not configured.")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(API_URL, headers=headers, json=main_payload)
            response.raise_for_status()
            logging.info(f"Successfully triggered email agent. Status: {response.status_code}")
            return {"success": True}
            
    except httpx.HTTPStatusError as e:
        logging.error(f"Email agent API error: {e.response.status_code} - {e.response.text}")
        raise Exception(f"Failed to trigger email agent: {e.response.text}")
    except Exception as e:
        logging.error(f"Unexpected error calling email agent: {e}", exc_info=True)
        raise 