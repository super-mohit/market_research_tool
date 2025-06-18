# src/utils/email_agent.py
import os
import httpx
import logging
import json
import tempfile

# Get credentials from environment variables
SUPERVITY_API_TOKEN = os.getenv("SUPERVITY_API_TOKEN")
SUPERVITY_ORG_ID = os.getenv("SUPERVITY_ORG_ID")
EMAIL_AGENT_ID = os.getenv("EMAIL_AGENT_ID")
EMAIL_SKILL_ID = os.getenv("EMAIL_SKILL_ID")

API_URL = "https://api.supervity.ai/botapi/draftSkills/v2/execute/"

async def send_report_email_via_file(receiver_email: str, company_name: str, file_link: str):
    """
    Calls the Supervity email agent by sending the payload as a temporary text file.
    This matches the `inputFiles` curl command.
    """
    logging.info(f"Preparing to trigger email agent for {receiver_email} via file upload.")

    # This is the JSON content that will go inside the text file
    payload_content = {
        "receiver_email": receiver_email,
        "company_name": company_name,
        "file_link": file_link
    }

    # The API expects form data, not a JSON body
    form_data = {
        'v2AgentId': EMAIL_AGENT_ID,
        'v2SkillId': EMAIL_SKILL_ID,
    }

    headers = {
        'x-api-token': SUPERVITY_API_TOKEN,
        'x-api-org': SUPERVITY_ORG_ID,
    }
    
    if not all([SUPERVITY_API_TOKEN, SUPERVITY_ORG_ID, EMAIL_AGENT_ID, EMAIL_SKILL_ID]):
        logging.error("Email agent credentials are not fully configured.")
        raise Exception("Email service is not configured.")

    # Create a temporary file to hold the JSON payload
    # 'w+' allows writing and reading. 't' for text mode.
    # `delete=False` is important on some systems to keep the file accessible
    # while it's open by name.
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False) as temp_f:
        json.dump(payload_content, temp_f)
        temp_f.flush() # Ensure all data is written to disk
        temp_file_path = temp_f.name
        logging.info(f"Created temporary payload file at: {temp_file_path}")

    try:
        # Use a context manager for the file to ensure it's handled correctly
        with open(temp_file_path, 'rb') as f:
            # The file needs to be sent as multipart/form-data
            files = {
                'inputFiles': ('payload.txt', f, 'text/plain')
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(API_URL, headers=headers, data=form_data, files=files)
                response.raise_for_status()
                logging.info(f"Successfully triggered email agent via file. Status: {response.status_code}")
                return {"success": True, "message": "Email process initiated."}

    except httpx.HTTPStatusError as e:
        error_body = e.response.text
        logging.error(f"Email agent API error: {e.response.status_code} - {error_body}")
        raise Exception(f"Failed to trigger email agent: {error_body}")
    except Exception as e:
        logging.error(f"An unexpected error occurred while calling email agent: {e}", exc_info=True)
        raise
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            logging.info(f"Removed temporary payload file: {temp_file_path}") 